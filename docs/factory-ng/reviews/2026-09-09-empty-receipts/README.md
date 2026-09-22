# Empty dashboard source records repaired

The live `/factory-ng/data` endpoint reported three unreadable sources. All
three were zero-byte September 4 receipt artifacts: two Claude observations
and one integration. There was no JSON content to recover. The surviving
logs do not establish what originally interrupted or failed those writes.

The original artifacts were moved under `originals/` with the
`dispatcher-admin` scoped lock. [recovery.json](recovery.json) records their
original paths, modification times, byte counts and SHA-256 hashes. No current
job or other receipt referenced those paths. Later valid receipts for the
affected jobs remain in the normal history; provider logs remain untouched.
No outcomes or token counts were reconstructed, and no attempts were reset.

The receipt writers previously used `Path.write_text` on the final filename,
exposing empty or partial JSON when a write failed or was interrupted. Map,
remote Map/Engine, integration and source-wait receipts now share
`scripts/factory_ng_receipts.py`: serialize, write a sibling temporary file,
flush/fsync, then publish with an atomic hard link. A collision cannot replace
an immutable receipt. Integration filenames include a nanosecond suffix so
rapid retries preserve both receipts. In-flight processes may retain the old
writer until they finish; subsequent invocations load the updated code.

Validation:

- Three publication regressions pass: complete visibility, simulated disk-full
  failure leaving no final artifact, and refusal to overwrite an existing file.
- Nineteen reliability tests pass, including two integration passes in the
  same timestamp second that retain distinct receipts.
- Seven dashboard index tests pass; all changed Python modules compile.
- After index refresh, the live endpoint at `2026-09-09T14:29:51.076809Z`
  returned `invalid_files: []`. Counts were unchanged: 4,313 tickets, 5,209
  attempts, 663 accepted attempts, 564 integrations, 98 current problems.

No dashboard restart was needed. Canonical source was clean at startup and
owned by normal NG integration at the final health check. Separate existing
watchdog job/integration alerts remain outside this history-record repair.
