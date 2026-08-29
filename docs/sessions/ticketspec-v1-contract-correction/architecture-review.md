# TicketSpec v1 contract-correction architecture review

Reviewed: 2026-08-28  
Verdict: `ACCEPT`

The deterministic TicketSpec bundle is accepted as the entry contract for the
golden Map flow. The independent review reran the documented top-level pipeline,
inspected the implementation rather than relying on its report, added uncovered
scope and readiness attacks, and reran the complete pipeline successfully.
Stages 1–3 are complete; stages 4–7 may now begin under the pinned Map Skill.

## Independently verified

- compilation starts at `candidate`; only
  `compiler/readiness.py:evaluate` writes the final lifecycle;
- the evaluator now validates gate receipt schemas, command/output digests,
  expected exits, and the receipt-set digest before consuming `passed`;
- a forged passing receipt leaves lifecycle `candidate`;
- the current parser is rerun from the pinned Oracle snapshot and compared to
  the stored analyses, rather than comparing stored artifacts only;
- root-cause, sole-blocker, and predicted-whole-face-unlock sets are derived
  and cross-checked independently, including full member equality;
- zeroed or substituted scope, graph, evidence, projection, identity, policy,
  Skill, repository, Engine, gate, result, and manifest evidence is rejected;
- the session-local Go overlay test traverses the real target-player draw path,
  gives both players populated libraries, and proves target `+2`, controller
  `+0` without modifying the Engine repository;
- closed Draft 2020-12 schemas validate normative nested structures;
- the top-level pipeline completes two normative-identical runs, maintains one
  history identity, passes 37 adversarial assertions, writes the manifest last,
  and passes the separate manifest verifier;
- both previous TicketSpec prototype trees remain byte-identical;
- no model stage, Map patch, live ticket mutation, service change, deployment,
  branch push, or database mutation occurred during stages 1–3.

## Review corrections incorporated

Independent review found and repaired two gaps before acceptance:

1. the readiness evaluator previously read receipt result labels before their
   cryptographic/mechanical verification, relying on the later validator to
   reject forgery;
2. the validator did not rederive sole-blocker/unlock subsets or compare the
   evidence analyses to a fresh live-parser run from the pinned snapshot.

The repaired pipeline includes exact negative coverage for both conditions and
for semantic byte-count and subset-member mismatches.

## Entry verdict for the golden flow

Ticket `ticket:sha256:cd300ae084ecf9dcabc9db8cf82c89dc44ced93dae3a50a4d54c94192fb926e8`
is mechanically `ready`. Its immutable root-cause scope contains Comparative
Analysis and Inspiration. Only Inspiration is a sole blocker and predicted
whole-face unlock because Comparative Analysis also retains the independent
Surge gap.

Stages 4–7 must preserve the ticket identity and scope, use the pinned
`implement-map-class` Skill, modify no Engine path, execute every patch gate,
partition both original members exactly once, and record unavailable token
counters as unavailable rather than estimating them. Acceptance authorizes an
isolated, fully observed golden Map attempt; it does not authorize deployment
or live ticket mutation.
