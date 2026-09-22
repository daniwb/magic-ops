# Small Map qualification — 2026-09-21

Result: **2 of 3 historical Map tasks passed all original ticket gates**.
A separately recorded follow-up on the third task also failed. This is useful
bounded-task evidence, not qualification for unrestricted Map or Engine work.
The production worker remains disabled with its expired one-hour deadline.

| Task | Original attempt | Calls | Wall time | Pinned cards |
| --- | --- | ---: | ---: | --- |
| Gained-life static pump | Pass after one test-syntax correction | 2 | 20.6 s | 2 fully parsed |
| Drawn-two static keywords | Pass on first response | 1 | 106.5 s | 6 fully parsed |
| Graveyard thresholds | Failed pinned-card gate after protocol correction | 2 | 33.5 s | All 7 still unresolved |
| Graveyard follow-up with measured inputs | Failed tests; correction returned no answer | 2 | 12.0 s | Full-card gate not reached |

## Method

Three small historical parser-only tickets, each restricted to `reparse.py`
and one new test file. Their engine support already exists. Preflight cloned
each exact recorded source revision, checked preparation requirements and
confirmed genuine baseline misses: 2, 6 and 7 pinned cards respectively.
Frozen ticket files, behavior requirements, source revisions and original
gates were preserved. Every packet included the full exact
`parse_static_condition` function, supplementing the normal evidence packet.
The original trials used the same production Goose adapter and staged runner,
including the original one NEED/one correction limits, strict applier, scope
checks, named unit tests and complete pinned-card measurement.

`run.py` redirects all receipts/candidates to this benchmark directory, outside
Factory intake. Models have no tools or mutation authority. The harness used
isolated clones; no canonical edits, production admission, integration or
six-shard production run occurred. Accepted means original ticket gates passed,
not that patches were integrated. The two accepted patches were reviewed:
exact string matches with positive and adjacent-negative tests.

## Remaining failure and the evidence lesson

The graveyard task initially emitted malformed delimiters. Its one correction
applied, and its six generated unit tests passed, but those tests used the wrong
input form and even asserted additional thresholds that the ticket forbade.
The whole-card gate caught that all seven cards remained unresolved.

The historical ticket lacks relevant parser probes, so function source alone
was insufficient evidence of its caller inputs. A separate follow-up added
measured `parse_static_condition` calls while parsing all seven pinned cards
(see `graveyard-thresholds-handoff/measured-handoffs.txt`). It preserved every
original gate and requirement, rather than replacing the failed attempt.
The follow-up still put the new rule behind an earlier named-delirium return;
its own positive tests caught that precedence error. The one correction call
returned no usable answer. Neither attempt produced an accepted patch.

No further retries were made. The evidence supports further small, explicitly
bounded Map experiments only, with real parser input traces and whole-card
checks. Three cases from one parser function do not establish broad reliability.
The free-router alias is recorded; underlying selected-model identity is not
available here, so this is not a controlled model comparison.

## Artifacts and reproduction

- `preflight.json`: hashes, source revisions, actual baseline misses and packet sizes.
- `results.json`: original three-case outcomes and the separate follow-up.
- Each case directory: full packets, raw provider events, receipts and timing;
  successful cases also have candidate patches.
- `run.py --preflight`, then `run.py --case <name>`; the separate follow-up uses
  `--case graveyard-thresholds --handoffs`. Completed output directories are
  protected from accidental reuse; use a fresh benchmark directory for a new run.
- `summarize.py` regenerates the combined result from retained receipts.

Use `PYTHONPATH=/data/magic-stack/pydeps:scripts` from the operations repo for
these scripts. No worker activation is performed by the benchmark scripts.
