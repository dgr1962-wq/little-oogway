#!/usr/bin/env bash
set -euo pipefail

root=/home/darren/Documents/Little-Oogway
set -a
source "$root/tokenspace/.env"
set +a
export TOKENSPACE_PASSWORD="$POSTGRES_PASSWORD"
exec "$root/oogway-core/.venv/bin/oogway-memory" worker --drain --batch-size 8 --threads 2
