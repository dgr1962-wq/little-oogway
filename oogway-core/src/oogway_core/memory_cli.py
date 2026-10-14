from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import psycopg

from .cli import development_dsn
from .archive import AnyKeyArchiveController
from .embeddings import OllamaEmbeddingModel
from .ingestion import classify_locator, fetch_source, validate_url
from .memory import chunk_text, load_transcript, redact_secrets
from .repository import MemoryHit, TokenSpaceRepository
from .retrieval import HybridMemoryRetriever
from .retrieval_eval import evaluate_retrieval, load_evaluation
from .tools import start_background_worker


WORKSPACE = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import, embed, and search Oogway memories")
    parser.add_argument(
        "--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument(
        "--model", default=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:v1.5")
    )
    commands = parser.add_subparsers(dest="command", required=True)

    import_parser = commands.add_parser("import", help="Import retrieval-only text sources")
    import_parser.add_argument("paths", nargs="+", type=Path)
    import_parser.add_argument("--chunk-chars", type=int, default=3000)
    import_parser.add_argument("--overlap", type=int, default=300)

    embed_parser = commands.add_parser("embed", help="Embed imported memories")
    embed_parser.add_argument("--batch-size", type=int, default=32)

    search_parser = commands.add_parser("search", help="Search imported memories")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--lexical-only", action="store_true")

    evaluate_parser = commands.add_parser(
        "evaluate", help="Run the versioned retrieval quality benchmark"
    )
    evaluate_parser.add_argument(
        "--file", type=Path, default=WORKSPACE / "oogway-core/evals/memory_retrieval.json"
    )
    evaluate_parser.add_argument("--json-output", type=Path)

    consolidate_parser = commands.add_parser(
        "consolidate", help="Record safe exact-duplicate relationships"
    )
    consolidate_parser.add_argument(
        "--propose-semantic", action="store_true",
        help="also record conservative cross-source near-duplicate proposals",
    )

    absorb_parser = commands.add_parser(
        "absorb", help="Queue a local text file or approved HTTPS page for ingestion"
    )
    absorb_parser.add_argument("source")
    absorb_parser.add_argument("--chunk-chars", type=int, default=3000)
    absorb_parser.add_argument("--overlap", type=int, default=300)
    absorb_parser.add_argument("--max-attempts", type=int, default=3)
    absorb_parser.add_argument("--no-start", action="store_true")

    archive_parser = commands.add_parser(
        "archive-absorb",
        help="Discover and queue the published AnyKeyCafe archive",
    )
    archive_parser.add_argument(
        "--sample", type=int,
        help="queue only the first N canonical URLs for a controlled test",
    )
    archive_parser.add_argument("--chunk-chars", type=int, default=3000)
    archive_parser.add_argument("--overlap", type=int, default=300)
    archive_parser.add_argument("--max-attempts", type=int, default=3)
    archive_parser.add_argument("--no-start", action="store_true")
    archive_parser.add_argument("--inventory-only", action="store_true")

    worker_parser = commands.add_parser(
        "worker", help="Process durable ingestion jobs in the background"
    )
    worker_parser.add_argument("--drain", action="store_true")
    worker_parser.add_argument("--batch-size", type=int, default=8)
    worker_parser.add_argument("--gpu", action="store_true")
    worker_parser.add_argument("--threads", type=int, default=2)

    jobs_parser = commands.add_parser("jobs", help="Show recent ingestion jobs")
    jobs_parser.add_argument("--limit", type=int, default=20)
    consolidate_parser.add_argument("--vector-threshold", type=float, default=0.96)
    consolidate_parser.add_argument("--text-overlap-threshold", type=float, default=0.80)
    consolidate_parser.add_argument("--neighbors", type=int, default=10)
    consolidate_parser.add_argument(
        "--select-canonical", action="store_true",
        help="choose and record the preferred copy for every confirmed relation",
    )

    commands.add_parser("status", help="Show memory and embedding counts")
    return parser


def source_locator(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(WORKSPACE))
    except ValueError:
        return str(resolved)


