# Open architecture questions

1. **UUID continuity gate.** This release proves UUID presence and uniqueness,
   not continuity. Which prior pinned releases should a longitudinal gate retain
   to measure UUID reuse, disappearance, and changed content under stable UUID?

2. **Token production policy.** The universal inventory includes all 9,072
   `tokens`-collection rows. Should the initial production projection include
   them, exclude them with a reason-coded membership decision, or expose a
   separate token projection? Collection provenance is more reliable than
   layout/type alone.

3. **Funny and memorabilia boundary.** Should a policy use card `isFunny`, set
   type, or both? The audit deliberately preserves both signals and does not
   select an exclusion rule.

4. **Semantic face naming.** Is the durable serialized value for absent side
   literally `none`, or should `oracle_face_id` carry a structured nullable
   component to avoid sentinel-string ambiguity?

5. **Projection vocabulary.** Should Dreamcast and Shandalar be members of a
   broad `digital` projection, or should each platform be a separate projection
   with `digital` only as a union view?

6. **Set/product granularity.** Which identifiers and finish variants must be
   materialized in the first inventory versus retained in a lossless raw-field
   envelope? `(setCode, number, language)` has 7,854 duplicate keys and cannot
   substitute for UUID.

7. **Upstream anomaly policy.** Referential checks are clean in this release.
   When a future snapshot has dangling or non-reciprocal relations, should it
   remain ingestible with an anomaly status, or fail snapshot publication?

8. **AtomicCards lifecycle.** How long should same-release AtomicCards
   compatibility fixtures remain a required regression gate after consumers
   migrate to AllPrintings identities?

9. **Large inventory storage.** Select the content-addressed/compressed store,
   retention window, recovery procedure, and descriptor URI scheme before a
   production generator emits the full universal inventory.

