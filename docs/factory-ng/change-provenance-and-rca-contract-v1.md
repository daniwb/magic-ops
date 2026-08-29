# Factory NG — Change Provenance and Root-Cause Contract v1

Status: proposed implementation contract, 2026-08-28  
Applies to: every Factory-authored change that is eligible for integration.

## Purpose

Factory NG must be able to answer, long after a change lands: **which ticket,
attempt, model profile, evidence, Skill, tests, and reviewer produced this
line of code?**  This makes later defects diagnosable without reducing the
answer to misleading blame such as “Qwen caused it.”

A model identifier establishes provenance.  A root-cause analysis establishes
causality.  They are related, but never interchangeable.

## Immutable attempt provenance

The harness writes the provenance record after gates and fresh review; a model
never writes or self-certifies it.  Every record has a content digest and is
stored with the Ticket Execution Bundle.

Required fields:

- Ticket ID, root mission IDs, graph parents, and change class;
- attempt ID; project/source revision; result commit and patch digest;
- exact resolved model, provider, **model-profile ID/version**, executable
  adapter version, invocation policy, and pinned Model Profile artifact digest;
- pinned evidence-bundle digest and Skill digest;
- raw token/cost/time telemetry; tool/NEED/repair counts;
- changed paths; baseline and post-change scope measurement;
- the complete, harness-attested execution receipt (including the gate set),
  bound to ticket, roots, attempt, source revision, result commit, patch,
  evidence, Skill, profile/model, telemetry, changed paths, and scope;
- a gate-set digest computed from that execution receipt, rather than a
  free-standing hash;
- a pinned acceptance-gate manifest naming every required gate ID and command
  digest. An accepted receipt must contain that **exact** set, with every gate
  passed; the immutable TicketSpec acceptance contract separately attests the
  manifest digest, so a hidden/holdout gate cannot be omitted from both the
  ticket and execution record;
- review decisions, reviewer model/profiles, review digests, and timestamps;
  and
- `contract_change_scope`: `none`, `amendment`, or `high_impact`.

For an accepted outcome, roots, result commit, normalized raw-counter fields,
changed paths, and both baseline/post-change scope measurements are mandatory
in the provenance record itself (not merely implied by a linked receipt).

Factory-contract records also name their `affected_contract_areas`. Changes to
cross-project identity, acceptance semantics, integration authority, or
token/cost accounting are mechanically classified `high_impact`; no producer
may downgrade them to a one-review amendment.

The canonical machine-readable shape is
[`schemas/factory.change-provenance-v1.schema.json`](schemas/factory.change-provenance-v1.schema.json).

## Commit trailers

Every Factory-created integration commit must preserve the following trailers.
They are written by the harness during commit creation, including after a
successful review; they are not supplied by the implementation model.

```text
Factory-Ticket: ticket:sha256:<ticket-id>
Factory-Roots: <root-id>[, <root-id>...]
Factory-Attempt: attempt:sha256:<attempt-id>
Factory-Change-Class: map|engine|handler|refactor|factory
Factory-Model-Profile: <profile-id>@<version>
Factory-Model: <provider>/<resolved-model>
Factory-Evidence: sha256:<bundle-digest>
Factory-Skill: sha256:<skill-digest>
Factory-Gates: sha256:<gate-receipt-set-digest>
Factory-Review: <accepted-review-id>
Factory-Provenance: sha256:<provenance-record-digest>
```

For a human-authored change, `Factory-Model-Profile` is `human@1` and
`Factory-Model` is `human`; the rest of the receipt remains required.  A merge commit may add
integration-specific trailers but must not erase the implementation trailers.

High-impact contract changes additionally carry both independently accepted
review IDs in `Factory-Review`; the provenance record is the authoritative
machine-readable proof that one is Sol and one is Opus.

Each high-impact approval has a distinct immutable `review_id`,
`review_attempt_id`, and review digest. The provenance relationship validator
rejects any reuse among accepted reviews, so two labels cannot be attached to
one review artifact. Every accepted Factory-contract reviewer attempt—whether
an amendment or high-impact change—must also differ from the producing
execution attempt, preserving fresh-context independence.

The digest binds a harness-written, Ed25519-attested
`factory.review-receipt/v1` containing the raw-review digest, review package
digest, profile, provider, resolved model, decision, and review attempt. Every
accepted review and every accepted provenance envelope must verify against the
operator-controlled harness trust root; a model cannot manufacture either
artifact. The validator checks Factory-contract reviewers against the closed
[`review-profiles/v1.json`](review-profiles/v1.json) registry. A label such as
`attacker-sol-review` is therefore not evidence of a Sol review.

Every Factory-contract provenance record pins one `reviewed_package_sha256`.
Each accepted review receipt must carry that exact digest, so Sol and Opus
cannot approve different or obsolete packages and have their approvals reused
for the current change.