def import_paths(args: argparse.Namespace, repository: TokenSpaceRepository) -> int:
    total = 0
    for path in args.paths:
        text, digest, byte_count = load_transcript(path)
        source_modified_at = datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat()
        redacted = redact_secrets(text)
        chunks = chunk_text(
            redacted.content,
            max_chars=args.chunk_chars,
            overlap=args.overlap,
        )
        locator = source_locator(path)
        _, count = repository.import_source_chunks(
            source_type="chat-export-text",
            source_locator=locator,
            content_sha256=digest,
            source_metadata={
                "retrieval_only": True,
                "original_filename": path.name,
                "bytes": byte_count,
                "lines": text.count("\n") + 1,
                "source_modified_at": source_modified_at,
                "redactions": redacted.counts,
                "chunk_chars": args.chunk_chars,
                "overlap": args.overlap,
            },
            chunks=chunks,
        )
        total += count
        print(f"{locator}: {count} chunks, redactions={sum(redacted.counts.values())}")
    print(f"Imported {len(args.paths)} sources and {total} chunks")
    return 0


def embed_memories(
    args: argparse.Namespace,
    repository: TokenSpaceRepository,
    model: OllamaEmbeddingModel,
) -> int:
    if args.batch_size < 1 or args.batch_size > 128:
        raise ValueError("batch-size must be between 1 and 128")
    digest = model.digest()
    completed = 0
    while True:
        pending = repository.unembedded_memories(
            model_digest=digest,
            limit=args.batch_size,
        )
        if not pending:
            break
        vectors = model.embed([f"search_document: {content}" for _, content in pending])
        completed += repository.store_embeddings(
            model=model.model_name,
            model_digest=digest,
            embeddings=[(memory_id, vector) for (memory_id, _), vector in zip(pending, vectors)],
        )
        print(f"Embedded {completed} memories", flush=True)
    print(f"Embedding complete: {completed} new vectors with {model.model_name} ({digest[:12]})")
    return 0


def process_ingestion_job(
    repository: TokenSpaceRepository,
    model: OllamaEmbeddingModel,
    *,
    batch_size: int,
) -> bool:
    job = repository.claim_ingestion_job()
    if job is None:
        return False
    try:
        source = fetch_source(job.source_kind, job.source_locator)
        repository.set_ingestion_stage(job.id, "normalizing")
        redacted = redact_secrets(source.text)
        repository.set_ingestion_stage(job.id, "chunking")
        chunk_chars = int(job.options.get("chunk_chars", 3000))
        overlap = int(job.options.get("overlap", 300))
        chunks = chunk_text(redacted.content, max_chars=chunk_chars, overlap=overlap)
        source_id, chunk_count = repository.import_source_chunks(
            source_type=f"absorbed-{source.kind}",
            source_locator=source.locator,
            content_sha256=source.content_sha256,
            source_metadata={
                "retrieval_only": True,
                "bytes": source.byte_count,
                "redactions": redacted.counts,
                "chunk_chars": chunk_chars,
                "overlap": overlap,
                **source.metadata,
            },
            chunks=chunks,
            provenance_source="background-ingestion",
        )
        repository.set_ingestion_stage(job.id, "embedding")
        digest = model.digest()
        embedded = 0
        while True:
            pending = repository.unembedded_memories(
                model_digest=digest, limit=batch_size, source_id=source_id
            )
            if not pending:
                break
            vectors = model.embed(
                [f"search_document: {content}" for _, content in pending]
            )
            embedded += repository.store_embeddings(
                model=model.model_name,
                model_digest=digest,
                embeddings=[
                    (memory_id, vector)
                    for (memory_id, _), vector in zip(pending, vectors)
                ],
            )
        repository.set_ingestion_stage(job.id, "indexing")
        repository.complete_ingestion_job(
            job.id,
            {
                "source_id": source_id,
                "content_sha256": source.content_sha256,
                "chunks": chunk_count,
                "embeddings_created": embedded,
                "redactions": redacted.counts,
            },
        )
        print(f"Completed {job.id}: {chunk_count} chunks, {embedded} new embeddings")
    except Exception as exc:
        retrying = repository.fail_ingestion_job(job.id, f"{type(exc).__name__}: {exc}")
        state = "queued for retry" if retrying else "failed"
        print(f"Job {job.id} {state}: {exc}")
    return True


