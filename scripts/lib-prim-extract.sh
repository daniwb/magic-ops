# lib-prim-extract.sh — robust primitive-name extraction from park replies.
# Order: explicit "PRIMITIVE:" line > snake_case token in REASON > hyphenated
# token in REASON > slug of REASON's first 4 words. The old bare-word grep
# ([a-z]{6,}) filled 55 blocked tickets with prims like "examples"/"handler"
# (2026-08-09) — names e1 can't build, so the harvest circle silently stalled.
extract_prim() { # $@ = reply file paths/globs; prints name or unnamed-primitive
  local line tok
  tok=$(command grep -ahoP '^PRIMITIVE:\s*\K[A-Za-z0-9_-]+' "$@" 2>/dev/null | tail -1 | tr 'A-Z' 'a-z')
  if [ -z "$tok" ]; then
    line=$(command grep -ahoP '^REASON:.*' "$@" 2>/dev/null | tail -1)
    tok=$(printf '%s' "$line" | command grep -oP '\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b' | head -1)
    [ -z "$tok" ] && tok=$(printf '%s' "$line" | command grep -oP '\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b' | head -1)
    [ -z "$tok" ] && tok=$(printf '%s' "$line" | sed 's/^REASON:[[:space:]]*//' \
      | tr -cs 'A-Za-z0-9' ' ' | tr 'A-Z' 'a-z' \
      | awk '{o=$1; for(i=2;i<=4&&i<=NF;i++)o=o"-"$i; print o}')
  fi
  printf '%s' "${tok:-unnamed-primitive}"
}
