# Oogway Core

Oogway Core is Little Oogway's model-neutral conversation runtime. Its first vertical slice calls host-side Ollama, records the complete exchange in the isolated TokenSpace v2 development database, and exposes an adapter matching Roundtable's existing participant protocol.

## Runtime boundary

- Ollama and `qwen3:8b` run on the host at `http://127.0.0.1:11434`.
- PostgreSQL runs in the TokenSpace Compose stack at `127.0.0.1:55432`.
- The development CLI refuses any database host, port, name, or user other than the isolated TokenSpace development target.
- The password comes from the environment and is never stored in source files or command output.
- Roundtable remains host-side. The adapter uses structural compatibility, so Roundtable itself does not depend on or import Oogway Core.

## Set up

```bash
cd /home/darren/Documents/Little-Oogway/oogway-core
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Start the database if needed:

```bash
cd /home/darren/Documents/Little-Oogway
python3 tokenspace/scripts/dev.py start
python3 tokenspace/scripts/dev.py migrate
```

## Run one persisted turn

Load the ignored development password without printing it, then run the CLI:

```bash
cd /home/darren/Documents/Little-Oogway/oogway-core
set -a
source ../tokenspace/.env
set +a
export TOKENSPACE_PASSWORD="$POSTGRES_PASSWORD"
.venv/bin/oogway-chat \
  --title "Local Oogway conversation" \
  --prompt "What should we remember from this exchange?"
