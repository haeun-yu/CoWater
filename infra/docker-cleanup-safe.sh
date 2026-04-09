#!/usr/bin/env bash
set -euo pipefail

printf 'Running safe Docker cleanup...\n'
docker builder prune -f
docker image prune -f

printf '\nPost-cleanup usage:\n'
docker system df