def print_hits(hits: list[MemoryHit]) -> None:
    for position, hit in enumerate(hits, start=1):
        excerpt = " ".join(hit.content.split())[:500]
        print(
            f"\n{position}. {hit.source_locator} chunk {hit.source_ordinal} "
            f"score={hit.combined_score:.4f} "
            f"lexical={hit.lexical_score:.4f} semantic={hit.semantic_score:.4f}"
        )
        print(excerpt)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = TokenSpaceRepository(development_dsn())
    model = OllamaEmbeddingModel(model_name=args.model, base_url=args.ollama_url)
    if args.command == "import":
        return import_paths(args, repository)
    if args.command == "embed":
        return embed_memories(args, repository, model)
    if args.command == "absorb":
        if args.chunk_chars < 200 or args.chunk_chars > 20000:
            raise ValueError("chunk-chars must be between 200 and 20000")
        if args.overlap < 0 or args.overlap >= args.chunk_chars:
            raise ValueError("overlap must be nonnegative and smaller than chunk-chars")
        if args.max_attempts < 1 or args.max_attempts > 20:
            raise ValueError("max-attempts must be between 1 and 20")
        kind, locator = classify_locator(args.source)
        if kind == "url":
            validate_url(locator)
        job_id, created = repository.enqueue_ingestion_job(
            source_kind=kind,
            source_locator=locator,
            options={"chunk_chars": args.chunk_chars, "overlap": args.overlap},
            max_attempts=args.max_attempts,
        )
        print(f"{'Queued' if created else 'Already active'} ingestion job {job_id}: {locator}")
        if not args.no_start:
            start_background_worker()
        return 0
    if args.command == "archive-absorb":
        if args.sample is not None and (args.sample < 1 or args.sample > 10000):
            raise ValueError("sample must be between 1 and 10000")
        if args.chunk_chars < 200 or args.chunk_chars > 20000:
            raise ValueError("chunk-chars must be between 200 and 20000")
        if args.overlap < 0 or args.overlap >= args.chunk_chars:
            raise ValueError("overlap must be nonnegative and smaller than chunk-chars")
        if args.max_attempts < 1 or args.max_attempts > 20:
            raise ValueError("max-attempts must be between 1 and 20")
        controller = AnyKeyArchiveController(repository)
        if args.inventory_only:
            inventory = controller.discover()
            for item in inventory[: args.sample]:
                print(f"{item.url} [{', '.join(item.discovered_by)}]")
            print(f"Discovered {len(inventory)} canonical published URLs")
            return 0
        result = controller.enqueue(
            sample=args.sample,
            chunk_chars=args.chunk_chars,
            overlap=args.overlap,
            max_attempts=args.max_attempts,
        )
        print(
            f"Discovered {result.discovered}; selected {result.selected}; "
            f"queued {result.queued}; already active {result.already_active}"
        )
        for job_id, url in zip(result.job_ids, result.urls):
            print(f"{job_id} {url}")
        if not args.no_start and result.queued:
            start_background_worker()
        return 0
    if args.command == "worker":
        if args.batch_size < 1 or args.batch_size > 128:
            raise ValueError("batch-size must be between 1 and 128")
        if args.threads < 1 or args.threads > 8:
            raise ValueError("threads must be between 1 and 8")
        worker_model = OllamaEmbeddingModel(
            model_name=args.model,
            base_url=args.ollama_url,
            num_gpu=None if args.gpu else 0,
            num_thread=args.threads,
        )
        processed = 0
        while process_ingestion_job(
            repository, worker_model, batch_size=args.batch_size
        ):
            processed += 1
            if not args.drain:
                break
        print(f"Worker processed {processed} job(s)")
        return 0
    if args.command == "jobs":
        if args.limit < 1 or args.limit > 100:
            raise ValueError("limit must be between 1 and 100")
        jobs = repository.list_ingestion_jobs(args.limit)
        for job in jobs:
            detail = job.error or json.dumps(job.result, sort_keys=True)
            print(
                f"{job.id} {job.status}/{job.stage} attempts="
                f"{job.attempt_count}/{job.max_attempts} {job.source_locator} {detail}"
            )
        print(f"{len(jobs)} job(s)")
        return 0
    if args.command == "search":
        if args.limit < 1 or args.limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if args.lexical_only:
            hits = repository.search_memories_lexical(args.query, limit=args.limit * 5)
            hits = repository.prefer_confirmed_memories(hits)[: args.limit]
        else:
            hits = HybridMemoryRetriever(repository, model).retrieve(
                args.query, limit=args.limit
            )
        print_hits(hits)
        print(f"\n{len(hits)} result(s)")
        return 0
    if args.command == "evaluate":
        specification = load_evaluation(args.file)
        report = evaluate_retrieval(
            HybridMemoryRetriever(repository, model), specification
        )
        for result in report.results:
            status = "PASS" if result["passed"] else "FAIL"
            rank = "-" if result["rank"] is None else result["rank"]
            score = "-" if result["top_score"] is None else f"{result['top_score']:.4f}"
            print(
                f"{status} {result['id']}: rank={rank} results={result['result_count']} "
                f"top_score={score} latency={result['latency_ms']:.2f}ms"
            )
        print(
            "\nMetrics: "
            f"hit@{specification.get('limit', 5)}={report.positive_hit_rate:.3f}, "
            f"MRR={report.mean_reciprocal_rank:.3f}, "
            f"negative_rejection={report.negative_rejection_rate:.3f}, "
            f"source_diversity={report.average_source_diversity:.3f}, "
            f"average_latency={report.average_latency_ms:.2f}ms"
        )
        print(f"Evaluation: {'PASS' if report.passed else 'FAIL'}")
        if args.json_output:
            args.json_output.write_text(
                json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8"
            )
        return 0 if report.passed else 2
    if args.command == "consolidate":
        result = repository.consolidate_exact_duplicates()
        semantic = None
        if args.propose_semantic:
            semantic = repository.propose_semantic_duplicates(
                model_digest=model.digest(),
                vector_threshold=args.vector_threshold,
                text_overlap_threshold=args.text_overlap_threshold,
                neighbors=args.neighbors,
            )
        canonical = repository.apply_canonical_policy() if args.select_canonical else None
        status = repository.consolidation_status()
        print(
            f"Exact duplicate groups: {result['groups']}\n"
            f"Confirmed duplicate relations: {result['relations']}\n"
            f"Stored consolidation relations: {status['relations']}\n"
            "Original memories changed or deleted: 0"
        )
        if semantic is not None:
            print(
                f"Semantic neighbor pairs above vector threshold: "
                f"{semantic['neighbors_scanned']}\n"
                f"Near-duplicate proposals: {semantic['proposals']}\n"
                "Semantic proposals automatically confirmed: 0"
            )
        if canonical is not None:
            reasons = ", ".join(
                f"{reason}={count}" for reason, count in sorted(canonical["reasons"].items())
            )
            print(
                f"Canonical preferences evaluated: {canonical['relations_evaluated']}\n"
                f"Canonical preferences changed: {canonical['preferences_changed']}\n"
                f"Selection reasons: {reasons}"
            )
        return 0
    digest = model.digest()
    status = repository.memory_status(model_digest=digest)
    consolidation = repository.consolidation_status()
    print(f"Sources: {status['sources']}")
    print(f"Memories: {status['memories']}")
    print(f"Embeddings: {status['embeddings']}")
    print(f"Missing for {model.model_name}: {status['missing_for_model']}")
    print(f"Consolidation relations: {consolidation['relations']}")
    print(f"Confirmed exact duplicates: {consolidation['exact_duplicates']}")
    print(f"Proposed semantic near-duplicates: {consolidation['proposed']}")
    return 0


def main() -> int:
    try:
        return run()
    except (OSError, UnicodeError, RuntimeError, ValueError, psycopg.Error) as exc:
        print(f"oogway-memory: {exc}")
        return 1
