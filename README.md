# Little Oogway

Little Oogway is a local-first assistant whose conversations, durable memory,
website knowledge, and multi-model deliberations remain under the operator's
control. This repository holds the source and reproducible configuration. It
does **not** hold the live TokenSpace database, private conversations, API
credentials, browser profiles, model files, or the frozen legacy corpus.

## What works now

- **Oogway Core** runs local Ollama conversations and persists ordered,
  provenance-tagged turns in TokenSpace.
- **TokenSpace v2** provides isolated PostgreSQL + pgvector storage, versioned
  migrations, hybrid retrieval, non-destructive consolidation, and a durable
  ingestion queue.
- **AnyKeyCafe archive ingestion** discovers the WordPress REST API and
  sitemaps, queues one canonical source at a time, and generates CPU-only
  embeddings without touching the legacy database.
- **Public website retrieval** searches only absorbed public AnyKeyCafe HTTPS
  sources. The website worker cannot access private conversations or local
  files.
- **Private web research** uses a loopback-only SearXNG service plus bounded
  public HTTPS page reading. Results remain explicitly untrusted evidence and
  are never absorbed, executed, or exposed to public visitors automatically.
- **Memory-to-web research** lets the authenticated private session retrieve
  provenance-bearing TokenSpace memories, compare them with current sources,
  and report citations and uncertainty without automatically changing memory.
- **Roundtable** coordinates Little Oogway, ChatGPT, Claude, and optionally
  DeepSeek through confirmed preflight, opening statements, resumable review
  passes, a mechanical procedural ledger, operator rulings, and locally chaired
  final minutes.
- **Private model selector** presents Little Oogway Core for direct conversation,
  AI Roundtable for structured deliberation, and Qwen 3 Visual for image work.
  Raw base and embedding models remain available to the runtime but are hidden
  from ordinary chat selection.
- **Private visual understanding** normalizes WebP and other common image formats
  before Qwen3-VL inspection, keeps visible text untrusted, and composes SDXL
  variation prompts in a separate second pass.
- **Main Desk image workspace control** lets only an authenticated Open WebUI
  administrator check, start, stop, or restart Stable Diffusion over an
  authenticated LAN service. It provides no remote shell or arbitrary command
  execution, and is not attached to the public website.
- **Nomic Atlas export** produces a deliberately filtered public-only semantic
  map. The first 2,000-point map is linked from the live Little Oogway page.

Current public pages:

- [Little Oogway](https://anykeycafe.com/little-oogway/)
- [Ask Little Oogway](https://anykeycafe.com/ai/little-oogway/)
- [TokenSpace](https://anykeycafe.com/tokenspace/)
- [AI Round Table](https://anykeycafe.com/ai-round-table/)
- [Public memory map](https://atlas.nomic.ai/data/dgr1962/little-oogway-public-anykeycafe-memory-field/map)

## Repository layout

- `oogway-core/` — conversation runtime, retrieval, ingestion controller,
  Open WebUI tool, localhost APIs, services, and tests.
- `tokenspace/` — the isolated v2 database definition, migrations, safe
  lifecycle helper, and smoke tests.
- `roundtable/` — deterministic multi-participant deliberation controller and
  audit-transcript machinery.
- `integrations/public-website/` — outbound WordPress worker and localhost-only
  public retrieval service definition.
- `integrations/nomic-atlas/` — guarded public-only export and upload tools.
- `integrations/searxng/` — loopback-only private metasearch service.
- `integrations/wordpress/` — source for the Little Oogway Atlas website
  section.
- `docs/` — experiment plans and dated project status reports.

## Security and data boundaries

The normal Oogway Core runtime is the only administrative path for archive-wide
ingestion. The public WordPress guide has a separate, deliberately smaller
surface: it can submit a visitor question and receive public AnyKeyCafe excerpts
and an answer, but it cannot enqueue ingestion, inspect private TokenSpace
memory, run shell commands, or reach the legacy database.

External Roundtable participants never receive Little Oogway's memory-informed
opening. The local chair receives the complete local docket; external reviewers
see a withholding marker in place of the private opening.

See [SECURITY.md](SECURITY.md) for the release boundary and operator rules.

## Tests

The repository uses the standard-library `unittest` runner:

```bash
python3 -m unittest discover -s tokenspace/tests -v
PYTHONPATH=oogway-core/src python3 -m unittest discover -s oogway-core/tests -v
PYTHONPATH=roundtable/src python3 -m unittest discover -s roundtable/tests -v
python3 -m unittest discover -s integrations/public-website -v
```

On October 14, 2026, all 106 tests passed (TokenSpace 5, Oogway Core 75,
Roundtable 24, public website boundary 2). Runtime counts and ingestion progress
are live operational state and are intentionally not committed.

## Development boundary

The active v2 database is the isolated Compose stack at `127.0.0.1:55432`.
Ollama and model files remain host-side. The old approximately 155 GB database
and raw corpus are frozen historical material and are neither read nor modified
by this repository's current runtime.

Start with the component documentation:

- [Oogway Core](oogway-core/README.md)
- [TokenSpace](tokenspace/README.md)
- [Roundtable](roundtable/README.md)
