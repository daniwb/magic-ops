#!/usr/bin/env bash
# integrator-lite — unbemannter Lander für Reparse-Branches.
#
# BATCH-MODUS (Dani, 2026-08-04): ALLE konfliktfreien Branches zusammen
# mergen, EIN flip/import-Wave, EIN Gate-Lauf (build + Fast-Gate + volle
# Sharded-Suite), EIN Deploy — statt ~10 min Suite pro Branch. Ist das
# Batch-Gate rot, Fallback auf per-Branch-Landung zur Isolation des
# Verursachers (das alte Verhalten ist der Bisektionspfad, nicht der
# Default). Konflikte gehen weiterhin einzeln auf die Review-Liste.
#
# Cron: */15 * * * *  (flock-guarded). Stopp: touch /opt/development/magic-ops/INTEGRATOR_LITE_OFF
set -uo pipefail

REPO=/opt/development/test/openmagic
LIVE=/opt/development/magic-new
GO=/usr/local/go/bin/go
# cron PATH lacks go — test-cards-sharded.sh calls bare `go` (cardfns gate step
# 2026-08-04); without this every suite run dies "go: command not found".
export PATH="/usr/local/go/bin:$PATH"
LOG="$LIVE/.bugfixer-logs/integrator-lite.log"
REVIEW_LIST="$LIVE/.bugfixer-logs/integrator-needs-review.txt"
LOCK=/tmp/integrator-lite.lock
OFF=/opt/development/magic-ops/INTEGRATOR_LITE_OFF

exec 9>"$LOCK"; flock -n 9 || exit 0
[ -f "$OFF" ] && exit 0
log() { printf '[%s] %s\n' "$(date -Is)" "$*" >> "$LOG"; }

cd "$REPO" || exit 1
# Nie auf schmutzigem/mid-merge Baum arbeiten (interaktive Session hat Vorrang)
[ -n "$(git status --porcelain | grep -v '^??')" ] && { log "tree dirty — skip run"; exit 0; }
git fetch -q origin 'refs/heads/main:refs/remotes/origin/main' 'refs/heads/reparse/*:refs/remotes/origin/reparse/*' 2>/dev/null || { log "fetch failed"; exit 0; }
git merge -q --ff-only origin/main 2>/dev/null || { log "local main not ff-able — skip"; exit 0; }

candidates() {
  git for-each-ref --format='%(refname:short)' refs/remotes/origin/reparse/ | while read -r ref; do
    [ "$(git rev-list --count origin/main.."$ref")" = 0 ] && continue
    echo "$ref"
  done
}

run_gates() { # one wave + full gates over the CURRENT tree; returns 0 on green
  local tag="reparse-auto-$(date +%m%d-%H%M)"
  python3 scripts/paragraph/reparse.py --flip-batch 300 --tag "$tag" >> "$LOG" 2>&1
  python3 scripts/paragraph/reparse.py --import-corpus --tag "$tag" >> "$LOG" 2>&1
  (cd backend && "$GO" build ./...) >> "$LOG" 2>&1 || return 1
  (cd backend && "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1) >> "$LOG" 2>&1 || return 1
  bash scripts/test-cards-sharded.sh 6 >> "$LOG" 2>&1 || return 1
  return 0
}

push_deploy() { # $1 = commit message
  git add -A backend/data/carddb
  git commit -qm "$1" 2>/dev/null || true
  if ! git push -q origin main 2>>"$LOG"; then
    git reset -q --hard origin/main
    log "push failed — reset, retry next run"
    return 1
  fi
  (cd backend && "$GO" build -o "$LIVE/bin/magic-api-server" ./api) >> "$LOG" 2>&1 \
    && sudo -n systemctl restart magic-backend 2>>"$LOG"
  # $LIVE is a pure mirror of origin/main (deploy binary is built from $REPO
  # above, independent of this) — it should never carry local edits of its
  # own. Discard any drift before pulling: found 2026-08-11/12 that
  # corpus/build-plan.jsonl/.md repeatedly went dirty in $LIVE (source
  # unconfirmed) and silently blocked --ff-only on every single cycle
  # (`|| true` swallowed it), letting $LIVE fall up to 30 commits behind
  # with no error surfaced. See memory: integrator_lite_live_pull_silent_fail.
  git -C "$LIVE" checkout -q -- . 2>>"$LOG"
  git -C "$LIVE" pull -q --ff-only 2>>"$LOG" || true
  # Keep the FTS5 knowledge service (:4103, used by map/engine/handler
  # pre-seeds) in step with what just landed — it only rebuilds at process
  # start or on this call, otherwise newly-landed primitives/handlers are
  # invisible to /find and /similar (found stale 2026-08-10: 3 days behind,
  # 10 primitives missing). Fire-and-forget, fail-open: never block a deploy.
  curl -s -m 10 http://127.0.0.1:4103/reindex >/dev/null 2>&1 &
  return 0
}

# ---- Phase 1: batch — alle konfliktfreien Branches zusammen mergen ----
merged=()
for ref in $(candidates); do
  branch="${ref#origin/}"
  if git merge --no-edit -q "$ref" 2>>"$LOG"; then
    merged+=("$branch")
  else
    git merge --abort 2>/dev/null
    log "$branch: merge conflict — listed for review"
    grep -qxF "$branch (merge conflict)" "$REVIEW_LIST" 2>/dev/null || echo "$branch (merge conflict)" >> "$REVIEW_LIST"
  fi
done
[ "${#merged[@]}" = 0 ] && exit 0

log "batch candidate: ${#merged[@]} branch(es): ${merged[*]} (one wave, one gate run)"
if run_gates; then
  if push_deploy "feat(reparse): auto-land batch of ${#merged[@]} (integrator-lite batch; all gates green): ${merged[*]}"; then
    log "batch: ${#merged[@]} branch(es) LANDED + deployed in one gate run"
  fi
  exit 0
fi

# ---- Phase 2: Batch-Gate rot — per-Branch-Bisektion (altes Verhalten) ----
git reset -q --hard origin/main
log "batch gate RED — falling back to per-branch isolation"
landed=0
for ref in $(candidates); do
  branch="${ref#origin/}"
  log "candidate: $branch (full gates, isolation mode)"
  if ! git merge --no-edit -q "$ref" 2>>"$LOG"; then
    git merge --abort 2>/dev/null; git reset -q --hard origin/main
    log "$branch: merge conflict — listed for review"
    grep -qxF "$branch (merge conflict)" "$REVIEW_LIST" 2>/dev/null || echo "$branch (merge conflict)" >> "$REVIEW_LIST"
    continue
  fi
  if ! run_gates; then
    git reset -q --hard origin/main
    log "$branch: gates RED — listed for review, tree reset"
    grep -qxF "$branch (gates red)" "$REVIEW_LIST" 2>/dev/null || echo "$branch (gates red)" >> "$REVIEW_LIST"
    continue
  fi
  push_deploy "feat(reparse): auto-land $branch (integrator-lite; all gates green)" || continue
  log "$branch: LANDED + deployed"
  landed=$((landed+1))
done
[ "$landed" -gt 0 ] && log "isolation run done: $landed branch(es) landed"
exit 0
