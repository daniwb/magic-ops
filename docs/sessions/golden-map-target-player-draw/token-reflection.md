# Token reflection

The four independent-review launches reported 1,048,258 input tokens, including 865,536 cached input tokens, plus 8,073 output tokens. The raw input total therefore crossed the 500,000 warning threshold. Cached input is a subset of input and is not added again.

The work remains necessary. The expensive review found a genuine production-boundary defect that all deterministic gates missed: the overlay constructed a target-bearing stack object directly, while the converter discarded the Map target. Stopping at the warning would preserve a false success.

Corrective action: split the discovered converter work into an Engine child ticket, add a test crossing DSL conversion and actual resolution, keep subsequent reviewer context limited to the two staged diffs and receipts, and never treat the warning as a hard stop.
