#!/usr/bin/env bash
set -euo pipefail

root=/home/darren/Documents/Little-Oogway
set -a
. "$root/tokenspace/.env"
set +a
export TOKENSPACE_PASSWORD="$POSTGRES_PASSWORD"

exec "$root/oogway-core/.venv/bin/python" -m oogway_core.operator_api

