#!/bin/bash
# fresh-review.sh — fresh-context reviewer (phase.rs adoption 2026-08-10).
# The reviewer sees ONLY the diff + the standards, never the conversation
# that produced the change ("do not review your own work in your own
# context"). SHADOW MODE for now: logs findings, never blocks. Intended
# integration point: integrator-lite.sh after a successful batch merge
# (run on the merged range, log-only), or manual: fresh-review.sh <range>.
set -u
RANGE="${1:-origin/main..HEAD}"
REPO="${REVIEW_REPO:-/opt/development/magic-new}"
LOG=/tmp/orch/review-shadow.log
MODEL="${REVIEW_MODEL:-sonnet}"
GATES=/opt/development/magic-ops/prompts/quality-gates.md

cd "$REPO" || exit 2
DIFF=$(git diff "$RANGE" -- ':!backend/data/carddb' 2>/dev/null | head -c 180000)
CARDS=$(git diff --stat "$RANGE" -- backend/data/carddb 2>/dev/null | tail -1)
[ -z "$DIFF" ] && { echo "$(date -Is) $RANGE: empty diff (carddb-only: $CARDS)" >>"$LOG"; exit 0; }

PROMPT_FILE=$(mktemp /tmp/orch/review-prompt.XXXXXX)
{
  echo "You are a fresh-context code reviewer for a Go MTG engine + Python parser."
  echo "You see ONLY this diff and the standards below — judge the diff on its own."
  echo "Checklist: (1) correct seam — is the change where the responsibility lives,"
  echo "or a symptom patch? (2) reuse — does it duplicate an existing helper/"
  echo "primitive (that is a defect even if it works)? (3) honest-miss discipline —"
  echo "does any change ship placeholder semantics (fixed amounts for dynamic"
  echo "counts, dropped conditions/durations, junk filter tokens)? (4) tests — is"
  echo "there a discriminating test that fails if the change is reverted (AST-shape"
  echo "assertions do not count)? (5) vocabulary — new effect strings registered,"
  echo "not grandfathered? Report format: one line 'REVIEW_VERDICT: CLEAN' or"
  echo "'REVIEW_VERDICT: FINDINGS' followed by findings as '- [HIGH|MED|LOW]"
  echo "<summary>. Evidence: <path:line>. Fix: <one line>'. Findings only — no"
  echo "praise, no recap."
  echo
  echo "=== STANDARDS ==="
  cat "$GATES"
  echo
  echo "=== DIFF ($RANGE; carddb changes summarized: $CARDS) ==="
  printf '%s\n' "$DIFF"
} > "$PROMPT_FILE"

OUT=$(timeout 600 claude -p --model "$MODEL" --permission-mode plan < "$PROMPT_FILE" 2>&1 | tail -c 8000)
rm -f "$PROMPT_FILE"
{
  echo "=== $(date -Is) range=$RANGE model=$MODEL ==="
  printf '%s\n' "$OUT"
} >> "$LOG"
printf '%s\n' "$OUT" | grep -q "REVIEW_VERDICT: FINDINGS" && exit 1 || exit 0
