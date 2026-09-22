# Python producer profiling — 2026-09-15

Read-only investigation, no production code or CPU policy changes. Measurements
ran at nice 10 on CPUs 12,19. Canonical source was clean after measurement.

- One build-plan history load: 6.577 CPU seconds, 6,275 production keys.
- Loading the corpus: about 2.03 CPU seconds, 16,768 review cards.
- Parser import: about 0.41 CPU seconds.
- Registry extraction: 0.267 Python CPU seconds, 1.139 wall seconds including its
  existing compiled Go helper. Python CPU time excludes helper CPU.
- Parser cold-path profiling found two additional full corpus loads for
  `subtype_vocab` and `subtype_is_land`. These tables are cached only per process.
- A uniformly spaced 60-review-card sample caused 677 regex compilations even
  on its second pass. Python's default pattern caches are smaller than the
  pattern set used by the parser and its card-name-dependent patterns.
- A separate, unprofiled comparison measured normal warm parsing at
  0.728–0.745 CPU seconds. An experimental bounded pattern cache took 0.542
  seconds to warm, then 0.133 seconds per identical pass (about 5.5x faster).
  All 60 outputs matched on every pass. This measures one sample's warm parser
  portion, not end-to-end throughput or equivalence over the whole corpus.

The experiment wraps a private Python regex hook only inside a disposable
process. It is not a production patch. Production work should prefer explicit
compiled-pattern reuse, preserve pattern/flag semantics, and validate corpus
output equivalence and bounded memory before adoption.

Other opportunities visible in source: build-plan producers reread all tickets
and corpus shards per invocation; parse-cache stamps contain the entire Git
revision, invalidating reuse on unrelated commits. A dependency fingerprint
would need parser modules, registry inputs and corpus-derived vocabularies, not
just reparse.py. Worker ticket publication and final gates must still validate
current source. Priorities: reuse regex patterns, retain compact indexes and
vocabularies, and share cached parsing across lanes with correct invalidation.
