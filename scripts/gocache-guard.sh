#!/usr/bin/env bash
# gocache-guard — the shared build cache hit 32G and ENOSPC'd the box twice
# (2026-08-05 + 08-06). Trim when >20G AND no build/test in flight.
# Cron: 40 * * * *
C=/opt/development/.gocache-magic
SZ=$(du -s "$C" 2>/dev/null | awk '{print int($1/1024/1024)}')
[ "${SZ:-0}" -lt 20 ] && exit 0
pgrep -f "go (build|test|vet)" >/dev/null && exit 0
GOCACHE="$C" go clean -cache 2>/dev/null
echo "[$(date -Is)] gocache was ${SZ}G — cleaned" >> /tmp/orch/gocache-guard.log
