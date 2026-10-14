# Integrations

These components connect Little Oogway to public surfaces without widening the
private runtime boundary.

- `public-website/` contains the outbound worker used by the AnyKeyCafe guide
  and the localhost-only public retrieval service definition.
- `nomic-atlas/` contains the guarded public-memory export and upload tools.
  Generated JSONL and credentials are excluded from Git.
- `wordpress/anykey-little-oogway-atlas/` contains the source of the live Atlas
  section. Installable ZIP files are release artifacts and are not committed.
