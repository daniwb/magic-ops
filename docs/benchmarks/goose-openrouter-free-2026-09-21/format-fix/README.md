# Goose OpenRouter patch-response fixes — 2026-09-21

The Factory uses exact SEARCH/REPLACE blocks and NEWFILE blocks. The applier
and all original scope/source/test gates remain unchanged.

## Findings and changes

- Responses simulated XML/bash tool calls although no tools existed. The
  OpenRouter adapter now provides a system-level no-tools contract, worked
  patch example, and final reminder without removing any ticket evidence.
- Continuation/correction instructions now have an explicit harness-set phase;
  their system contract closes the NEED allowance rather than reoffering it.
- Unambiguous FILE blocks using `<<<<<<< SEARCH`, `=======` or `>>>REPLACE`
  receive marker-only normalization. Paths, source text and NEWFILE contents
  are preserved. Incomplete/ambiguous blocks remain rejected. Raw replies and
  every normalization are retained in the adapter artifact.
- Rate-limit detection previously scanned reasoning and could match a source
  line number such as 429. It now excludes reasoning and event metadata.
  Completion-budget exhaustion/truncation is classified before provider errors.
  Goose's explicit truncation signal also invalidates partial answers below
  the configured token ceiling. Model-call logs retain the failure reason.

Retrospective classification of all 24 original call artifacts finds four
completion-budget exhaustions and one reasoning-only answer. The original
rate-limit receipt was a false classification of budget exhaustion. Original
receipts were preserved; see `retrospective-classification.json`.

## Verification and limits

59 relevant regression tests pass, including original staged/repair tests,
exact/ambiguous/missing-source rejection after marker normalization and budget
classification. The changed profile validates.

`live-conformance.json`: a real free-router call produced an existing-file edit
and a new unittest file. The unchanged strict applier applied them and the test
passed. It reported 101 output tokens and zero cost.

`frozen-replay.json`: replayed the exact failed correction packet from the
13:25:32 Engine attempt. The new live response took 33.9 seconds and 11,886
output tokens, reporting zero cost. It still used `>>>REPLACE`; normalization
corrected four separators. The strict applier then rejected two FILE blocks
that lacked SEARCH/REPLACE structure (new content presented as existing-file
edits). This is not a successful Engine implementation, and no patch was
accepted, integrated or deployed. Application ran only in disposable clones
at the ticket's recorded source revision.

The production worker stays disabled with its expired trial deadline. These
fixes improve protocol handling, not proof of model coding quality. A further
qualification should start with small evidence-complete tasks before broad
Engine work. Higher token ceilings or fuzzy source matching would not repair
the demonstrated errors.
