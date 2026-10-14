#!/usr/bin/env bash
set -euo pipefail
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
  echo "This installer is scoped to Ubuntu 24.04." >&2
  exit 1
fi
for package in docker-ce docker-ce-cli containerd.io podman-docker; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    echo "Existing $package detected; inspect before changing packages." >&2
    exit 1
  fi
done
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl start docker
sudo docker version
sudo docker compose version
