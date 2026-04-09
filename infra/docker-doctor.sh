#!/usr/bin/env bash
set -euo pipefail

printf '== Filesystem ==\n'
df -h

printf '\n== Docker disk usage ==\n'
docker system df

printf '\n== Container status ==\n'
docker ps -a --format '{{.Names}}\t{{.Status}}'
