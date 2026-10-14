# Public AnyKeyCafe assistant

This directory contains the outbound-only WordPress worker and the service unit
for Oogway Core's localhost-only public retrieval API.

The worker asks local Ollama to answer with bounded excerpts drawn only from
public AnyKeyCafe pages. Its token authorizes only the WordPress job queue; it
does not grant shell access, private memory access, archive ingestion, or access
to the legacy database.

Configuration belongs in a local mode-600 environment file and must not be
committed. The tracked worker accepts `LITTLE_O_SITE`, `LITTLE_O_WORKER_TOKEN`,
`OLLAMA_URL`, `LITTLE_O_MODEL`, and `PUBLIC_RETRIEVAL_URL` through the
environment.
