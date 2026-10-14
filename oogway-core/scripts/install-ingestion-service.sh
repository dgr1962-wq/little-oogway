#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
ln -sfn "$root/oogway-core/systemd/oogway-ingest.service" "$unit_dir/oogway-ingest.service"
ln -sfn "$root/oogway-core/systemd/oogway-ingest.timer" "$unit_dir/oogway-ingest.timer"
systemctl --user daemon-reload
systemctl --user enable --now oogway-ingest.timer
systemctl --user status oogway-ingest.timer --no-pager
