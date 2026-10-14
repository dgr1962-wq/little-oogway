#!/usr/bin/env bash
set -euo pipefail

CORE_DIR="/home/darren/Documents/Little-Oogway/oogway-core"
TOKENSPACE_ENV="/home/darren/Documents/Little-Oogway/tokenspace/.env"

set -a
. "$TOKENSPACE_ENV"
set +a
export TOKENSPACE_PASSWORD="$POSTGRES_PASSWORD"

exec "$CORE_DIR/.venv/bin/oogway-memory" archive-absorb "$@"
