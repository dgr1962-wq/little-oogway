# Security and release boundary

## Never commit

- `.env` files or credentials of any kind
- Nomic, DeepSeek, WordPress, OpenRouter, or worker tokens
- TokenSpace database contents, dumps, Docker volumes, or connection passwords
- private conversations, imported transcripts, Roundtable transcripts, or
  browser profiles
- raw model/corpus files, including the frozen legacy Pile material
- generated Atlas JSONL exports, even when their inputs were public

Only `.env.example` templates with inert placeholders belong in source control.

## Public versus administrative capabilities

Archive-wide ingestion is administrative. It is exposed through the authorized
Oogway Core runtime and the private Open WebUI tool, not through the public
website assistant. Public retrieval is constrained to active HTTPS sources on
`anykeycafe.com` and `www.anykeycafe.com` and is served through a localhost-only
API to an outbound worker.

The Nomic Atlas exporter independently enforces the same public-source boundary,
opens TokenSpace read-only, replaces database UUIDs with stable one-way point
identifiers, and excludes local files and conversations.

## Machine-operator boundary

- Machine tools exist only in the private Open WebUI administrative session.
- The public website and Roundtable API do not load or proxy operator tools.
- The operator API binds to loopback and requires a local bearer token for its
  programmatic endpoints.
- Read access is limited to `/home/darren` and `/mnt/storage`, excluding known
  credential and browser-profile locations.
- Mutating commands are proposals first. Approval and execution state is kept in
  the TokenSpace `operator_actions` audit ledger.
- Commands are structured argument arrays; shells, destructive utilities, and
  privilege-escalation programs are denied.
- The current service has user-level authority only and runs with
  `NoNewPrivileges=true`. Root capability requires a separately reviewed,
  narrowly scoped broker and a local administrator installation step.

## Operational safety

- Preserve the existing TokenSpace v2 data volume when updating source.
- Do not run generic Docker prune or volume deletion commands.
- Do not connect current tooling to the frozen legacy database.
- Review generated datasets before uploading them to any external service.
- Keep public and private service credentials in mode-600 local files.

Security-sensitive reports should be shared privately with the operator rather
than opened as a public issue.
