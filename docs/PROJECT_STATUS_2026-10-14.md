# Project status — October 14, 2026

## Completed in this release

1. TokenSpace v2 is the active memory foundation, with seven versioned
   migrations, hybrid lexical/vector retrieval, persistent ingestion jobs, and
   non-destructive consolidation records.
2. Oogway Core owns normal conversation, memory retrieval, bounded single-source
   absorption, and administrative AnyKeyCafe archive discovery and queueing.
3. The full-archive control is available only to the authenticated private
   Open WebUI environment. It is not registered with the public website guide or
   the Roundtable bridge.
4. Archive ingestion uses the existing WordPress API, TokenSpace database, and
   queue. The worker generates embeddings on CPU and leaves current services and
   stored memories in place.
5. The public website assistant now benefits from accumulated ingestion through
   the localhost-only public retrieval API. It receives only public AnyKeyCafe
   excerpts and cannot retrieve private sources.
6. Roundtable now supports confirmed preflight, ordered openings, mechanically
   classified review passes, operator rulings, and resumable deliberation
   without repeating openings. It defers while amendments, clarification
   requests, points of order, or unclassified interventions remain unresolved.
   External participants receive withholding markers for Little Oogway's local
   memory-informed material, including when that private seat fails; the local
   chair receives the full private docket. Participant dispositions require a
   strict first-line label, and chair output is rejected unless its disposition
   matches the mechanical ledger.
   Retry-safe local model calls receive one controlled retry. A failed chair
   report leaves the round open for chair-only recovery, without repeating paid
   or browser participant turns. Interrupted preflights can be recovered into a
   fresh confirmation, and the local monitor displays phase, participant,
   elapsed time, ledger state, and reported DeepSeek token usage.
7. A filtered 2,000-point public-memory export was mapped in Nomic Atlas. The
   live Little Oogway page includes the first snapshot and a link to the map.
8. The private Core session can search the live web through a loopback-only
   SearXNG service and read one bounded public HTTPS page at a time. External
   text is labeled untrusted evidence, active HTML is stripped, local-network
   targets are denied, and no result is automatically executed or absorbed.
9. That same private research surface can explicitly retrieve TokenSpace
   memories with IDs, provenance, and relevance scores, allowing Little Oogway
   to compare remembered context with current web evidence. The public website
   and Roundtable do not receive this private research tool.
10. The private Open WebUI selector now distinguishes direct Little Oogway Core
    conversation from the AI Roundtable. The Roundtable is connected through a
    localhost-only Pipe, while Nomic Embed and raw Qwen base engines are hidden
    from chat without being removed from the runtime.

## Verification

- TokenSpace: 5 tests passed.
- Oogway Core: 69 tests passed.
- Roundtable: 24 tests passed.
- Public website boundary: 2 tests passed.
- Live four-seat procedural validation: one opening phase, two review passes,
  one operator ruling, and one completed audit record. ChatGPT, Claude, and
  DeepSeek supported the ruled amendment; a transient local Ollama timeout was
  recorded as `UNAVAILABLE` rather than concealed.
- Live website Atlas section: desktop and phone layouts verified.
- Public map: contains only active AnyKeyCafe HTTPS sources; local files,
  conversations, private memories, and original database identifiers excluded.
- Live read-only retrieval boundary check: private retrieval found a selected
  private chat source; public retrieval returned 50 candidates and zero
  non-public sources.
- Independent philosopher audit findings B1-B11 were corrected: authenticated
  operator sessions, path-aware command policy, secret-free execution
  environments, fail-closed privileged operations, seat-based Roundtable
  redaction, strict dispositions, mechanical chair validation, and exclusive
  active preflight leases.

## Deliberate exclusions

Runtime data is not source code. Database contents, historical transcripts,
browser sessions, API keys, ingestion logs, generated Atlas payloads, installed
virtual environments, and the frozen legacy corpus remain outside Git.

The GitHub release is a clean source snapshot. Deployments should retain local
configuration and database volumes rather than replacing them from the
repository.
