#!/bin/bash
# Primitive-Builder gegen den v4-Dispatcher (statt Kanboard).
# Holt offene [VOCAB] von v4 /vocab-list, baut (bewiesenes 2-Lauf-Muster),
# Gate = eigene Tests, dann merge+push+deploy + v4 /vocab-close (requeued die
# blockierten Karten automatisch). Fehlschlag/Engine-Hook → v4 /vocab-fail.
set -uo pipefail

LOCK=/tmp/prim-builder-v4.lock
exec 9>"$LOCK"; flock -n 9 || { echo "already running"; exit 0; }

export PATH=/usr/local/go/bin:$PATH
[ "${GLM_WORKER:-0}" != "1" ] && unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

DISP="${DISP:-http://localhost:9999}"
CLONE="${CLONE:-/tmp/work/prim-builder}"
REPO_SSH="${REPO_SSH:-git@github.com:daniwb/openmagic.git}"
CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
LIVE_REPO="/opt/development/magic-new"
MAX_PRIMS="${MAX_PRIMS:-10}"
MODEL="${MODEL:-claude-sonnet-5}"
USAGE_LIMIT_PCT="${USAGE_LIMIT_PCT:-95}"

log() { printf '[%s] prim-v4: %s\n' "$(date -Is)" "$*"; }

