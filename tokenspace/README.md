# TokenSpace v2 development foundation

Docker runs only the disposable development database. Ollama, NVIDIA inference, and Roundtable stay on the host. The live approximately 155 GB database, legacy schema/ingestion files, and valuable transcripts are preserved. No legacy import runs automatically.

The TokenSpace development container uses Docker's `unless-stopped` restart policy because it now backs the local Oogway and Open WebUI services. It returns automatically after a reboot unless it was deliberately stopped.

| Setting | Development value |
| --- | --- |
| Compose project | `little-oogway-tokenspace-dev` |
| Image | `pgvector/pgvector:0.8.7-pg16-trixie` |
| Endpoint | `127.0.0.1:55432` |
| Database / user | `tokenspace_v2_dev` / `tokenspace_dev` |
| Volume | `little-oogway-tokenspace-dev-data` |

No host database directory is mounted. Port 55432 differs from the conventional PostgreSQL port 5432. Docker refuses startup if occupied; do not stop another service to free it. Runtime inspection confirms the container publishes only `127.0.0.1:55432`. The tag pins pgvector and the PostgreSQL major version; patch releases within the tag can change.

## Install Docker

Ubuntu 24.04 repositories on this machine provide `docker.io` and `docker-compose-v2`. Run this single command in a host terminal:

```bash
bash /home/darren/Documents/Little-Oogway/tokenspace/scripts/install-docker-ubuntu.sh
```

The installer prompts for sudo, installs Engine and Compose, starts Docker, and prints versions. It checks for conflicting Docker CE packages and does not change repositories, upgrade the system, or grant Docker group membership. Docker is now installed, and the `darren` account belongs to the `docker` group. The upstream alternative is documented at https://docs.docker.com/engine/install/ubuntu/; do not mix package sources.

## Start, migrate, inspect

```bash
cd /home/darren/Documents/Little-Oogway
# Only if .env does not exist; replace placeholder password before starting:
cp -n tokenspace/.env.example tokenspace/.env
chmod 600 tokenspace/.env
sudo python3 tokenspace/scripts/dev.py start
sudo python3 tokenspace/scripts/dev.py migrate
sudo python3 tokenspace/scripts/dev.py migrate  # repeat must be a no-op
sudo python3 tokenspace/scripts/dev.py smoke
sudo python3 tokenspace/scripts/dev.py inspect
```

An ignored local `.env` with a generated password has been prepared; `.env.example` has only a placeholder. Host clients use the endpoint above and local password. Changing `.env` after initialization does not change the database role password.

The helper fixes the Compose project/file, service, database, and user. SQL executes inside the container through Compose, never via host PostgreSQL. Start waits for health. Inspect reports health, published port, PostgreSQL/pgvector versions, schemas/tables, and migration records. Smoke inserts and reads a complete conversation/memory chain, checks ordering, foreign keys, and nonempty memory text, then rolls back every test row.

## Stop and reset

```bash
sudo python3 tokenspace/scripts/dev.py stop
# DESTRUCTIVE: removes only this stack and little-oogway-tokenspace-dev-data.
sudo python3 tokenspace/scripts/dev.py reset --confirm-disposable-reset
sudo python3 tokenspace/scripts/dev.py start
sudo python3 tokenspace/scripts/dev.py migrate
```

Stop preserves data. Reset uses `compose down --volumes` for this fixed project; no external volume or host data mount is configured. Never use generic Docker prune commands for this workflow.

## Versioned schema

`migrations/0001_core.sql` creates model-neutral participants, conversations, numbered rounds, ordered turns with completed/failed/skipped statuses, provenance/metadata, and text memories linked to source turns. `0002_participant_identity.sql` adds stable participant identity keys, repoints existing duplicate participant references to their canonical rows, and makes future registration idempotent. `0003_memory_retrieval.sql` adds hashed memory sources, ordered retrieval-only chunks, generated English full-text search, and a separate 768-dimensional embedding table with an HNSW cosine index. `0004_memory_consolidation.sql` adds a reviewable relation ledger for exact duplicates, semantic candidates, and superseded memories. `0005_memory_preference.sql` records a preferred member and its selection reason without removing the alternate. `0006_ingestion_jobs.sql` adds active source versions and a durable, retryable ingestion queue. `0007_source_identity.sql` preserves distinct provenance when different source locations contain identical text. Consolidation relations never delete or rewrite source memories. Ordinals begin at zero. Unique constraints enforce ordering; foreign keys preserve relationships and prevent deletion of referenced records.

Embeddings remain separate from core memory text, keyed by the exact Ollama model digest. This permits later additive support for another embedding model without rewriting source text or provenance.

Name UTF-8 migrations `0001_description.sql`, `0002_description.sql`, etc. A session advisory lock serializes runs. Each migration and SHA-256 record commit together. Repeat runs skip matching migrations and reject edited applied files. Add new migrations instead of editing applied ones. Files must contain ordinary SQL without transaction control or psql meta-commands. Reset is the disposable development recovery path; no automatic downgrade is provided.

## Validation

```bash
python3 -m unittest discover -s tokenspace/tests -v
```

Five offline tests pass: checksum/lock/transaction generation, unsafe filename rejection, fixed SQL target, and reset guard/scope. Compose YAML parsing and image/port/volume isolation checks pass.

Runtime validation completed on October 13, 2026:

- Docker Engine 29.1.3 and Compose 2.40.3 can be used without sudo.
- The container is healthy and publishes only `127.0.0.1:55432`.
- The running database is `tokenspace_v2_dev`, using PostgreSQL 16.15 and pgvector 0.8.7.
- The database uses the named volume `little-oogway-tokenspace-dev-data` at `/var/lib/postgresql/data`; there is no host bind mount.
- Repeat migration runs completed successfully without duplicating records. The ledger contains `0001_core`, `0002_participant_identity`, and `0003_memory_retrieval`; checksums are visible through `dev.py inspect`.
- All core conversation and retrieval tables, indexes, and the migration ledger exist.
- The rollback-only smoke test verifies conversation readback, source provenance, generated full-text search, 768-dimensional vector storage, consolidation relations, ordering, foreign keys, and text constraints without leaving test rows. Intentional Core and memory validation populated application data in the isolated development database.

The helper invokes `psql` through the fixed Compose service and explicitly selects `tokenspace_v2_dev`; it has no host connection option. The Compose stack mounts only its named Docker volume and does not mount or target the live PostgreSQL installation.

Legacy files and logs remain historical material. The bulk corpus is outside this folder; transcripts remain in `../data/transcripts/`.
