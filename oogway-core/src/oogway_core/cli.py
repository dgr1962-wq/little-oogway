from __future__ import annotations

import argparse
import os
from typing import Sequence
from urllib.parse import quote

import psycopg

from .ollama import OllamaChatModel
from .embeddings import OllamaEmbeddingModel
from .repository import TokenSpaceRepository
from .retrieval import HybridMemoryRetriever
from .session import ConversationSession
from .tools import AbsorbSourceTool


def development_dsn(environment: dict[str, str] | None = None) -> str:
    env = os.environ if environment is None else environment
    host = env.get("TOKENSPACE_HOST", "127.0.0.1")
    port = env.get("TOKENSPACE_PORT", "55432")
    database = env.get("TOKENSPACE_DATABASE", "tokenspace_v2_dev")
    user = env.get("TOKENSPACE_USER", "tokenspace_dev")
    password = env.get("TOKENSPACE_PASSWORD")
    if (host, port, database, user) != (
        "127.0.0.1", "55432", "tokenspace_v2_dev", "tokenspace_dev"
    ):
        raise ValueError("The development CLI only targets 127.0.0.1:55432/tokenspace_v2_dev")
    if not password:
        raise ValueError("Set TOKENSPACE_PASSWORD from the ignored tokenspace/.env file")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one persisted Little Oogway turn")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--title", default="Oogway Core local session")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument(
        "--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--memory-limit", type=int, default=5)
    parser.add_argument("--no-tools", action="store_true")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model = OllamaChatModel(model_name=args.model, base_url=args.ollama_url)
    store = TokenSpaceRepository(development_dsn())
    retriever = None
    if not args.no_memory:
        retriever = HybridMemoryRetriever(
            repository=store,
            embedding_model=OllamaEmbeddingModel(base_url=args.ollama_url),
        )
    session = ConversationSession(
        model=model,
        store=store,
        memory_retriever=retriever,
        memory_limit=args.memory_limit,
        tools=() if args.no_tools else (AbsorbSourceTool(store),),
    )
    conversation_id = session.start(title=args.title, metadata={"interface": "cli"})
    response = session.ask(args.prompt)
    print(response.content)
    print(f"\nConversation: {conversation_id}")
    print(f"Round: {response.round_id}")
    print(f"Response turn: {response.response_turn_id}")
    return 0


def main() -> int:
    try:
        return run()
    except (RuntimeError, ValueError, psycopg.Error) as exc:
        print(f"oogway-chat: {exc}")
        return 1