# Peak-Gate (DeepSeek doppelte Kosten in Stoßzeiten): PEAK_PAUSE=1 aktiviert
peak_gate() {
  [ "${PEAK_PAUSE:-0}" = "1" ] || return 0
  local h; h=$(date -u +%H); h=$((10#$h))
  case " ${PEAK_HOURS:-1 2 3 6 7 8 9} " in *" $h "*) return 1;; esac
  return 0
}
peak_gate || { log "Peak-Stunde (UTC $(date -u +%H)) — Batch übersprungen"; exit 0; }

usage_ok() {
  [ "$USAGE_LIMIT_PCT" -le 0 ] 2>/dev/null && return 0
  local tok body u5 u7 lim5 nh
  tok=$(jq -r '.claudeAiOauth.accessToken // empty' "$HOME/.claude/.credentials.json" 2>/dev/null || true)
  [ -z "$tok" ] && return 0
  body=$(curl -fsS --max-time 15 -H "Authorization: Bearer $tok" -H "anthropic-beta: oauth-2025-04-20" \
    https://api.anthropic.com/api/oauth/usage 2>/dev/null) || return 0
  u5=$(printf '%s' "$body" | jq -r '.five_hour.utilization // 0 | floor'); u7=$(printf '%s' "$body" | jq -r '.seven_day.utilization // 0 | floor')
  lim5="$USAGE_LIMIT_PCT"; nh=$(TZ='Europe/Zurich' date +%H); nh=$((10#$nh))
  { [ "$nh" -ge 23 ] || [ "$nh" -lt 6 ]; } && lim5=100
  [ "$u5" -ge "$lim5" ] && { log "usage 5h=${u5}% — stop"; return 1; }
  [ "$u7" -ge "$USAGE_LIMIT_PCT" ] && { log "usage 7d=${u7}% — stop"; return 1; }
  return 0
}
usage_ok || exit 0

[ -d "$CLONE/.git" ] || GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git clone -q "$REPO_SSH" "$CLONE" || { log "clone failed"; exit 1; }
cd "$CLONE"; git config user.email prim-builder@magic; git config user.name prim-builder

# Offene VOCABs von v4 holen (nur nicht-gescheiterte, meiste-Karten-zuerst wäre schön,
# v4 liefert älteste-zuerst; nach blocked sortieren wir hier):
LIST=$(curl -fsS -m 30 "$DISP/vocab-list" 2>/dev/null || echo '[]')
COUNT=$(printf '%s' "$LIST" | jq 'length')
log "$COUNT offene [VOCAB] von v4"
[ "$COUNT" = 0 ] && exit 0

BUILT=0
# nach #blockierter Karten absteigend (größter Hebel zuerst)
printf '%s' "$LIST" | jq -c 'sort_by(-.blocked) | .[]' | while IFS= read -r V; do
  [ "$BUILT" -ge "$MAX_PRIMS" ] && break
  usage_ok || { log "usage-gate mitten im Batch — stop"; break; }
  VID=$(printf '%s' "$V" | jq -r '.id')
  TITLE=$(printf '%s' "$V" | jq -r '.title')
  DESC=$(printf '%s' "$V" | jq -r '.descr')
  BLK=$(printf '%s' "$V" | jq -r '.blocked')

  log "baue v4#$VID ($BLK Karten): $TITLE"
  curl -s "$DISP/vocab-claim?id=$VID&worker=$(printf '%s' "${BUILDER_ID:-prim}" | jq -sRr @uri)&model=$(printf '%s' "$MODEL" | jq -sRr @uri)" >/dev/null 2>&1 || true
  git checkout -q main && git fetch -q origin main && git reset -q --hard origin/main && git clean -qfd
  BR="prim/v4vocab-$VID"; git checkout -qB "$BR"

  P1=/tmp/primv4-$VID-p1.txt
  { cat scripts/skills/build-engine-primitive.md
    echo ""; echo "=== DEMAND: $TITLE ==="; printf '%s\n' "$DESC"
    echo ""; echo "=== RULES ==="
    echo "- STEP 0 (MANDATORY, do this FIRST): grep backend/cardfns/ and backend/game/ for an EXISTING primitive/field/method that already provides THIS capability (the demand often uses different words than the real symbol name — e.g. 'roll a d20' → RollDie, 'becomes-blocked event' → OnBecomesBlocked). If one GENUINELY covers the need — right filter, scope, and duration, not merely a related function — print exactly one line 'ALREADY_EXISTS: <exact func or field name>' and STOP without building. Be STRICT: an unfiltered version when the card needs a filtered one, or a one-kind version when it needs all-kinds, does NOT count — build in that case. When in doubt, build."
    echo "- Full checkout, branch $BR. Explore backend/game+cardfns allowed."
    echo "- NEVER push. Additive-first (new backend/cardfns/lib_*.go). Real engine hook in backend/game/ only if unavoidable and CERTAIN safe, else print ENGINE_HOOK_NEEDED: <slug> | <what> and STOP."
    echo "- Do NOT run full suites; iterate with focused -run tests."
  } > "$P1"
  OUT1=$(timeout 2400 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 100 < "$P1" 2>>/tmp/primv4-claude.err || echo TIMEOUT)

  if printf '%s' "$OUT1" | grep -q "^ENGINE_HOOK_NEEDED:"; then
    HOOK=$(printf '%s' "$OUT1" | grep "^ENGINE_HOOK_NEEDED:" | head -1)
    log "v4#$VID engine-hook nötig"
    curl -s "$DISP/vocab-fail?id=$VID&reason=$(printf '%s' "engine-hook: $HOOK" | jq -sRr @uri)" >/dev/null
    continue
  fi

  # Bereits-vorhanden: Sonnet meldet ein existierendes Primitiv. KONSERVATIVES
  # Sicherheitsnetz — die genannte Funktion/Feld MUSS wirklich im Code stehen,
  # sonst wird gebaut (verhindert Halluzinieren-um-Arbeit-zu-sparen und
  # fälschliches Schließen echt-fehlender VOCABs = Kartenverlust).
  if printf '%s' "$OUT1" | grep -q "^ALREADY_EXISTS:"; then
    EXFN=$(printf '%s' "$OUT1" | grep "^ALREADY_EXISTS:" | head -1 | sed 's/^ALREADY_EXISTS: *//' | tr -d '`()' | awk '{print $1}')
    if [ -n "$EXFN" ] && grep -rqE "func +$EXFN\b|^[[:space:]]*$EXFN[[:space:]]+[A-Za-z\[]" "$CLONE/backend/cardfns/" "$CLONE/backend/game/" 2>/dev/null; then
      log "v4#$VID bereits vorhanden ($EXFN) — schließe statt bauen"
      curl -s "$DISP/vocab-close?id=$VID" >/dev/null
      continue
    fi
    log "v4#$VID: ALREADY_EXISTS '$EXFN' NICHT im Code verifizierbar — baue trotzdem"
  fi

  P2=/tmp/primv4-$VID-p2.txt
  { echo "Continue on branch $BR. Ensure ONE focused behavioral test (backend/cardfns/..._test.go, core + worst edge). Iterate: cd backend && /usr/local/go/bin/go test ./cardfns/ -run '<Names>' -count=1. Add primitive to scripts/skills/primitive-catalog.md (signature + [dur:]). git add+commit. NEVER push. Final: BUILT: <slug> or FAILED: <reason>."
  } > "$P2"
  timeout 1800 "$CLAUDE_BIN" -p --model "$MODEL" --permission-mode bypassPermissions --max-turns 60 < "$P2" >>/tmp/primv4-claude.err 2>&1 || true
  [ -n "$(git status --porcelain)" ] && { git add -A; git commit -qm "feat(primitive): $TITLE (v4 builder)" || true; }

  NEW_TESTS=$(git diff main --name-only | grep '_test\.go$' || true)
  if [ -z "$NEW_TESTS" ]; then
    log "v4#$VID: kein Test — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=no-test" >/dev/null; continue
  fi
  TESTS=$(cat $NEW_TESTS 2>/dev/null | sed -n 's/^func \(Test[A-Za-z0-9_]*\).*/\1/p' | sort -u | paste -sd'|')
  if ! (cd backend && timeout 300 /usr/local/go/bin/go build ./... >/dev/null 2>&1 \
     && timeout 300 /usr/local/go/bin/go test ./cardfns/ -run "^($TESTS)$" -count=1 >/tmp/primv4-$VID-gate.log 2>&1); then
    log "v4#$VID: Gate rot — fail"; curl -s "$DISP/vocab-fail?id=$VID&reason=gate-red" >/dev/null; continue
  fi

  git checkout -q main && git pull -q --no-rebase origin main
  if ! git merge -q --no-ff "$BR" -m "feat(primitive): $TITLE (v4 builder, vocab #$VID)"; then
    git merge --abort 2>/dev/null || true; curl -s "$DISP/vocab-fail?id=$VID&reason=merge-conflict" >/dev/null; continue
  fi
  PUSHED=0; for i in 1 2 3; do git push -q origin main 2>/dev/null && { PUSHED=1; break; }; git pull -q --no-rebase origin main || true; done
  [ "$PUSHED" != 1 ] && { curl -s "$DISP/vocab-fail?id=$VID&reason=push-failed" >/dev/null; continue; }

  SHA=$(git rev-parse --short HEAD)
  log "v4#$VID gebaut+gemerged ($SHA) → vocab-close (requeued $BLK Karten)"
  curl -s "$DISP/vocab-close?id=$VID" >/dev/null
  BUILT=$((BUILT+1))
done

# Deploy + Regression einmal am Ende (nur wenn was gebaut wurde)
if [ -n "$(git -C "$CLONE" log --oneline --since='30 minutes ago' origin/main 2>/dev/null | grep 'v4 builder' || true)" ]; then
  git -C "$CLONE" checkout -q main && git -C "$CLONE" pull -q --no-rebase origin main || true
  (cd "$CLONE/backend" && timeout 590 /usr/local/go/bin/go build -o "$LIVE_REPO/bin/magic-api-server" ./api) \
    && sudo -n systemctl restart magic-backend magic-frontend 2>/dev/null && log "deployed" || log "deploy skipped/failed"
  /opt/development/magic-new/scripts/kanboard-regression-check.sh >> /opt/development/magic-new/.bugfixer-logs/regression-cron.log 2>&1 || true
  log "Regression: $(cat /opt/development/magic-new/.bugfixer-logs/regression-status.txt 2>/dev/null || echo '?')"
fi
log "Batch fertig"