The closed Sol/Opus review registry and package-match rule apply **only** when
`change_class` is `factory`. Map, Engine, Handler, and behavior-preserving
Refactor tickets use their TicketSpec/Skill/evidence/gate policy and may use a
compatible normal reviewer; their accepted review is still harness-attested,
but they do not inherit Factory-contract governance.

Every accepted review receipt also pins the digest of the execution receipt's
acceptance-gate manifest. This binds the review package to the same complete
ticket/evidence/Skill gate contract that the harness executed, rather than to a
selective list of passing results.

All content-address fields use the exact form `sha256:` followed by 64
lowercase hexadecimal characters; ticket, attempt, and review identities use
that same exact digest with their respective prefixes. The validators recompute
the digests for canonical artifacts present in the receipt (review receipts,
gate manifests, and gate-result sets) instead of trusting a declared label.
An accepted review additionally binds a validator-derived subject digest of
the ticket, attempt, source revision, patch, changed paths, evidence, Skill,
and the canonical digest of the complete harness-attested execution receipt.
It therefore cannot be replayed for a different patch or execution bundle.

The final accepted record contains only the accepted decision set for that
outcome. Earlier rejected review rounds are preserved as immutable linked
attempt history; they cannot be reinterpreted as approvals for a later patch.

## Root-cause analysis

An incident, regression, or unexpected scope result creates a linked
`reflection` ticket.  Its RCA must reference the exact provenance record and
classify the primary cause and contributing causes independently from the
model that authored the patch:

1. `product_semantics` — project behavior or prior implementation was wrong;
2. `ticket_contract` — required behavior, negative example, or scope was
   incomplete/incorrect;
3. `evidence_or_index` — the packet omitted or misranked decisive context;
4. `skill` — a binding Skill was incomplete, ambiguous, or wrong;
5. `model_profile` — a profile disregarded an explicit contract or selected an
   unjustified interpretation;
6. `harness_or_gate` — a mechanical check was missing, wrong, or bypassed;
7. `review` — the fresh review had enough evidence but failed to detect it;
8. `integration_or_environment` — merge, deploy, corpus, configuration, or
   runtime state changed the outcome.

`model_profile` is a permissible primary cause only with counterfactual
evidence: the TicketSpec and packet were sound, the defect was detectable by
the declared gate/review contract, and the model output violated or ignored
that contract.  Otherwise it is recorded as provenance or a contributor, not
as an unsupported attribution.

The RCA schema is
[`schemas/factory.root-cause-analysis-v1.schema.json`](schemas/factory.root-cause-analysis-v1.schema.json).
Every corrective action becomes a linked child ticket: contract amendment,
new evidence/index rule, Skill revision, gate, profile repair, code fix, or
explicitly accepted residual.

## Small refactor safety policy

Refactor tickets are behavior-preserving by default.  They must name one
coherent abstraction and carry a frozen before snapshot for every affected
Map/Engine scope member.  They may not combine cleanup with an unreviewed
semantic change; a discovered behavior defect becomes a separate child ticket.

Before production, a refactor requires:

1. path/scope and diff-size policy validation;
2. identical parser/DSL/runtime behavior on its declared snapshot;
3. relevant regression and holdout tests; and a mutation or discriminating
   test where the risk warrants one;
4. residual-scope remeasurement; and
5. the ordinary ticket review policy appropriate to that work's risk.

Refactor review is deliberately **not** restricted to Sol or Opus. Its safety
comes first from small scope, behavior snapshots, and deterministic gates. A
ticket's work profile may select an independent reviewer when warranted, but
that is separate from Factory-contract governance below.

## Factory-contract governance

A **contract change** changes how the factory defines, creates, routes,
accepts, records, reviews, integrates, or learns from work. It includes changes
to TicketSpec schemas, lifecycle/graph rules, Model Profile contracts, routing
or budget policy, Skills used as binding worker contracts, acceptance/gate
contracts, telemetry accounting, provenance/RCA schemas, and deployment
authority.

Every contract change must receive a thorough fresh-context review by **only**
a Sol or Opus review profile before it can be accepted. The review receives the
previous contract, proposed diff, affected fixtures/receipts, migration impact,
and counterexamples; it must explicitly decide whether the change preserves
the factory's ground-truth and safety properties. A reviewer cannot apply the
change, deploy it, mutate live tickets, or waive a failed deterministic check.

Changes that alter cross-project identity, acceptance semantics, integration
authority, or token/cost accounting require independent Sol **and** Opus
approval. Smaller contract amendments require one of them. Until this review
and the relevant schema/fixture tests pass, the amendment remains `proposed`
and has no production effect.

No change reaches production until its provenance record, reviews required by
its ticket or contract class, and all deterministic gates are accepted.

## Feedback loop

The daily reflection report aggregates defects by profile, work type, Skill,
evidence/index version, gate family, and reviewer—not only by model name.  A
repeated pattern may propose a versioned contract or profile amendment, but no
reflection auto-mutates a production contract or routing policy.
