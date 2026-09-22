---
name: verify-card-behavior
description: Prove a complete card through the current parser, converter and public game actions.
---

Write discriminating tests in the allowed new shape test file. Test-only work
is valid even when all underlying Engine capabilities already exist. Do not
change runtime code, parser code, corpus records, or expected Oracle behavior
to make a test pass. A failing behavioral test is evidence of an unfinished
card and must retain its failure receipt.

Load the named card from backend/data/carddb in the test's checkout and run
scripts/paragraph/reparse.py reparse_card against that actual definition.
Require eligible and no misses. Merge the returned abilities and keywords
(and other emitted definition fields) into the definition, then JSON-decode
into cards.CardDefinition and call ToGameCard. Never substitute handcrafted
abilities for the card under test. A test can invoke Python with os/exec from
backend/cards, setting cmd.Dir to ../.. and adding scripts/paragraph to
sys.path. Use a unique helper name in each new test file.

Exercise casting, attachment, blocking or public event delivery as appropriate,
then actual target selection and stack resolution. Assert every ability and
all the pinned checklist cases, including adjacent negative cases. Do not
skip cases, swallow errors, or regard a successful parse/private helper as
complete behavior. Run the exact named Go test, the package gates, and diff
checks. Request bounded source evidence when an API is unknown.