```

The command prints the model response plus the TokenSpace conversation, round, and response-turn identifiers. One `ConversationSession` can accept multiple prompts; it keeps a single conversation and increments the round ordinal for each call.

Memory retrieval is enabled by default. Before each model call, Core performs hybrid full-text and semantic search, rejects results below the calibrated relevance threshold, suppresses adjacent overlapping chunks, and limits how many chunks one source can contribute. It injects the remaining excerpts as explicitly untrusted historical context and records their IDs and scores in the response-turn metadata. Answers include a deterministic `Memory sources consulted` appendix, while model-written `[memory:IDENTIFIER]` citations are validated and recorded. Use `--no-memory` when a memory-free response is required.

## Import and search memory

The retrieval model is `nomic-embed-text:v1.5`, pinned by its Ollama model digest when vectors are stored. Install it once:

```bash
ollama pull nomic-embed-text:v1.5
```

With `TOKENSPACE_PASSWORD` loaded as above:

```bash
cd /home/darren/Documents/Little-Oogway/oogway-core
.venv/bin/oogway-memory import ../data/transcripts/*.txt
.venv/bin/oogway-memory embed --batch-size 32
.venv/bin/oogway-memory status
.venv/bin/oogway-memory search "How should Oogway preserve human intent?"
.venv/bin/oogway-memory search --lexical-only "exact phrase or keyword"
.venv/bin/oogway-memory evaluate
.venv/bin/oogway-memory consolidate
.venv/bin/oogway-memory consolidate --propose-semantic
```

The versioned evaluation set is in `evals/memory_retrieval.json`. It contains positive corpus questions and unrelated negative controls, and fails if hit rate, reciprocal rank, negative rejection, or source diversity falls below its declared thresholds. Use `--json-output PATH` to save a machine-readable report.

Consolidation is deliberately non-destructive. The base command records byte-identical memory chunks as confirmed duplicate relationships in TokenSpace, is safe to repeat, and reports how many originals changed or were deleted. Retrieval also fingerprints normalized result text so equivalent chunks from different exports cannot occupy multiple context slots. The `--propose-semantic` pass considers only cross-source neighbors, requires at least 0.96 vector similarity plus 80 percent five-token shingle containment, and stores matches with `proposed` review status. It never confirms, merges, or deletes them automatically. Manual decisions store a reviewer, rationale, and review time in the relation evidence, and repeat detection preserves those decisions. The thresholds and neighbor count can be adjusted with `--vector-threshold`, `--text-overlap-threshold`, and `--neighbors` for later experiments.

`consolidate --select-canonical` records a preferred copy for every confirmed relationship. It chooses an explicit conversation timestamp when available, then the more complete passage, then newer source-export time, and finally stable source order. Retrieval suppresses an alternate only when its preferred counterpart appears in the same candidate set, so unique boundary text remains searchable. Source memories and transcript files remain unchanged.

Import and embedding are idempotent. Re-running import updates the same source chunks, and embedding processes only memories missing the current model digest.

## Background absorption

Local text files and approved HTTPS pages can be submitted to a durable queue. Submission returns immediately; the user service fetches, normalizes, redacts, chunks, embeds, and indexes the source in the background. Jobs record their stage, attempt count, errors, and result counts in TokenSpace. Interrupted work is recovered, failed work uses bounded retries, and repeated unchanged content reuses its source and embeddings.

Install the low-priority recovery service once:

```bash
cd /home/darren/Documents/Little-Oogway/oogway-core
scripts/install-ingestion-service.sh
```

With `TOKENSPACE_PASSWORD` loaded as in the setup example:

```bash
.venv/bin/oogway-memory absorb /absolute/path/to/notes.txt
.venv/bin/oogway-memory absorb https://anykeycafe.com/little-o/
.venv/bin/oogway-memory jobs
```

Remote ingestion currently allows only HTTPS pages at `anykeycafe.com` and `www.anykeycafe.com`; redirects are checked again before content is accepted. Sources are limited to 10 MiB and to plain text or HTML. The worker defaults to CPU-only Ollama embeddings with two threads and batches of eight, leaving the GPU available for conversation. It runs with lower CPU and disk priority, drains the queue, and exits. The two-minute timer is a recovery path; `absorb` also starts the worker immediately.

The queue is the persistence layer behind the conversational “absorb this source” tool.

### Full AnyKeyCafe archive controller

Archive-wide ingestion reuses the same TokenSpace queue and worker. The
controller discovers canonical public content through the WordPress REST API
and sitemaps, filters out taxonomy/archive duplicates, and enqueues one source
at a time. It does not introduce another database or ingestion path.

The administrative Open WebUI tool is
`openwebui_tools/anykey_archive_ingestion.py`. It invokes the authorized Oogway
Core runner and is intended only for an authenticated private session. Do not
register it with the public WordPress assistant or the Roundtable bridge.

```bash
scripts/run-archive-controller.sh --inventory-only
scripts/run-archive-controller.sh --sample 3
scripts/run-archive-controller.sh
```

The normal worker continues to create CPU-only embeddings. Existing memory and
services stay in place, and the controller never connects to the frozen legacy
database.

The bounded conversational tool is now connected to the normal `oogway-chat` runtime. An explicit absorb request containing exactly one approved URL or local file path bypasses the language-model call, creates the real job, starts the worker, and persists the factual tool result as the response turn:

```bash
.venv/bin/oogway-chat \
  --prompt "Hey Little Oogway, absorb https://anykeycafe.com/tokenspace/"
```

“Absorb this” without an address asks for the exact source. Multiple sources are rejected so every job retains a clear audit trail. Discussion containing the word “absorb” without a source continues as ordinary conversation. Use `--no-tools` when a model-only turn is required.

The import pipeline hashes the original bytes, strips a UTF-8 byte-order mark, normalizes line endings, heuristically redacts common credential formats in the indexed copy, and records source paths, byte/line counts, chunk offsets, and redaction counts. Original transcript files are never modified. Every imported chunk is labeled `retrieval_only`; nothing is classified as training data.

## Use through Roundtable

`RoundtableParticipantAdapter` supplies the `name` property and `respond(prompt)` method already expected by `RoundtableController`:

```python
from oogway_core import (
    AbsorbSourceTool,
    ConversationSession,
    OllamaChatModel,
    RoundtableParticipantAdapter,
    TokenSpaceRepository,
)
from oogway_core.cli import development_dsn
from roundtable.controller import RoundtableController

store = TokenSpaceRepository(development_dsn())
session = ConversationSession(
    model=OllamaChatModel(),
    store=store,
    tools=(AbsorbSourceTool(store),),
)
participant = RoundtableParticipantAdapter(session)
result = RoundtableController([participant]).run_round("What matters here?")
```

The adapter returns TokenSpace conversation, round, and response-turn IDs in Roundtable's participant metadata. A model failure is recorded as a failed TokenSpace turn before it is raised to Roundtable, whose existing failure isolation then records it in JSONL.

### Open WebUI Roundtable model

The local OpenAI-compatible bridge exposes Roundtable as the model ID `little-oogway-roundtable` at `http://127.0.0.1:8091/v1`. It is registered in Open WebUI as a local OpenAI API connection, so it can be selected from the normal model picker while `qwen3:8b` remains the default model.

The bridge runs memory-aware Little Oogway plus visible ChatGPT and Claude browser participants. It conducts opening statements, a review pass with procedural dispositions, a mechanically classified ledger, and Little Oogway's chaired disposition. External services receive the submitted agenda and one another's public openings. Little Oogway's memory-informed opening is replaced by a withholding marker in every external docket, so recalled TokenSpace material stays local to the chair. When `DEEPSEEK_API_KEY` is configured, DeepSeek joins through its API and streams into a dedicated local monitor window. Without an API key, ChatGPT and Claude continue normally and DeepSeek is omitted. The bridge returns the ledger, chair's disposition, openings, reviews, and Round ID, while Roundtable writes its JSONL audit transcript under `roundtable/transcripts/webui`. Explicit single-source absorption requests use the bounded ingestion tool and return its factual result directly.

Optional DeepSeek settings belong in the local, mode-600 file `~/.config/little-oogway/roundtable.env`:

```bash
DEEPSEEK_API_KEY=replace-with-local-key
DEEPSEEK_MODEL=deepseek-flash
```

The service reads that file at startup. Do not commit it or put its contents in project transcripts.

The user service starts automatically and listens on localhost only:

```bash
systemctl --user status oogway-roundtable-api.service
curl http://127.0.0.1:8091/health
```

Its tracked unit and launcher are `systemd/oogway-roundtable-api.service` and `scripts/run-roundtable-api.sh`. After changing either one, run `systemctl --user daemon-reload` and restart the service.

### Private machine operator

Little Oogway's private Open WebUI can use the machine-operator tool in
`openwebui_tools/little_oogway_operator.py`. The tool is deliberately separate
from the public website and Roundtable bridges and refuses non-admin users.

The operator service listens only on `127.0.0.1:8094`. Read-only inspection is
available immediately, while commands are written to the TokenSpace
`operator_actions` audit ledger and remain pending until a local administrator
approves them in the loopback approval console. Commands use structured argument
arrays rather than shell text, and credential locations, shells, destructive
utilities, and privilege-escalation entry points are blocked.

Install the user service on Little Oogway with:

```bash
mkdir -p ~/.config/little-oogway
umask 077
openssl rand -hex 32 > ~/.config/little-oogway/operator.token
systemctl --user link "$PWD/systemd/oogway-operator.service"
systemctl --user daemon-reload
systemctl --user enable --now oogway-operator.service
```

This service normally runs as `darren` and holds no root credential. A red-risk
administrative request is limited to a reviewed executable allowlist,
recorded in the same ledger, and launched through PolicyKit only after local
approval. PolicyKit then requires graphical administrator authentication for
that specific operation. The model never receives a password, unrestricted
sudo, or a root shell.

### Public website retrieval

The AnyKeyCafe worker is intentionally separate from the private runtime. A
localhost-only API (`oogway-public-retrieval`) searches only active absorbed URL
sources under `https://anykeycafe.com/` and returns bounded excerpts. The
outbound website worker combines those excerpts with WordPress-provided public
context and sends the answer back to the site. It has no archive-ingestion,
shell, local-file, or private-conversation capability.

## Tests

```bash
cd /home/darren/Documents/Little-Oogway/oogway-core
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover Ollama chat and embedding requests, dimensionality validation, chunking, credential redaction, source hashing, ordered multi-round persistence, failed model-call persistence, memory-context handling, citation validation, retrieval relevance and diversity controls, evaluation scoring, blank prompts, the Roundtable response contract, and enforcement of the isolated development database target.

## Validation evidence

Runtime validation on October 13, 2026 completed real `qwen3:8b` conversations through host Ollama and through `RoundtableController` via `RoundtableParticipantAdapter`. The memory pipeline imported nine source files as 5,328 retrieval-only chunks, stored 5,328 768-dimensional embeddings, and completed both lexical and hybrid searches. A direct Core turn recalled four source chunks; a Roundtable turn recalled three. Both recorded their memory IDs without retrieval errors. Repeat import created no duplicate sources or memories, and a repeat embedding pass created zero vectors.

## Current scope

The legacy 155 GB bulk-ingestion database is frozen and intentionally excluded from the runtime. Core uses only TokenSpace v2, the nine deliberately imported historical transcripts, and conversations created through the new runtime. Imported text remains historical, untrusted, retrieval-only context. The bounded user-level operator and TokenSpace approval ledger are in place. Privileged maintenance is a separate red-risk tier requiring both ledger approval and per-operation graphical PolicyKit authentication.
