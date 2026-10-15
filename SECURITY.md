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
- The Open WebUI Roundtable selector is a private in-process Pipe that may call
  only the Roundtable API on `127.0.0.1:8091`; it does not expose that API to the
  LAN or public website.
- Nomic Embed and raw Qwen engines are hidden from the chat selector, not
  removed. TokenSpace may continue to use Nomic for CPU-only embeddings.
- The operator API binds to loopback, rejects unexpected Host, Origin, and
  cross-site browser requests, and requires a bearer token for programmatic
  endpoints. The approval dashboard requires a short-lived authenticated
  session with a distinct CSRF token; it never embeds the bearer token.
- Read access is limited to `/home/darren` and `/mnt/storage`, excluding known
  credential and browser-profile locations. Protected filenames include local
  environment files, operator and service tokens, Git/netrc credentials,
  common credential JSON files, and WordPress `wp-config.php`.
- Mutating commands are proposals first. Approval and execution state is kept in
  the TokenSpace `operator_actions` audit ledger.
- Commands are structured argument arrays and use a small path-aware allowlist
  (`mkdir`, `touch`, `cp`, and `mv`). Every file operand is revalidated at both
  proposal and execution time. All other executables fail closed.
- Executed commands receive a minimal environment with no TokenSpace or
  PostgreSQL credentials. The service itself is systemd-hardened and remains
  user-level. Privileged execution is disabled until individual administrative
  operations have argument-level broker profiles; an executable name alone is
  never treated as a sufficient root boundary.
- Pending proposals are bounded to reduce approval-fatigue attacks.

## Reciprocal Main Desk boundary

- Cross-machine project access uses a dedicated source-address-restricted key
  forced to `internal-sftp`; it cannot open a shell, allocate a terminal, or
  forward agents, X11, or network ports.
- Little Oogway's persistent Core-facing mounts expose only the operator's
  `Documents` directory and the dedicated `/mnt/AI_WORKSPACE/website-staging`
  tree. The forced-SFTP credential belongs to the operator account and is not a
  filesystem chroot; its private key is therefore kept outside Core's tool
  interface and must not be handed to a model or public service.
- Mounted paths remain subject to the same Core `PathPolicy`, protected-name
  rules, and authenticated private-session boundary as local files.
- File access is not publication authority. Live deployment must use a separate
  target-specific controller that presents a preview/diff and requires an
  explicit administrator approval before changing the hosted site.

## Roundtable and creative-production boundary

- Core may prepare a Roundtable preflight and bounded document packet, but the
  preflight contacts nobody. External calls require a second exact typed
  confirmation containing that preflight's UUID.
- Fixed creative jobs never accept a command line or script. FFmpeg uses named
  profiles, and Blender accepts only an approved `.blend` path plus a 1–300
  frame range while embedded Python is disabled.
- Installing OBS, Kdenlive, Audacity, Inkscape, or another desktop application
  does not grant autonomous GUI or publication control. Each state-changing
  controller requires its own reviewed operation and confirmation policy.

## Private web-research boundary

- Web search and page reading exist only in the authenticated private Open
  WebUI session and the bearer-protected loopback Core service.
- SearXNG binds to loopback. The public website and Roundtable do not load or
  proxy the web-research tool.
- Page reading permits credential-free public HTTPS URLs on port 443, rejects
  literal IP addresses and local/private/reserved DNS results, revalidates
  redirects, accepts only bounded textual content, and strips active HTML.
- Search snippets and fetched pages are labeled untrusted evidence. Their text
  never grants authority to call tools, reveal secrets, modify the machine, or
  enter memory. Important claims require independent or primary-source checks.
- Search and reading do not enqueue ingestion. Absorption remains a separate,
  explicit administrative act with its existing audit trail.
- Private TokenSpace retrieval is available beside web research so historical
  context can be compared with current evidence. Memory identifiers and private
  source locators remain confined to the authenticated administrative session.

## Operational safety

- Preserve the existing TokenSpace v2 data volume when updating source.
- Do not run generic Docker prune or volume deletion commands.
- Do not connect current tooling to the frozen legacy database.
- Review generated datasets before uploading them to any external service.
- Keep public and private service credentials in mode-600 local files.

Security-sensitive reports should be shared privately with the operator rather
than opened as a public issue.
