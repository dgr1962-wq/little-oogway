#!/usr/bin/env bash
set -euo pipefail
root=/home/darren/Documents/Little-Oogway
set -a
source "$root/tokenspace/.env"
set +a
export TOKENSPACE_PASSWORD="$POSTGRES_PASSWORD"
export PYTHONPATH="$root/oogway-core/src:$root/roundtable/src"
exec "$root/oogway-core/.venv/bin/python" -m oogway_core.roundtable_api
