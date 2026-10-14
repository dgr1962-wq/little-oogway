from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .controller import RoundtableController
from .participants import MockParticipant, OllamaParticipant, Participant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one local Roundtable round")
    parser.add_argument("--prompt", required=True, help="Question posed to every participant")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model for Little Oogway")
    parser.add_argument(
        "--ollama-url",
        default="http://127.0.0.1:11434",
        help="Base URL of the local Ollama service",
    )
    parser.add_argument(
        "--transcript-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory for JSONL transcripts",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--with-mock", action="store_true", help="Run a mock observer before Oogway")
    mode.add_argument("--mock-only", action="store_true", help="Run without contacting Ollama")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    participants: list[Participant] = []
    if args.with_mock or args.mock_only:
        participants.append(MockParticipant())
    if not args.mock_only:
        participants.append(
            OllamaParticipant(model=args.model, base_url=args.ollama_url)
        )

    result = RoundtableController(
        participants=participants,
        transcript_directory=args.transcript_dir,
    ).run_round(args.prompt)

    print(f"Round {result.round_id}")
    for participant in result.participants:
        print(f"\n[{participant.participant}] ({participant.duration_ms} ms)")
        print(participant.content if participant.succeeded else participant.error)
    print(f"\nTranscript: {result.transcript_path}")
    return 0 if result.succeeded else 1


def main() -> int:
    return run()
