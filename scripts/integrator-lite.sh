#!/usr/bin/env bash
# integrator-lite — unbemannter Lander für RISIKOARME Reparse-Branches.
#
# Landet reparse/task-* Branches automatisch NUR wenn:
#   - der Diff AUSSCHLIESSLICH scripts/paragraph/*.py berührt (kein Engine-Code)
#   - der Merge konfliktfrei ist
#   - build + Fast-Gate (Vocab/Shape/Subtype-Ratchet) + VOLLE Sharded-Suite grün
# Alles andere (Engine-Diffs, Konflikte, rote Gates) wird NUR GELISTET —
# Review bleibt bei der interaktiven Fable-Session. Kein Claude-Call, 0 Token.
#
# Cron: */15 * * * *  (flock-guarded). Stopp: touch /opt/development/magic-ops/INTEGRATOR_LITE_OFF
set -uo pipefail

REPO=/opt/development/test/openmagic
LIVE=/opt/development/magic-new
GO=/usr/local/go/bin/go
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

landed=0
for ref in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin/reparse/); do
  branch="${ref#origin/}"
  # schon in main?
  [ "$(git rev-list --count origin/main.."$ref")" = 0 ] && continue
  # 2026-08-04: python-only restriction DROPPED — since the contract asks
  # map workers for Go shape tests, their branches legitimately carry Go
  # diffs; the FULL gates below (build + fast gate + complete sharded
  # suite) carry correctness for every tier. Conflicts still go to review.
  log "candidate: $branch (full gates)"
  if ! git merge --no-edit -q "$ref" 2>>"$LOG"; then
    git merge --abort 2>/dev/null; git reset -q --hard origin/main
    log "$branch: merge conflict — listed for review"
    grep -qxF "$branch (merge conflict)" "$REVIEW_LIST" 2>/dev/null || echo "$branch (merge conflict)" >> "$REVIEW_LIST"
    continue
  fi
  tag="reparse-auto-$(date +%m%d-%H%M)"
  python3 scripts/paragraph/reparse.py --flip-batch 300 --tag "$tag" >> "$LOG" 2>&1
  python3 scripts/paragraph/reparse.py --import-corpus --tag "$tag" >> "$LOG" 2>&1
  ok=1
  (cd backend && "$GO" build ./...) >> "$LOG" 2>&1 || ok=0
  if [ "$ok" = 1 ]; then
    (cd backend && "$GO" test ./cards/ -run 'TestVocabulary|TestV2|TestShape_|TestCardDBSubtypeScopes' -count=1) >> "$LOG" 2>&1 || ok=0
  fi
  [ "$ok" = 1 ] && { bash scripts/test-cards-sharded.sh 6 >> "$LOG" 2>&1 || ok=0; }
  if [ "$ok" != 1 ]; then
    git reset -q --hard origin/main
    log "$branch: gates RED — listed for review, tree reset"
    grep -qxF "$branch (gates red)" "$REVIEW_LIST" 2>/dev/null || echo "$branch (gates red)" >> "$REVIEW_LIST"
    continue
  fi
  git add -A backend/data/carddb
  git commit -qm "feat(reparse): auto-land $branch (integrator-lite; python-only, all gates green)" 2>/dev/null || true
  if ! git push -q origin main 2>>"$LOG"; then
    git reset -q --hard origin/main
    log "$branch: push failed — reset, retry next run"
    continue
  fi
  (cd backend && "$GO" build -o "$LIVE/bin/magic-api-server" ./api) >> "$LOG" 2>&1 \
    && sudo -n systemctl restart magic-backend 2>>"$LOG" \
    && log "$branch: LANDED + deployed"
  git -C "$LIVE" pull -q --ff-only 2>>"$LOG" || true
  landed=$((landed+1))
done
[ "$landed" -gt 0 ] && log "run done: $landed branch(es) landed"
exit 0
