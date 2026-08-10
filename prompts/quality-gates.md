# QUALITY GATES (phase.rs adoption, 2026-08-10 — mandatory, all lanes)

GATE 1 — VERIFY THE PREMISE. Before building or fixing anything for a card,
read that card's record "text" field in backend/data/carddb/<letter>.json and
treat THAT as the oracle text. Never work from the ticket's paraphrase or
from memory. If the ticket contradicts the record text, follow the record
and note the discrepancy in your output. (Reviews verify execution against a
premise — they cannot catch a fabricated premise. Only this gate can.)

GATE 2 — EXISTENCE CHECK before ANY new primitive/executor/emitter case.
Run the 5-grep protocol and print the result line:
  1. grep corpus/primitive-inventory.json for the concept AND its synonyms
     (if the file is missing: python3 scripts/primitive_inventory.py)
  2. grep backend/cards/registry*.go   (regEffect calls + the frozen literal)
  3. grep backend/cards/registry_grandfather.go
  4. grep 'case "' backend/game/ability_effects.go backend/cards/converter.go
  5. grep scripts/skills/primitive-catalog.md
If ANY hit shows the capability already exists — same name, different name,
or as a parameter of an existing primitive — USE it and cite file:line. Do
NOT build a duplicate. If the inventory shows a sibling cluster for your
name root (X/X_all/X_self/X_target...), parameterize the existing primitive
instead of adding a sibling. Print exactly one line:
  EXISTENCE_CHECK: <file:line of what you will reuse | none — building new>

GATE 3 — HONEST MISS over silently wrong. If a clause cannot be represented
with existing vocabulary, leave the honest miss (park / MISSING_PRIMITIVE
per your lane's rules). NEVER ship placeholders: no fixed amount:1 for a
dynamic count, no junk filter tokens, no dropped condition/duration/
optionality. A shipped record represents the printed semantics fully, or it
does not ship.

GATE 4 — DISCRIMINATING TEST. Every new executor/primitive needs at least
one test that drives the REAL pipeline (ActivateAbility / ResolveTopOfStack
/ cast flow) and FAILS if your change is reverted. AST-shape assertions
alone do not satisfy this.
