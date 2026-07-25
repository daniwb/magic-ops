#!/bin/bash
# Erzeugt eine kompakte ENGINE-REFERENZ aus den TATSÄCHLICH in echten cardfns-Handlern
# verwendeten game.-Symbolen (garantiert real) + Kern-Struct-Feldern + Methoden-Gotchas.
# Gibt Markdown auf stdout. 0 Modell-Token. Usage: engine-reference.sh <clone>
set -uo pipefail
CLONE="${1:-/tmp/work/ollama-shadow}"
G="$CLONE/backend/game"; CF="$CLONE/backend/cardfns"

# Alle game.<Exported>-Symbole aus echten Handlern (kein Test), nach Kategorie.
syms(){ grep -rhoE "\bgame\.$1[A-Za-z0-9]*" "$CF"/*.go 2>/dev/null | grep -v _test | sed 's/^game\.//' | sort -u; }
line(){ printf '%s\n' "$(syms "$1" | tr '\n' ' ')"; }

echo "=== ENGINE REFERENCE (exact names of engine constants/fields used by real handlers — use these EXACT spellings; a symbol not in the CATALOG or here does NOT exist → declare MISSING_PRIMITIVE) ==="
echo ""
echo "**Event constants** (subscribe via gs.EventBus.Subscribe(game.<Event>, ...)):"
line "Event"
echo ""
echo "**Counter types** (game.Counter…):"; line "Counter"
echo "**Target types** (game.Target…):"; line "Target"
echo "**Card types** (game.Type…):"; line "Type"
echo "**Keywords** (game.Keyword… / bare):"; grep -rhoE "\bgame\.(Keyword[A-Za-z]*|Flying|Vigilance|Trample|Haste|Menace|Deathtouch|Lifelink|FirstStrike|DoubleStrike|Reach|Hexproof|Indestructible)\b" "$CF"/*.go 2>/dev/null | grep -v _test | sed 's/^game\.//' | sort -u | tr '\n' ' '; echo
echo "**Colors** (game.…):"; grep -rhoE "\bgame\.(White|Blue|Black|Red|Green|Colorless)\b" "$CF"/*.go 2>/dev/null | sed 's/^game\.//' | sort -u | tr '\n' ' '; echo
echo ""
echo "**Key struct fields** (exact field names — NOTE: game.Player has NO ID field; player identity is the int index):"
for s in Card Player StackObject Event; do
  echo -n "  game.$s: "
  awk "/type $s struct/{f=1;next} f&&/^}/{f=0} f&&/^\t[A-Z]/{print \$1}" "$G"/*.go 2>/dev/null | sort -u | tr '\n' ' '
  echo ""
done
echo ""
echo "**Method gotchas** (real signatures — do NOT guess arg/return counts):"
grep -rhoE "func \([a-z]+ \*(GameState|Battlefield|Zone|Player|Card)\) (GetCard|GetCreatures|GetUntappedLands|DrawCards|CastSpell|HasCard|AddCard|Publish)[A-Za-z]*\([^)]*\)( \([^)]*\)| [A-Za-z\*\[\]]+)?" "$G"/*.go 2>/dev/null | sort -u | sed 's/^/  /' | head -20
