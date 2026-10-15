#!/usr/bin/env bash
set -Eeuo pipefail

environment_dir="/home/darren/venvs/tokensense-qlora"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
private_root="/mnt/storage/tokensense"
requirements="$project_dir/configuration/requirements-lock.txt"

if [[ -e "$environment_dir" ]]; then
  echo "Refusing to replace existing environment: $environment_dir" >&2
  exit 2
fi

install -d -m 0700 \
  "$private_root" \
  "$private_root/configuration" \
  "$private_root/datasets" \
  "$private_root/datasets/incoming" \
  "$private_root/datasets/validated" \
  "$private_root/training" \
  "$private_root/evaluation" \
  "$private_root/adapters" \
  "$private_root/adapters/experimental" \
  "$private_root/adapters/validated" \
  "$private_root/adapters/production" \
  "$private_root/adapters/archived" \
  "$private_root/checkpoints" \
  "$private_root/experiments" \
  "$private_root/reports" \
  "$private_root/atlas" \
  "$private_root/models" \
  "$private_root/models/huggingface"
install -d -m 0755 "$(dirname "$environment_dir")"

python3 -m venv "$environment_dir"
"$environment_dir/bin/python" -m pip install --upgrade \
  pip==25.2 setuptools==80.9.0 wheel==0.45.1
"$environment_dir/bin/python" -m pip install \
  torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
  --index-url https://download.pytorch.org/whl/cu124
"$environment_dir/bin/python" -m pip install -r "$requirements"
"$environment_dir/bin/python" -m pip install --no-deps -e "$project_dir"
"$environment_dir/bin/python" -m pip check
"$environment_dir/bin/python" -m pip freeze | LC_ALL=C sort \
  > "$private_root/configuration/environment.freeze.txt"
cp "$requirements" "$private_root/configuration/requirements-lock.txt"
sha256sum "$private_root/configuration/"*.txt \
  > "$private_root/configuration/manifest.sha256"

echo "Environment ready: $environment_dir"
echo "Private workspace: $private_root"
