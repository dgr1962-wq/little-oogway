from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence


class CitableMemory(Protocol):
    memory_id: str
    source_locator: str
    source_ordinal: int


_CITATION = re.compile(r"\[memory:([^\]\s]+)\]")


@dataclass(frozen=True)
class CitationResult:
    content: str
    metadata: dict[str, object]


def finalize_memory_citations(
    content: str, memories: Sequence[CitableMemory]
) -> CitationResult:
    """Validate model citations and add a deterministic retrieval audit trail."""
    available = {memory.memory_id: memory for memory in memories}
    cited = _CITATION.findall(content)
    valid = list(dict.fromkeys(item for item in cited if item in available))
    invalid = list(dict.fromkeys(item for item in cited if item not in available))
    cleaned = _CITATION.sub(
        lambda match: match.group(0)
        if match.group(1) in available
        else "[memory:unverified]",
        content,
    ).rstrip()
    appendix = ["", "Memory sources consulted:"]
    appendix.extend(
        f"- [memory:{memory.memory_id}] "
        f"{memory.source_locator}#chunk-{memory.source_ordinal}"
        for memory in memories
    )
    return CitationResult(
        content=cleaned + "\n" + "\n".join(appendix),
        metadata={
            "available_memory_ids": list(available),
            "valid_model_citations": valid,
            "invalid_model_citations": invalid,
            "model_citation_count": len(cited),
            "source_count": len(memories),
        },
    )
