#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
docker info >/dev/null
docker compose version >/dev/null
[[ -f .env ]] || { echo 'Copy .env.example to .env and set FUSION_PASSWORD.' >&2; exit 1; }
password=$(sed -n 's/^FUSION_PASSWORD=//p' .env | tail -n1)
[[ -n "$password" && "$password" != CHANGE_ME ]] || { echo 'Set FUSION_PASSWORD in .env.' >&2; exit 1; }
args=(-f compose.yaml)
# Docker GPU access is selected independently of Fusion's automatic GLX backend.
# 0/cpu: no GPU; 1/dri: direct /dev/dri; nvidia: NVIDIA Container Toolkit.
case "${FUSION_GPU:-0}" in
  0|cpu|none) ;;
  1|dri)
    [[ -d /dev/dri ]] || { echo '/dev/dri is absent; cannot enable direct DRM GPU access.' >&2; exit 1; }
    args+=(-f compose.gpu.yaml)
    ;;
  nvidia|toolkit)
    args+=(-f compose.nvidia.yaml)
    ;;
  *) echo 'FUSION_GPU must be 0, cpu, 1, dri, nvidia, or toolkit.' >&2; exit 2 ;;
esac
docker compose "${args[@]}" config --quiet
docker compose --progress plain "${args[@]}" build 2>&1 | tee build.log
docker compose "${args[@]}" up -d --no-build
web_port=$(sed -n 's/^WEB_PORT=//p' .env | tail -n1)
web_port=${web_port:-3081}
echo "Open https://SERVER:${web_port}; username: fusion"
