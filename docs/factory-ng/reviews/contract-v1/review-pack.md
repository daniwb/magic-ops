# Factory NG Contract Review v1

You are an independent fresh-context reviewer. You must not edit files, run
commands, deploy, mutate tickets, or waive a failed deterministic gate. Review
only the hash-pinned proposed contracts below.

## Review decision

Return this exact structure in plain text:

```text
REVIEW_DECISION: ACCEPT|REJECT
RISK_CLASS: normal|high-impact
SUMMARY: <at most 120 words>
FINDING: <none, or severity|file|concrete problem|why it violates contract>
REQUIRED_CHANGE: <none, or concrete contract/fixture change>
COUNTEREXAMPLE: <none, or an input/sequence that demonstrates the issue>
```

`ACCEPT` is allowed only when all conditions below hold. A `REJECT` must name
an actionable, evidence-based contract defect; do not reject merely because the
implementation has not been built yet.

## Required safety properties

1. The Factory, never an implementation model, owns mission, scope,
   acceptance, patch application, gates, and integration authority.
2. A model profile may differ by executable, context renderer, tools, and
   repair policy but cannot broaden a Ticket's authority.
3. Raw token counters are retained separately; unknown is not silently zero;
   200k/500k are warning/reflection controls, not automatic cancellation.
4. Provenance identifies the producing attempt/profile but RCA does not blame a
   model without counterfactual evidence.
5. Commit trailers and immutable receipts cannot be model self-certification.
6. Refactor tickets remain small and behavior-preserving; Sol/Opus-only review
   applies to Factory-contract changes, not ordinary refactor tickets.
7. Contract amendments remain proposed until the required Sol/Opus review and
   schema/fixture checks pass; nothing in this proposal mutates production.
8. Since these documents affect acceptance, telemetry, provenance, and
   integration authority, classify this package `high-impact` and review it as
   an independent governance change.

## Fixtures / counterexamples to test mentally

- A Qwen-produced patch passes a visible test but fails a hidden holdout: RCA
  must permit `harness_or_gate` as primary cause, not automatically Qwen.
- A Claude response claims `GATE GREEN`: it must not create accepted trailers;
  only the harness after recorded gates/review may do so.
- A 510k-token Engine attempt is necessary and passes gates: it must create a
  warning/reflection checkpoint, not lose its work automatically.
- A cosmetic refactor is safe through behavior snapshots/gates; it must not be
  blocked merely because its reviewer is not Sol/Opus.
- A change to token-accounting semantics must require independent Sol and Opus
  approval before it becomes live.

## Hash-pinned contract contents

Package digest: `sha256:554c81066c7405dc4269d7bf4b2cf8f78e776b425f9b57ac2072615658db6db4`


--- FILE: scripts/factory-ng-contract-review-pack.py (sha256:d3bf0bcb5a81928a6244e3a998e608a0b11496e6c75a1b582dc8d758177524f8) ---
#!/usr/bin/env python3
"""Build a self-contained, hash-pinned Factory NG contract review package."""
import argparse
import hashlib
import json
import pathlib


OPS = pathlib.Path('/opt/development/magic-ops')
CONTRACT_FILES = [
    'scripts/factory-ng-contract-review-pack.py',
    'docs/factory-ng/model-profile-contract-v1.md',
    'docs/factory-ng/change-provenance-and-rca-contract-v1.md',
    'docs/factory-ng/schemas/factory.change-provenance-v1.schema.json',
    'docs/factory-ng/schemas/factory.root-cause-analysis-v1.schema.json',
    'docs/factory-ng/schemas/factory.model-profile-v1.schema.json',
    'docs/factory-ng/schemas/factory.execution-receipt-v1.schema.json',
    'docs/factory-ng/review-profiles/v1.json',
    'docs/factory-ng/review-attestation-keys/v1.json',
    'docs/factory-ng/review-attestation-keys/factory-harness-review-v1.pub.pem',
    'docs/factory-ng/fixtures/contract-review/valid-rca-model-profile.json',
    'docs/factory-ng/fixtures/contract-review/invalid-rca-model-profile-no-counterfactual.json',
    'docs/factory-ng/fixtures/contract-review/valid-provenance-high-impact.json',
    'docs/factory-ng/fixtures/contract-review/valid-provenance-refactor-qwen-review.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-contract-path-evasion.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-one-review.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-combined-reviewer.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-duplicate-review.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-amendment-wrong-reviewer.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-misclassified-token-accounting.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-package-mismatch.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-accepted-missing-complete-evidence.json',
    'docs/factory-ng/fixtures/contract-review/invalid-child-profile-authority-override.json',
    'docs/factory-ng/fixtures/contract-review/invalid-profile-no-extends-authority.json',
    'docs/factory-ng/fixtures/contract-review/invalid-child-profile-tool-escalation.json',
    'docs/factory-ng/fixtures/contract-review/valid-child-profile-readonly-tools.json',
    'docs/factory-ng/fixtures/contract-review/valid-execution-receipt.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-short-digest.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-nonhex-digest.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-trailing-digest.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-content-mismatched-gate-command.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-accepted-without-harness-evidence.json',
    'docs/factory-ng/fixtures/contract-review/valid-execution-receipt-over-threshold.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-over-threshold-no-reflection.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-mismatched-call-aggregate.json',
    'docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-partial-unavailable-aggregate.json',
    'docs/factory-ng/fixtures/contract-review/invalid-provenance-review-subject-replay.json',
    'scripts/test_factory_ng_contracts.py',
    'scripts/factory-ng-profile-validate.py',
    'scripts/factory-ng-provenance-validate.py',
    'scripts/factory-ng-receipt-validate.py',
    'docs/factory-ng/model-profiles/v1/staged-baseline.json',
    'docs/factory-ng/model-profiles/v1/qwen-prepared-local.json',
    'docs/factory-ng/model-profiles/v1/qwen-prepared-direct.json',
    'docs/factory-ng/model-profiles/v1/codex-constrained.json',
    'docs/factory-ng/model-profiles/v1/claude-staged.json',
]

PROMPT_HEAD = '''# Factory NG Contract Review v1

You are an independent fresh-context reviewer. You must not edit files, run
commands, deploy, mutate tickets, or waive a failed deterministic gate. Review
only the hash-pinned proposed contracts below.

## Review decision

Return this exact structure in plain text:

```text
REVIEW_DECISION: ACCEPT|REJECT
RISK_CLASS: normal|high-impact
SUMMARY: <at most 120 words>
FINDING: <none, or severity|file|concrete problem|why it violates contract>
REQUIRED_CHANGE: <none, or concrete contract/fixture change>
COUNTEREXAMPLE: <none, or an input/sequence that demonstrates the issue>
```

`ACCEPT` is allowed only when all conditions below hold. A `REJECT` must name
an actionable, evidence-based contract defect; do not reject merely because the
implementation has not been built yet.

## Required safety properties

1. The Factory, never an implementation model, owns mission, scope,
   acceptance, patch application, gates, and integration authority.
2. A model profile may differ by executable, context renderer, tools, and
   repair policy but cannot broaden a Ticket's authority.
3. Raw token counters are retained separately; unknown is not silently zero;
   200k/500k are warning/reflection controls, not automatic cancellation.
4. Provenance identifies the producing attempt/profile but RCA does not blame a
   model without counterfactual evidence.
5. Commit trailers and immutable receipts cannot be model self-certification.
6. Refactor tickets remain small and behavior-preserving; Sol/Opus-only review
   applies to Factory-contract changes, not ordinary refactor tickets.
7. Contract amendments remain proposed until the required Sol/Opus review and
   schema/fixture checks pass; nothing in this proposal mutates production.
8. Since these documents affect acceptance, telemetry, provenance, and
   integration authority, classify this package `high-impact` and review it as
   an independent governance change.

## Fixtures / counterexamples to test mentally

- A Qwen-produced patch passes a visible test but fails a hidden holdout: RCA
  must permit `harness_or_gate` as primary cause, not automatically Qwen.
- A Claude response claims `GATE GREEN`: it must not create accepted trailers;
  only the harness after recorded gates/review may do so.
- A 510k-token Engine attempt is necessary and passes gates: it must create a
  warning/reflection checkpoint, not lose its work automatically.
- A cosmetic refactor is safe through behavior snapshots/gates; it must not be
  blocked merely because its reviewer is not Sol/Opus.
- A change to token-accounting semantics must require independent Sol and Opus
  approval before it becomes live.

## Hash-pinned contract contents
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # The review gate loads the complete fixture directory.  Derive that part
    # of the package instead of maintaining a second, fallible hand-written
    # fixture list here.
    fixture_prefix = 'docs/factory-ng/fixtures/contract-review/'
    files = [rel for rel in CONTRACT_FILES if not rel.startswith(fixture_prefix)]
    files.extend(str(path.relative_to(OPS)) for path in sorted((OPS / fixture_prefix).glob('*.json')))
    entries = []
    sections = [PROMPT_HEAD]
    for rel in files:
        path = OPS / rel
        raw = path.read_bytes()
        entries.append({'path': rel, 'sha256': 'sha256:' + digest(raw), 'bytes': len(raw)})
        text = raw.decode('utf-8')
        sections.append('\n\n--- FILE: %s (%s) ---\n%s' % (rel, entries[-1]['sha256'], text))
    manifest = {
        'schema': 'factory.contract-review-package/v1',
        'scope': 'high-impact Factory NG governance contract',
        'files': entries,
    }
    manifest_raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b'\n'
    manifest['package_sha256'] = 'sha256:' + digest(manifest_raw)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    sections.insert(1, '\nPackage digest: `%s`\n' % manifest['package_sha256'])
    (args.output / 'review-pack.md').write_text(''.join(sections))


if __name__ == '__main__':
    main()


--- FILE: docs/factory-ng/model-profile-contract-v1.md (sha256:0e00403fb251d3c56d0121a29ea402c13e373ad27b208ad63e2c9c0a77291070) ---
# Factory NG — Model Profile Contract v1

Status: proposed baseline, 2026-08-28  
Scope: reusable factory core; first implementation targets Magic Map work.

## Purpose

A Ticket is deliberately model-neutral.  A **Model Profile** is the versioned
adapter that decides how a particular executable/model receives the Ticket
Execution Bundle and how it is allowed to work.  This prevents the false
assumption that every model benefits from identical prompts, tools, or repair
loops, while preserving one trustworthy factory lifecycle.

```text
TicketSpec + pinned Skill + evidence bundle + acceptance contract
                         |
                         v
                  selected Model Profile
                         |
                         v
             native executable / model-specific workflow
                         |
                         v
       constrained patch or explicit decision + raw telemetry
                         |
                         v
         harness apply, deterministic gates, immutable receipt
```

The Factory owns the facts and the decision to accept work.  The adapter owns
the model-specific way of producing it.

## Common interface

Conceptually every adapter implements:

```text
execute(ticket, evidence_bundle, model_profile) -> execution_receipt
```

`ticket` is a validated TicketSpec with its DAG identity, work type, permitted
scope, pinned Skill digest, and predeclared completion behavior.  The
`evidence_bundle` is immutable for an attempt: source examples, indexed
symbols/regions, nearest working implementation, baseline measurements, and
test/gate contract.  Its digest is recorded in the receipt.

An adapter may render this input as a file, stdin, native session context, or a
sequence of messages.  It may not expand the ticket's permitted files, redefine
acceptance, or silently invent a new mission.

## Required profile declaration

Every profile is a versioned JSON document and declares:

- `id`, `version`, and the executable command/adapter implementation;
- model/provider identity and availability policy;
- bundle renderer and output contract;
- allowed tools and filesystem/network permissions;
- context, time, turn, token, and repair policies;
- which raw telemetry fields are measurable and how they are parsed;
- supported work types/Skills and required gates;
- explicit escalation, refusal, `NEED`, and infrastructure-failure behavior.

The machine-readable declaration is
[`schemas/factory.model-profile-v1.schema.json`](schemas/factory.model-profile-v1.schema.json).
A child profile may narrow the baseline's authority and execution options but
may not override its `authority` block or `budget_policy`; inheritance is
validated by the profile loader as well as the standalone schema.

V1 child profiles use a registered adapter and declare `filesystem: read-only`,
`network: none`, and a closed read-only tool set. A runner that needs write,
shell, network, commit, or deploy authority is not a child-profile variation:
it requires an explicit, reviewed Factory-contract amendment and a new baseline
with its own deterministic safety gates.

Profiles are policy, not credentials.  API keys, account state, and local-host
addresses are runtime configuration and never part of the profile artifact.

## Receipt contract

Every execution attempt returns a receipt containing at least:

- ticket ID and root IDs, profile ID/version, executable and resolved model;
- source revision, Skill digest, evidence-bundle digest, and adapter-command
  digest (secrets removed);
- each model call's raw provider counters: input, output, cache read, cache
  write, reasoning, provider-reported cost, elapsed time, and availability;
- normalized aggregate counters without double-counting cached input;
- tool/repair/NEED counts, output classification, patch digest, and changed
  paths;
- every gate command and its result; scope/accounting measurement; and
- terminal outcome: `accepted`, `parked`, `needs_split`, `reroute`,
  `gate_failed`, `contract_failed`, or `infrastructure_failed`.

For an `accepted` receipt, the schema requires a harness identity, immutable
attempt/model/adapter/patch identity, explicit raw counters for every model
call (or a reasoned `unavailable` value), before/after scope records, at least
one changed path, and one or more harness-recorded passing gates. A receipt is
evidence generated by the harness; a model response cannot make itself one.

Unknown telemetry is represented as unavailable, never as zero.  `500k`
effective tokens is a warning/reflection checkpoint, not a cancellation rule.
For V1, `effective_tokens` is the harness-normalized `input_tokens +
output_tokens`; raw cache-read, cache-write, and reasoning counters remain
separate because provider reporting overlaps and must not be double-counted.
The harness reconciles aggregate input/output totals with every per-call raw
counter, including cache and reasoning counters; if any such raw counter is
unavailable, the corresponding aggregate is unavailable rather than guessed.
An attempt above 500k opens a linked reflection ticket but may still be
accepted if its normal gates pass.
The canonical receipt shape is
[`schemas/factory.execution-receipt-v1.schema.json`](schemas/factory.execution-receipt-v1.schema.json).

## Same ticket does not mean same prompt

A valid cross-model comparison holds these invariants constant:

1. TicketSpec, source revision, Skill, scope, evidence facts, and acceptance
   gates.
2. Permitted product-file scope and the harness-owned application/gate path.
3. Maximum semantic work: the same Map-only or Engine-only child ticket, not a
   combined cross-layer mission unless that is the TicketSpec.

It intentionally permits profiles to differ in their rendered instructions,
native executable, tool allowance, context delivery, and bounded repair policy.
For example, local Qwen may receive exact regions and a small tool loop, while
Claude receives the old read-only block-output workflow.  This measures the
best supported work style for each model instead of measuring who survives an
arbitrary universal agent shell.

## Initial profiles

The initial profile documents live in `docs/factory-ng/model-profiles/v1/`.
They all use the old pipeline's central safety property: models emit a
constrained patch or a structured decision; the harness applies it and owns
the gates.  The existing Map pipeline is the baseline adapter, not legacy code
to be discarded.

The first promotion rule is modest: a profile is eligible for a work type only
after it has passed two independently frozen, production-shaped tickets with
the profile's declared acceptance contract.  Cost, elapsed time, repair count,
and scope completion are reported beside correctness; no single score alone
selects production routing.


--- FILE: docs/factory-ng/change-provenance-and-rca-contract-v1.md (sha256:e37ce75ed0bcd68cc9beeb89f1a32c91c23e68bffe4f488bd47cd284a2ccf1ba) ---
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


--- FILE: docs/factory-ng/schemas/factory.change-provenance-v1.schema.json (sha256:7ec9eb041b7606fedd16b77defa9a90f44096336bb6af2b3245a0539920c271c) ---
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "factory.change-provenance/v1",
  "type": "object",
  "required": ["schema", "ticket_id", "attempt_id", "change_class", "contract_change_scope", "source_revision", "patch_sha256", "model", "model_profile_sha256", "evidence_sha256", "skill_sha256", "gate_receipts_sha256", "reviews", "outcome"],
  "properties": {
    "schema": {"const": "factory.change-provenance/v1"},
    "ticket_id": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"},
    "root_ids": {"type": "array", "items": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"}, "minItems": 1},
    "attempt_id": {"type": "string", "pattern": "^attempt:sha256:[0-9a-f]{64}$"},
    "change_class": {"enum": ["map", "engine", "handler", "refactor", "factory"]},
    "contract_change_scope": {"enum": ["none", "amendment", "high_impact"]},
    "affected_contract_areas": {"type": "array", "uniqueItems": true, "items": {"enum": ["ticket_lifecycle", "model_profile", "skill_contract", "gate_contract", "telemetry", "provenance_rca", "cross_project_identity", "acceptance_semantics", "integration_authority", "token_cost_accounting"]}},
    "reviewed_package_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "source_revision": {"type": "string"},
    "result_commit": {"type": "string", "minLength": 7},
    "patch_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "model": {
      "type": "object",
      "required": ["profile", "resolved_model", "adapter_version"],
      "properties": {
        "profile": {"type": "string"},
        "resolved_model": {"type": "string"},
        "adapter_version": {"type": "string"}
      }
    },
    "model_profile_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "evidence_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "skill_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "telemetry": {"type": "object", "required": ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "provider_cost_usd", "elapsed_ms"], "properties": {"input_tokens": {"type": ["number", "object"]}, "output_tokens": {"type": ["number", "object"]}, "cache_read_tokens": {"type": ["number", "object"]}, "cache_write_tokens": {"type": ["number", "object"]}, "reasoning_tokens": {"type": ["number", "object"]}, "provider_cost_usd": {"type": ["number", "object"]}, "elapsed_ms": {"type": ["number", "object"]}}},
    "changed_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "scope_measurement": {"type": "object", "required": ["baseline", "post_change"], "properties": {"baseline": {"type": "object"}, "post_change": {"type": "object"}}},
    "gate_receipts_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "execution_receipt": {"type": "object"},
    "attestation": {"type": "object", "required": ["key_id", "algorithm", "signature_b64"], "properties": {"key_id": {"const": "factory-harness-review-v1"}, "algorithm": {"const": "ed25519"}, "signature_b64": {"type": "string", "minLength": 1}}},
    "reviews": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["decision", "reviewer_profile", "review_id", "review_attempt_id", "review_sha256", "review_receipt"],
        "properties": {
          "decision": {"enum": ["accepted", "rejected"]},
          "reviewer_profile": {"type": "string"},
          "review_id": {"type": "string", "pattern": "^review:sha256:[0-9a-f]{64}$"},
          "review_attempt_id": {"type": "string", "pattern": "^attempt:sha256:[0-9a-f]{64}$"},
          "review_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
          "review_receipt": {"type": "object", "required": ["schema", "review_id", "review_attempt_id", "reviewer_profile", "provider", "resolved_model", "package_sha256", "decision", "recorded_by"], "properties": {"schema": {"const": "factory.review-receipt/v1"}, "review_id": {"type": "string", "pattern": "^review:sha256:[0-9a-f]{64}$"}, "review_attempt_id": {"type": "string", "pattern": "^attempt:sha256:[0-9a-f]{64}$"}, "reviewer_profile": {"type": "string"}, "provider": {"type": "string", "minLength": 1}, "resolved_model": {"type": "string", "minLength": 1}, "package_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "decision": {"enum": ["accepted", "rejected"]}, "recorded_by": {"const": "factory-harness/v1"}, "raw_review_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "acceptance_gate_manifest_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "review_subject_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "attestation": {"type": "object", "required": ["key_id", "algorithm", "signature_b64"], "properties": {"key_id": {"const": "factory-harness-review-v1"}, "algorithm": {"const": "ed25519"}, "signature_b64": {"type": "string", "minLength": 1}}}}}
        }
      }
    },
    "outcome": {"enum": ["accepted", "rejected", "parked", "superseded"]}
  },
  "allOf": [
    {
      "if": {"properties": {"change_class": {"const": "factory"}}, "required": ["change_class"]},
      "then": {"required": ["affected_contract_areas", "reviewed_package_sha256"], "properties": {"affected_contract_areas": {"minItems": 1}, "contract_change_scope": {"enum": ["amendment", "high_impact"]}}}
    },
    {
      "if": {"properties": {"contract_change_scope": {"const": "amendment"}}, "required": ["contract_change_scope"]},
      "then": {"properties": {"reviews": {"contains": {"properties": {"decision": {"const": "accepted"}, "reviewer_profile": {"anyOf": [{"allOf": [{"pattern": "(^|[-_])sol([-_@]|$)"}, {"not": {"pattern": "(^|[-_])opus([-_@]|$)"}}]}, {"allOf": [{"pattern": "(^|[-_])opus([-_@]|$)"}, {"not": {"pattern": "(^|[-_])sol([-_@]|$)"}}]}]}}, "required": ["decision", "reviewer_profile"]}}}}
    },
    {
      "if": {"properties": {"contract_change_scope": {"const": "high_impact"}}, "required": ["contract_change_scope"]},
      "then": {
        "properties": {
          "affected_contract_areas": {"contains": {"enum": ["cross_project_identity", "acceptance_semantics", "integration_authority", "token_cost_accounting"]}},
          "reviews": {
            "allOf": [
              {"contains": {"properties": {"decision": {"const": "accepted"}, "reviewer_profile": {"allOf": [{"pattern": "(^|[-_])sol([-_@]|$)"}, {"not": {"pattern": "(^|[-_])opus([-_@]|$)"}}]}}, "required": ["decision", "reviewer_profile"]}},
              {"contains": {"properties": {"decision": {"const": "accepted"}, "reviewer_profile": {"allOf": [{"pattern": "(^|[-_])opus([-_@]|$)"}, {"not": {"pattern": "(^|[-_])sol([-_@]|$)"}}]}}, "required": ["decision", "reviewer_profile"]}}
            ]
          }
        }
      }
    }
    ,
    {
      "if": {"properties": {"outcome": {"const": "accepted"}}, "required": ["outcome"]},
      "then": {"required": ["root_ids", "result_commit", "telemetry", "changed_paths", "scope_measurement", "execution_receipt", "attestation"], "properties": {"reviews": {"items": {"properties": {"decision": {"const": "accepted"}}, "required": ["decision"]}}, "changed_paths": {"minItems": 1}}}
    }
  ],
  "additionalProperties": true
}


--- FILE: docs/factory-ng/schemas/factory.root-cause-analysis-v1.schema.json (sha256:e8e1afbe22b48f4f66be6c42cc16722aa2e752f2f3bd1fb5d4b9f439c532b8bd) ---
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "factory.root-cause-analysis/v1",
  "type": "object",
  "required": ["schema", "incident_id", "provenance_sha256", "primary_cause", "evidence", "corrective_ticket_ids", "status"],
  "properties": {
    "schema": {"const": "factory.root-cause-analysis/v1"},
    "incident_id": {"type": "string"},
    "provenance_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "primary_cause": {"enum": ["product_semantics", "ticket_contract", "evidence_or_index", "skill", "model_profile", "harness_or_gate", "review", "integration_or_environment"]},
    "contributing_causes": {"type": "array", "uniqueItems": true, "items": {"enum": ["product_semantics", "ticket_contract", "evidence_or_index", "skill", "model_profile", "harness_or_gate", "review", "integration_or_environment"]}},
    "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "model_profile_causal_claim": {"type": "boolean"},
    "counterfactual_evidence": {"type": "array", "items": {"type": "string"}},
    "corrective_ticket_ids": {"type": "array", "items": {"type": "string"}},
    "status": {"enum": ["open", "accepted", "corrected", "residual"]}
  },
  "allOf": [
    {
      "if": {"properties": {"primary_cause": {"const": "model_profile"}}, "required": ["primary_cause"]},
      "then": {"properties": {"model_profile_causal_claim": {"const": true}, "counterfactual_evidence": {"minItems": 1}}, "required": ["model_profile_causal_claim", "counterfactual_evidence"]}
    },
    {
      "if": {"properties": {"contributing_causes": {"contains": {"const": "model_profile"}}}, "required": ["contributing_causes"]},
      "then": {"properties": {"model_profile_causal_claim": {"const": true}, "counterfactual_evidence": {"minItems": 1}}, "required": ["model_profile_causal_claim", "counterfactual_evidence"]}
    }
  ],
  "additionalProperties": true
}


--- FILE: docs/factory-ng/schemas/factory.model-profile-v1.schema.json (sha256:6fe2e28a9b8b6bd00138b7f83e7876b7c6978c2acd4487151739443a0d8bbd6a) ---
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "factory.model-profile/v1",
  "type": "object",
  "required": ["schema", "id", "version"],
  "properties": {
    "schema": {"const": "factory.model-profile/v1"},
    "id": {"type": "string", "pattern": "^[a-z0-9-]+$"},
    "version": {"type": "string"},
    "extends": {"type": "string"},
    "adapter": {"type": "object"},
    "routing": {"type": "object"},
    "telemetry": {"type": "object"},
    "authority": {"type": "object"},
    "budget_policy": {"type": "object"}
  },
  "allOf": [
    {
      "if": {"properties": {"id": {"const": "staged-baseline"}}, "required": ["id"]},
      "then": {
        "required": ["input_contract", "output_contract", "authority", "budget_policy", "receipt"],
        "not": {"required": ["extends"]},
        "properties": {
          "authority": {
            "required": ["model_edits_workspace", "harness_applies_patch", "harness_owns_tests_and_gates", "commit_push_deploy"],
            "properties": {
              "model_edits_workspace": {"const": false},
              "harness_applies_patch": {"const": true},
              "harness_owns_tests_and_gates": {"const": true},
              "commit_push_deploy": {"const": false}
            }
          },
          "budget_policy": {
            "required": ["warning_is_hard_stop"],
            "properties": {"warning_is_hard_stop": {"const": false}}
          }
        }
      },
      "else": {
        "required": ["extends", "adapter", "routing", "telemetry"],
        "not": {"anyOf": [{"required": ["authority"]}, {"required": ["budget_policy"]}]},
        "properties": {
          "adapter": {
            "type": "object",
            "required": ["adapter_id", "executable", "allowed_tools", "filesystem", "network"],
            "properties": {
              "adapter_id": {"enum": ["qwen-prepared-local-v1", "qwen-prepared-direct-v1", "codex-constrained-v1", "claude-staged-v1"]},
              "executable": {"type": "string", "minLength": 1},
              "engine": {"type": "string"},
              "workflow": {"type": "string"},
              "allowed_tools": {"type": "array", "items": {"enum": ["read_file", "grep", "list_dir"]}, "uniqueItems": true},
              "filesystem": {"const": "read-only"},
              "network": {"const": "none"},
              "sandbox": {"const": "read-only"},
              "max_turns": {"type": "integer", "minimum": 1},
              "max_completion_tokens": {"type": "integer", "minimum": 1},
              "max_model_calls": {"type": "integer", "minimum": 1},
              "thinking": {"type": "string"},
              "output_markers": {"type": "array", "items": {"type": "string"}},
              "repair": {"type": "string"}
            },
            "additionalProperties": false,
            "allOf": [
            {"if": {"properties": {"adapter_id": {"const": "qwen-prepared-local-v1"}}}, "then": {"properties": {"executable": {"const": "scripts/qwen-agentic-call.py"}, "engine": {"const": "qwen-agentic"}}}},
            {"if": {"properties": {"adapter_id": {"const": "qwen-prepared-direct-v1"}}}, "then": {"properties": {"executable": {"const": "scripts/qwen-prepared-call.py"}, "engine": {"const": "qwen-prepared"}}}},
            {"if": {"properties": {"adapter_id": {"const": "codex-constrained-v1"}}}, "then": {"properties": {"executable": {"const": "codex exec"}, "engine": {"const": "codex"}}}},
            {"if": {"properties": {"adapter_id": {"const": "claude-staged-v1"}}}, "then": {"properties": {"executable": {"const": "claude -p"}, "engine": {"const": "claude"}}}}
            ]
          }
        }
      }
    }
  ],
  "additionalProperties": true
}


--- FILE: docs/factory-ng/schemas/factory.execution-receipt-v1.schema.json (sha256:e0cc485975ab871514d2dce9fe96078ba4db68c4cdb2e724a29d5d74ad7d0b5c) ---
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://factory-ng.local/schemas/factory.execution-receipt/v1",
  "type": "object",
  "required": ["schema", "attempt_id", "ticket_id", "root_ids", "profile", "model", "model_profile_sha256", "source_revision", "result_commit", "evidence_sha256", "skill_sha256", "adapter_command_sha256", "model_calls", "telemetry", "tool_counts", "patch_sha256", "changed_paths", "scope", "ticket_acceptance_contract", "acceptance_gate_manifest", "gates", "budget_checkpoint", "recorded_by", "attestation", "outcome"],
  "$defs": {
    "token_counter": {"oneOf": [{"type": "integer", "minimum": 0}, {"type": "object", "required": ["availability", "reason"], "properties": {"availability": {"const": "unavailable"}, "reason": {"type": "string", "minLength": 1}}}]},
    "metric": {"oneOf": [{"type": "number", "minimum": 0}, {"type": "object", "required": ["availability", "reason"], "properties": {"availability": {"const": "unavailable"}, "reason": {"type": "string", "minLength": 1}}}]},
    "raw_counters": {"type": "object", "required": ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "provider_cost_usd", "elapsed_ms"], "properties": {"input_tokens": {"$ref": "#/$defs/token_counter"}, "output_tokens": {"$ref": "#/$defs/token_counter"}, "cache_read_tokens": {"$ref": "#/$defs/token_counter"}, "cache_write_tokens": {"$ref": "#/$defs/token_counter"}, "reasoning_tokens": {"$ref": "#/$defs/token_counter"}, "provider_cost_usd": {"$ref": "#/$defs/metric"}, "elapsed_ms": {"$ref": "#/$defs/metric"}}, "additionalProperties": true}
  },
  "properties": {
    "schema": {"const": "factory.execution-receipt/v1"},
    "attempt_id": {"type": "string", "pattern": "^attempt:sha256:[0-9a-f]{64}$"},
    "ticket_id": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"},
    "root_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"}},
    "profile": {"type": "string", "pattern": "@"},
    "model_profile_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "model": {"type": "object", "required": ["provider", "resolved_model", "adapter_version"], "properties": {"provider": {"type": "string", "minLength": 1}, "resolved_model": {"type": "string", "minLength": 1}, "adapter_version": {"type": "string", "minLength": 1}}},
    "source_revision": {"type": "string", "minLength": 1},
    "result_commit": {"type": "string", "minLength": 7},
    "evidence_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "skill_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "adapter_command_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "model_calls": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "raw_counters"], "properties": {"id": {"type": "string", "minLength": 1}, "raw_counters": {"$ref": "#/$defs/raw_counters"}}}},
    "telemetry": {"$ref": "#/$defs/raw_counters"},
    "tool_counts": {"type": "object", "required": ["tool_calls", "need_requests", "repair_calls"], "properties": {"tool_calls": {"type": "integer", "minimum": 0}, "need_requests": {"type": "integer", "minimum": 0}, "repair_calls": {"type": "integer", "minimum": 0}}},
    "patch_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    "changed_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "scope": {"type": "object", "required": ["baseline", "post_change"], "properties": {"baseline": {"type": "object"}, "post_change": {"type": "object"}}},
    "ticket_acceptance_contract": {"type": "object", "required": ["schema", "ticket_id", "acceptance_gate_manifest_sha256", "attestation"], "properties": {"schema": {"const": "factory.ticket-acceptance/v1"}, "ticket_id": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"}, "acceptance_gate_manifest_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "attestation": {"type": "object", "required": ["key_id", "algorithm", "signature_b64"], "properties": {"key_id": {"const": "factory-harness-review-v1"}, "algorithm": {"const": "ed25519"}, "signature_b64": {"type": "string", "minLength": 1}}}}},
    "acceptance_gate_manifest": {"type": "object", "required": ["ticket_id", "evidence_sha256", "skill_sha256", "gates"], "properties": {"ticket_id": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"}, "evidence_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "skill_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "gates": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "command_sha256"], "properties": {"id": {"type": "string", "minLength": 1}, "command_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}}}}}},
    "gates": {"type": "array", "items": {"type": "object", "required": ["id", "command_sha256", "outcome"], "properties": {"id": {"type": "string", "minLength": 1}, "command_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}, "outcome": {"enum": ["passed", "failed", "not_run"]}}}},
    "budget_checkpoint": {"type": "object", "required": ["calculation", "ordinary_target_effective_tokens", "warning_reflection_effective_tokens", "effective_tokens", "status"], "properties": {"calculation": {"const": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting"}, "ordinary_target_effective_tokens": {"const": 200000}, "warning_reflection_effective_tokens": {"const": 500000}, "effective_tokens": {"$ref": "#/$defs/token_counter"}, "status": {"enum": ["within_target", "target_exceeded", "reflection_opened", "telemetry_unavailable"]}, "reflection_ticket_id": {"type": "string", "pattern": "^ticket:sha256:[0-9a-f]{64}$"}}},
    "recorded_by": {"const": "factory-harness/v1"},
    "attestation": {"type": "object", "required": ["key_id", "algorithm", "signature_b64"], "properties": {"key_id": {"const": "factory-harness-review-v1"}, "algorithm": {"const": "ed25519"}, "signature_b64": {"type": "string", "minLength": 1}}},
    "outcome": {"enum": ["accepted", "parked", "needs_split", "reroute", "gate_failed", "contract_failed", "infrastructure_failed"]}
  },
  "allOf": [
    {"if": {"properties": {"outcome": {"const": "accepted"}}, "required": ["outcome"]}, "then": {"properties": {"gates": {"minItems": 1, "items": {"properties": {"outcome": {"const": "passed"}}, "required": ["outcome"]}}, "changed_paths": {"minItems": 1}}}},
    {"if": {"properties": {"budget_checkpoint": {"properties": {"effective_tokens": {"type": "number", "maximum": 200000}}, "required": ["effective_tokens"]}}, "required": ["budget_checkpoint"]}, "then": {"properties": {"budget_checkpoint": {"properties": {"status": {"const": "within_target"}}, "required": ["status"]}}}},
    {"if": {"properties": {"budget_checkpoint": {"properties": {"effective_tokens": {"type": "number", "minimum": 200001, "maximum": 500000}}, "required": ["effective_tokens"]}}, "required": ["budget_checkpoint"]}, "then": {"properties": {"budget_checkpoint": {"properties": {"status": {"const": "target_exceeded"}}, "required": ["status"]}}}},
    {"if": {"properties": {"budget_checkpoint": {"properties": {"effective_tokens": {"type": "number", "minimum": 500001}}, "required": ["effective_tokens"]}}, "required": ["budget_checkpoint"]}, "then": {"properties": {"budget_checkpoint": {"properties": {"status": {"const": "reflection_opened"}}, "required": ["status", "reflection_ticket_id"]}}}},
    {"if": {"properties": {"budget_checkpoint": {"properties": {"effective_tokens": {"type": "object"}}, "required": ["effective_tokens"]}}, "required": ["budget_checkpoint"]}, "then": {"properties": {"budget_checkpoint": {"properties": {"status": {"const": "telemetry_unavailable"}}, "required": ["status"]}}}}
  ],
  "additionalProperties": true
}


--- FILE: docs/factory-ng/review-profiles/v1.json (sha256:c49d7250a71586423dfe7e57af89c118841f7026f9184daccac1ac892eead705) ---
{
  "schema": "factory.review-profile-registry/v1",
  "review_profiles": [
    {"id": "codex-sol-review@1", "provider": "openai", "resolved_model": "gpt-5.6-sol"},
    {"id": "claude-opus-review@1", "provider": "anthropic", "resolved_model": "claude-opus-5"}
  ]
}


--- FILE: docs/factory-ng/review-attestation-keys/v1.json (sha256:5a437b3d84cb9ef68ed04c9840844acee745ca63748d256050dd54bdc376a4d6) ---
{
  "schema": "factory.review-attestation-keys/v1",
  "keys": [
    {"id": "factory-harness-review-v1", "algorithm": "ed25519", "public_key_path": "docs/factory-ng/review-attestation-keys/factory-harness-review-v1.pub.pem"}
  ]
}


--- FILE: docs/factory-ng/review-attestation-keys/factory-harness-review-v1.pub.pem (sha256:a5265827f55e760c3481895ae6e58525d590d46ab9bd1f41edba67c34ffcf2be) ---
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA07x8YXNo9MVVFA5myvABtvYU1jHBEG6R6DH6oiGhxpo=
-----END PUBLIC KEY-----


--- FILE: scripts/test_factory_ng_contracts.py (sha256:d523e6e58dae25baaf52676915bd5b179c974617af8852570a95751128d32b49) ---
#!/usr/bin/env python3
"""Executable counterexamples for Factory NG governance contracts."""
import json
import os
import pathlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator, ValidationError


OPS = pathlib.Path('/opt/development/magic-ops')
SCHEMAS = OPS / 'docs/factory-ng/schemas'
FIXTURES = OPS / 'docs/factory-ng/fixtures/contract-review'


def load(path):
    return json.loads(path.read_text())


def validate(schema_name, fixture_name, must_pass):
    validator = Draft202012Validator(load(SCHEMAS / schema_name))
    data = load(FIXTURES / fixture_name)
    try:
        validator.validate(data)
        passed = True
    except ValidationError:
        passed = False
    if passed != must_pass:
        expectation = 'pass' if must_pass else 'fail'
        raise AssertionError('%s must %s %s' % (fixture_name, expectation, schema_name))


def validate_provenance(fixture_name, must_pass):
    result = subprocess.run(
        ['python3', str(OPS / 'scripts/factory-ng-provenance-validate.py'), str(FIXTURES / fixture_name)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if (result.returncode == 0) != must_pass:
        expectation = 'pass' if must_pass else 'fail'
        raise AssertionError('%s must %s provenance relationship validation: %s' % (fixture_name, expectation, result.stderr))


def validate_provenance_ignoring_ambient_trust_root():
    environment = dict(os.environ)
    environment['FACTORY_NG_TRUST_ROOT'] = '/tmp/factory-ng-attacker-controlled-root'
    result = subprocess.run(
        ['python3', str(OPS / 'scripts/factory-ng-provenance-validate.py'), str(FIXTURES / 'valid-provenance-refactor-qwen-review.json')],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment,
    )
    if result.returncode:
        raise AssertionError('ambient FACTORY_NG_TRUST_ROOT must not redirect accepted provenance validation: %s' % result.stderr)


def validate_receipt(fixture_name, must_pass):
    result = subprocess.run(
        ['python3', str(OPS / 'scripts/factory-ng-receipt-validate.py'), str(FIXTURES / fixture_name)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if (result.returncode == 0) != must_pass:
        expectation = 'pass' if must_pass else 'fail'
        raise AssertionError('%s must %s receipt relationship validation: %s' % (fixture_name, expectation, result.stderr))


def validate_review_package_fixture_coverage():
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            ['python3', str(OPS / 'scripts/factory-ng-contract-review-pack.py'), '--output', directory],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True,
        )
        manifest = load(pathlib.Path(directory) / 'manifest.json')
    packaged = {entry['path'] for entry in manifest['files'] if entry['path'].startswith('docs/factory-ng/fixtures/contract-review/')}
    expected = {str(path.relative_to(OPS)) for path in FIXTURES.glob('*.json')}
    if packaged != expected:
        raise AssertionError('contract review package must include exactly every fixture its deterministic gate can load')


def validate_external_trust_material_binding():
    spec = importlib.util.spec_from_file_location('factory_ng_receipt_validate_test', OPS / 'scripts/factory-ng-receipt-validate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for relative in module.REVIEWED_TRUST_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OPS / 'docs/factory-ng' / relative, target)
        module.verify_reviewed_trust_root(root)
        (root / 'review-profiles/v1.json').write_text('{"tampered":true}\n')
        try:
            module.verify_reviewed_trust_root(root)
        except ValidationError:
            return
    raise AssertionError('external trust material differing from the reviewed package must be rejected')


def main():
    validate_review_package_fixture_coverage()
    validate_external_trust_material_binding()
    validate('factory.root-cause-analysis-v1.schema.json', 'valid-rca-model-profile.json', True)
    validate('factory.root-cause-analysis-v1.schema.json', 'invalid-rca-model-profile-no-counterfactual.json', False)
    validate('factory.change-provenance-v1.schema.json', 'valid-provenance-high-impact.json', True)
    validate('factory.change-provenance-v1.schema.json', 'valid-provenance-refactor-qwen-review.json', True)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-ordinary-unsigned-review.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-contract-path-evasion.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-execution-binding-mismatch.json', True)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-adapter-path-evasion.json', True)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-omitted-required-gate.json', True)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-one-review.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-combined-reviewer.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-duplicate-review.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-amendment-wrong-reviewer.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-misclassified-token-accounting.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-package-mismatch.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-accepted-missing-complete-evidence.json', False)
    validate_provenance('valid-provenance-high-impact.json', True)
    validate_provenance('valid-provenance-refactor-qwen-review.json', True)
    validate_provenance('invalid-provenance-ordinary-unsigned-review.json', False)
    validate_provenance('invalid-provenance-contract-path-evasion.json', False)
    validate_provenance('invalid-provenance-execution-binding-mismatch.json', False)
    validate_provenance('invalid-provenance-adapter-path-evasion.json', False)
    validate_provenance('invalid-provenance-omitted-required-gate.json', False)
    validate_provenance_ignoring_ambient_trust_root()
    validate_provenance('invalid-provenance-high-impact-duplicate-review.json', False)
    validate_provenance('invalid-provenance-misclassified-token-accounting.json', False)
    validate_provenance('invalid-provenance-high-impact-package-mismatch.json', False)
    validate('factory.model-profile-v1.schema.json', 'invalid-child-profile-authority-override.json', False)
    validate('factory.model-profile-v1.schema.json', 'invalid-profile-no-extends-authority.json', False)
    validate('factory.model-profile-v1.schema.json', 'invalid-child-profile-tool-escalation.json', False)
    validate('factory.model-profile-v1.schema.json', 'invalid-child-profile-executable-escalation.json', False)
    validate('factory.model-profile-v1.schema.json', 'valid-child-profile-readonly-tools.json', True)
    validate('factory.execution-receipt-v1.schema.json', 'valid-execution-receipt.json', True)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-short-digest.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-nonhex-digest.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-trailing-digest.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-accepted-without-harness-evidence.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'valid-execution-receipt-over-threshold.json', True)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-over-threshold-no-reflection.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-mismatched-call-aggregate.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-partial-unavailable-aggregate.json', False)
    validate_receipt('valid-execution-receipt.json', True)
    validate_receipt('valid-execution-receipt-over-threshold.json', True)
    validate_receipt('invalid-execution-receipt-mismatched-call-aggregate.json', False)
    validate_receipt('invalid-execution-receipt-partial-unavailable-aggregate.json', False)
    validate_receipt('invalid-execution-receipt-content-mismatched-gate-command.json', False)
    validate('factory.execution-receipt-v1.schema.json', 'invalid-execution-receipt-ticket-required-gate-omitted.json', True)
    validate_receipt('invalid-execution-receipt-ticket-required-gate-omitted.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-review-subject-replay.json', True)
    validate_provenance('invalid-provenance-review-subject-replay.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-execution-profile-replay.json', True)
    validate_provenance('invalid-provenance-execution-profile-replay.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-model-profile-content-replay.json', True)
    validate_provenance('invalid-provenance-model-profile-content-replay.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-duplicate-raw-review.json', True)
    validate_provenance('invalid-provenance-high-impact-duplicate-raw-review.json', False)
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-review-reuses-execution-attempt.json', True)
    validate_provenance('invalid-provenance-review-reuses-execution-attempt.json', False)
    profile_validator = Draft202012Validator(load(SCHEMAS / 'factory.model-profile-v1.schema.json'))
    for profile in sorted((OPS / 'docs/factory-ng/model-profiles/v1').glob('*.json')):
        profile_validator.validate(load(profile))
    subprocess.run(['python3', str(OPS / 'scripts/factory-ng-profile-validate.py')], check=True)
    print('factory-ng contract fixtures: pass')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValidationError) as exc:
        print('factory-ng contract fixtures: FAIL: %s' % exc, file=sys.stderr)
        raise SystemExit(1)


--- FILE: scripts/factory-ng-profile-validate.py (sha256:086143556ffcb3abd685c5517ceadc3ad7ce0441e3a23dde66a394579bafe983) ---
#!/usr/bin/env python3
"""Validate Factory NG model profiles and their safe baseline inheritance."""
import argparse
import json
import pathlib
import sys

from jsonschema import Draft202012Validator, ValidationError


OPS = pathlib.Path('/opt/development/magic-ops')
DEFAULT_DIR = OPS / 'docs/factory-ng/model-profiles/v1'
SCHEMA = OPS / 'docs/factory-ng/schemas/factory.model-profile-v1.schema.json'
READ_ONLY_TOOLS = {'read_file', 'grep', 'list_dir'}
REGISTERED_ADAPTERS = {
    'qwen-prepared-local-v1': ('scripts/qwen-agentic-call.py', 'qwen-agentic'),
    'qwen-prepared-direct-v1': ('scripts/qwen-prepared-call.py', 'qwen-prepared'),
    'codex-constrained-v1': ('codex exec', 'codex'),
    'claude-staged-v1': ('claude -p', 'claude'),
}


def load(path):
    return json.loads(path.read_text())


def validate(profile_dir):
    validator = Draft202012Validator(load(SCHEMA))
    profiles = {}
    for path in sorted(profile_dir.glob('*.json')):
        profile = load(path)
        validator.validate(profile)
        profiles[profile['id'] + '@' + profile['version']] = (path, profile)
    baseline_key = 'staged-baseline@1.0.0'
    if baseline_key not in profiles:
        raise ValidationError('missing %s' % baseline_key)
    baseline = profiles[baseline_key][1]
    if baseline.get('authority', {}).get('model_edits_workspace') is not False:
        raise ValidationError('baseline must forbid model workspace edits')
    if baseline.get('authority', {}).get('harness_applies_patch') is not True:
        raise ValidationError('baseline must retain harness patch authority')
    if baseline.get('authority', {}).get('harness_owns_tests_and_gates') is not True:
        raise ValidationError('baseline must retain harness gate authority')
    if baseline.get('authority', {}).get('commit_push_deploy') is not False:
        raise ValidationError('baseline must forbid model commit/push/deploy')
    if baseline.get('budget_policy', {}).get('warning_is_hard_stop') is not False:
        raise ValidationError('baseline warning must not be a hard stop')
    for key, (path, profile) in profiles.items():
        if key == baseline_key:
            continue
        parent = profile.get('extends')
        if not parent:
            raise ValidationError('%s must extend %s' % (path, baseline_key))
        if parent not in profiles:
            raise ValidationError('%s extends unknown %s' % (path, parent))
        if 'authority' in profile or 'budget_policy' in profile:
            raise ValidationError('%s overrides baseline authority or budget policy' % path)
        adapter = profile['adapter']
        registered = REGISTERED_ADAPTERS.get(adapter.get('adapter_id'))
        if not registered:
            raise ValidationError('%s uses an unregistered adapter' % path)
        if (adapter.get('executable'), adapter.get('engine')) != registered:
            raise ValidationError('%s executable/engine does not match its registered adapter' % path)
        if adapter.get('filesystem') != 'read-only' or adapter.get('network') != 'none':
            raise ValidationError('%s broadens filesystem or network authority' % path)
        if not set(adapter.get('allowed_tools', [])).issubset(READ_ONLY_TOOLS):
            raise ValidationError('%s broadens tool authority' % path)
        # The current v1 hierarchy has exactly one immutable baseline. Keeping
        # this explicit prevents a later child-of-child chain from bypassing
        # the documented authority inheritance until it has its own contract.
        if parent != baseline_key:
            raise ValidationError('%s must extend %s directly in v1' % (path, baseline_key))
    return len(profiles)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profiles', type=pathlib.Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    print('factory-ng profiles: pass (%d)' % validate(args.profiles))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ValidationError) as exc:
        print('factory-ng profiles: FAIL: %s' % exc, file=sys.stderr)
        raise SystemExit(1)


--- FILE: scripts/factory-ng-provenance-validate.py (sha256:6009b3dcd6d491d2bf71b56119648305929caac3691f00e1155dd145c5d43716) ---
#!/usr/bin/env python3
"""Apply provenance checks that require relationships between review records."""
import argparse
import hashlib
import base64
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import importlib.util

from jsonschema import Draft202012Validator, ValidationError


OPS = pathlib.Path('/opt/development/magic-ops')
RECEIPT_MODULE_SPEC = importlib.util.spec_from_file_location('factory_ng_receipt_validate', OPS / 'scripts/factory-ng-receipt-validate.py')
factory_ng_receipt_validate = importlib.util.module_from_spec(RECEIPT_MODULE_SPEC)
RECEIPT_MODULE_SPEC.loader.exec_module(factory_ng_receipt_validate)
SCHEMA = OPS / 'docs/factory-ng/schemas/factory.change-provenance-v1.schema.json'
# This bootstrap anchor is operator-controlled outside the repository.  It is
# intentionally not environment-configurable: a worker-controlled environment
# must never be able to substitute reviewer identities or attestation keys.
TRUST_ROOT = pathlib.Path('/opt/development/factory-ng-trust')
REVIEW_PROFILES = TRUST_ROOT / 'review-profiles/v1.json'
ATTESTATION_KEYS = TRUST_ROOT / 'review-attestation-keys/v1.json'
SOL = re.compile(r'(^|[-_])sol([-_@]|$)')
OPUS = re.compile(r'(^|[-_])opus([-_@]|$)')
HIGH_IMPACT_AREAS = {
    'cross_project_identity',
    'acceptance_semantics',
    'integration_authority',
    'token_cost_accounting',
}
FACTORY_CONTRACT_PATHS = {
    'docs/factory-ng/schemas/factory.execution-receipt-v1.schema.json': {'acceptance_semantics', 'token_cost_accounting'},
    'docs/factory-ng/schemas/factory.change-provenance-v1.schema.json': {'acceptance_semantics', 'integration_authority'},
    'docs/factory-ng/schemas/factory.model-profile-v1.schema.json': {'integration_authority'},
    'docs/factory-ng/model-profile-contract-v1.md': {'integration_authority'},
    'docs/factory-ng/change-provenance-and-rca-contract-v1.md': {'acceptance_semantics'},
    'docs/factory-ng/review-profiles/v1.json': {'integration_authority'},
    'docs/factory-ng/model-profiles/v1/staged-baseline.json': {'model_profile', 'token_cost_accounting'},
    'scripts/test_factory_ng_contracts.py': {'acceptance_semantics'},
    'scripts/map-pipeline-apply.py': {'integration_authority'},
}
FACTORY_CONTRACT_PREFIXES = ('docs/factory-ng/schemas/', 'docs/factory-ng/model-profiles/v1/', 'docs/factory-ng/review-attestation-keys/', 'docs/factory-ng/fixtures/contract-review/')
FACTORY_NG_PREFIX = 'docs/factory-ng/'
FACTORY_NG_NON_CONTRACT_PREFIXES = ('docs/factory-ng/refactor-inventory/', 'docs/factory-ng/reviews/')
FACTORY_SCRIPT_PREFIX = 'scripts/factory-ng-'
FACTORY_SCRIPT_NON_CONTRACTS = {'scripts/factory-ng-refactor-inventory.py'}
FACTORY_CONTRACT_FILES = {
    'scripts/factory-ng-contract-review-pack.py',
    'scripts/factory-ng-profile-validate.py',
    'scripts/factory-ng-provenance-validate.py',
    'scripts/factory-ng-receipt-validate.py',
}


def load(path):
    return json.loads(path.read_text())


def registered_adapter_paths():
    paths = set()
    for profile_path in (OPS / 'docs/factory-ng/model-profiles/v1').glob('*.json'):
        executable = load(profile_path).get('adapter', {}).get('executable', '')
        if executable.startswith('scripts/'):
            paths.add(executable)
    return paths


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def review_subject_digest(record, receipt):
    return digest({
        'ticket_id': record['ticket_id'], 'attempt_id': record['attempt_id'],
        'source_revision': record['source_revision'], 'patch_sha256': record['patch_sha256'],
        'changed_paths': record['changed_paths'], 'evidence_sha256': record['evidence_sha256'],
        'skill_sha256': record['skill_sha256'],
        # The signed receipt is the complete executed bundle: roots, model
        # profile/adapter, result commit, telemetry, scope, gates, and its
        # pinned manifest.  Bind its canonical digest instead of maintaining
        # a fragile partial list of those fields in every review subject.
        'execution_receipt_sha256': digest(receipt),
    })


def verify_attestation(receipt, keys, noun='review receipt'):
    attestation = receipt.get('attestation')
    if not attestation or attestation.get('algorithm') != 'ed25519':
        raise ValidationError('%s lacks Ed25519 harness attestation' % noun)
    public_key = keys.get(attestation.get('key_id'))
    if not public_key:
        raise ValidationError('%s uses an untrusted attestation key' % noun)
    payload = dict(receipt)
    payload.pop('attestation', None)
    try:
        signature = base64.b64decode(attestation['signature_b64'], validate=True)
    except (KeyError, ValueError) as exc:
        raise ValidationError('invalid %s signature encoding' % noun) from exc
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory)
        payload_path, signature_path = directory / 'payload.json', directory / 'signature.bin'
        payload_path.write_bytes(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode())
        signature_path.write_bytes(signature)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(public_key), '-rawin', '-in', str(payload_path), '-sigfile', str(signature_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValidationError('%s has invalid harness attestation' % noun)


def validate_accepted_execution(record):
    if 'execution_receipt' not in record:
        raise ValidationError('accepted provenance lacks a harness execution receipt')
    receipt = record['execution_receipt']
    factory_ng_receipt_validate.validate(receipt)
    bindings = (
        ('ticket_id', 'ticket_id'), ('root_ids', 'root_ids'), ('attempt_id', 'attempt_id'),
        ('source_revision', 'source_revision'), ('patch_sha256', 'patch_sha256'),
        ('model_profile_sha256', 'model_profile_sha256'),
        ('result_commit', 'result_commit'), ('evidence_sha256', 'evidence_sha256'), ('skill_sha256', 'skill_sha256'),
    )
    for provenance_field, receipt_field in bindings:
        if record[provenance_field] != receipt[receipt_field]:
            raise ValidationError('accepted provenance %s does not bind its harness execution receipt' % provenance_field)
    if record['changed_paths'] != receipt['changed_paths']:
        raise ValidationError('accepted provenance changed_paths do not bind its harness execution receipt')
    if record['scope_measurement'] != receipt['scope']:
        raise ValidationError('accepted provenance scope_measurement does not bind its harness execution receipt')
    if record['telemetry'] != receipt['telemetry']:
        raise ValidationError('accepted provenance telemetry does not bind its harness execution receipt')
    if record['gate_receipts_sha256'] != digest(receipt['gates']):
        raise ValidationError('gate_receipts_sha256 does not bind the harness execution receipt gates')
    if record['model']['profile'] != receipt['profile'] or record['model']['resolved_model'] != receipt['model']['resolved_model'] or record['model']['adapter_version'] != receipt['model']['adapter_version']:
        raise ValidationError('accepted provenance model does not bind its harness execution receipt')
    if receipt['outcome'] != 'accepted':
        raise ValidationError('accepted provenance requires an accepted harness execution receipt')
    manifest_digest = digest(receipt['acceptance_gate_manifest'])
    subject_digest = review_subject_digest(record, receipt)
    for review in record['reviews']:
        if review['decision'] == 'accepted':
            if review['review_receipt'].get('acceptance_gate_manifest_sha256') != manifest_digest:
                raise ValidationError('accepted review receipt does not bind the execution acceptance-gate manifest')
            if review['review_receipt'].get('review_subject_sha256') != subject_digest:
                raise ValidationError('accepted review receipt does not bind the exact reviewed execution subject')


def validate(record):
    factory_ng_receipt_validate.verify_reviewed_trust_root()
    Draft202012Validator(load(SCHEMA)).validate(record)
    registry = {entry['id']: entry for entry in load(REVIEW_PROFILES)['review_profiles']}
    keys = {entry['id']: TRUST_ROOT / 'review-attestation-keys' / pathlib.Path(entry['public_key_path']).name for entry in load(ATTESTATION_KEYS)['keys']}
    for review in record['reviews']:
        receipt = review['review_receipt']
        if receipt['review_id'] != review['review_id'] or receipt['review_attempt_id'] != review['review_attempt_id']:
            raise ValidationError('review receipt identity does not match provenance review')
        if receipt['reviewer_profile'] != review['reviewer_profile'] or receipt['decision'] != review['decision']:
            raise ValidationError('review receipt profile or decision does not match provenance review')
        if digest(receipt) != review['review_sha256']:
            raise ValidationError('review_sha256 does not bind the immutable review receipt')
        if review['decision'] == 'accepted':
            if not receipt.get('raw_review_sha256'):
                raise ValidationError('accepted review receipt lacks the raw review digest')
            verify_attestation(receipt, keys)
        if record['change_class'] == 'factory':
            trusted = registry.get(receipt['reviewer_profile'])
            if not trusted or trusted['provider'] != receipt['provider'] or trusted['resolved_model'] != receipt['resolved_model']:
                raise ValidationError('Factory-contract review receipt is not bound to a registered reviewer identity')
            if review['decision'] == 'accepted' and receipt['package_sha256'] != record['reviewed_package_sha256']:
                raise ValidationError('accepted review receipt does not cover the reviewed package')
    areas = set(record.get('affected_contract_areas', []))
    derived_areas = set()
    for path in record.get('changed_paths', []):
        derived_areas.update(FACTORY_CONTRACT_PATHS.get(path, set()))
        if path.startswith(FACTORY_NG_PREFIX) and not path.startswith(FACTORY_NG_NON_CONTRACT_PREFIXES):
            derived_areas.add('acceptance_semantics')
        if path.startswith(FACTORY_SCRIPT_PREFIX) and path not in FACTORY_SCRIPT_NON_CONTRACTS:
            derived_areas.add('acceptance_semantics')
        if path in registered_adapter_paths():
            derived_areas.add('integration_authority')
        if path.startswith(FACTORY_CONTRACT_PREFIXES) or path in FACTORY_CONTRACT_FILES:
            if path.startswith('docs/factory-ng/model-profiles/v1/'):
                derived_areas.add('model_profile')
            elif path.startswith('docs/factory-ng/review-attestation-keys/'):
                derived_areas.add('integration_authority')
            elif path.startswith('docs/factory-ng/fixtures/contract-review/'):
                derived_areas.add('acceptance_semantics')
            else:
                derived_areas.add('provenance_rca')
    if derived_areas:
        if record['change_class'] != 'factory':
            raise ValidationError('Factory-contract path requires change_class factory')
        if not derived_areas.issubset(areas):
            raise ValidationError('affected_contract_areas omit harness-derived contract impact')
    if areas & HIGH_IMPACT_AREAS and record['contract_change_scope'] != 'high_impact':
        raise ValidationError('high-impact contract area requires high_impact scope')
    if record['outcome'] == 'accepted':
        verify_attestation(record, keys, 'accepted provenance')
        validate_accepted_execution(record)
    accepted = [review for review in record['reviews'] if review['decision'] == 'accepted']
    if record['change_class'] == 'factory' and any(review['review_attempt_id'] == record['attempt_id'] for review in accepted):
        raise ValidationError('accepted review reuses the producing execution attempt')
    if record['contract_change_scope'] != 'high_impact':
        return
    sol = [review for review in accepted if SOL.search(review['reviewer_profile']) and not OPUS.search(review['reviewer_profile'])]
    opus = [review for review in accepted if OPUS.search(review['reviewer_profile']) and not SOL.search(review['reviewer_profile'])]
    if not sol or not opus:
        raise ValidationError('high-impact record needs independent Sol and Opus reviews')
    for field in ('review_id', 'review_attempt_id', 'review_sha256'):
        values = [review[field] for review in accepted]
        if len(values) != len(set(values)):
            raise ValidationError('high-impact accepted reviews reuse %s' % field)
    raw_review_digests = [review['review_receipt']['raw_review_sha256'] for review in accepted]
    if len(raw_review_digests) != len(set(raw_review_digests)):
        raise ValidationError('high-impact accepted reviews reuse one raw review artifact')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('record', type=pathlib.Path)
    args = parser.parse_args()
    validate(load(args.record))
    print('factory-ng provenance: pass')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ValidationError) as exc:
        print('factory-ng provenance: FAIL: %s' % exc, file=sys.stderr)
        raise SystemExit(1)


--- FILE: scripts/factory-ng-receipt-validate.py (sha256:3d9582ed36392360e2205fe71c7ef634e7dada73b1ee0c80a714fc6ecd5dbf0f) ---
#!/usr/bin/env python3
"""Validate cross-field execution-receipt accounting invariants."""
import argparse, base64, hashlib, subprocess, tempfile
import json
import pathlib
import sys

from jsonschema import Draft202012Validator, ValidationError


OPS = pathlib.Path('/opt/development/magic-ops')
SCHEMA = OPS / 'docs/factory-ng/schemas/factory.execution-receipt-v1.schema.json'
# Operator-controlled bootstrap anchor; do not permit an ambient worker
# environment to redirect receipt verification to attacker-owned keys.
TRUST_ROOT = pathlib.Path('/opt/development/factory-ng-trust')
PUBLIC_KEY = TRUST_ROOT / 'review-attestation-keys/factory-harness-review-v1.pub.pem'
REVIEWED_TRUST_FILES = (
    pathlib.Path('review-profiles/v1.json'),
    pathlib.Path('review-attestation-keys/v1.json'),
    pathlib.Path('review-attestation-keys/factory-harness-review-v1.pub.pem'),
)


def load(path):
    return json.loads(path.read_text())


def verify_reviewed_trust_root(root=TRUST_ROOT):
    """Require the external bootstrap copy to equal the reviewed package files."""
    for relative in REVIEWED_TRUST_FILES:
        reviewed = OPS / 'docs/factory-ng' / relative
        deployed = root / relative
        if not deployed.is_file() or hashlib.sha256(deployed.read_bytes()).digest() != hashlib.sha256(reviewed.read_bytes()).digest():
            raise ValidationError('external trust material does not match the reviewed Factory package: %s' % relative)


def expected_model_profile_digest(profile):
    if profile == 'human@1':
        raw = b'factory-human-governance-profile/v1'
    else:
        profile_id, separator, version = profile.partition('@')
        if not separator:
            raise ValidationError('execution receipt has an unversioned model profile')
        candidates = list((OPS / 'docs/factory-ng/model-profiles/v1').glob('*.json'))
        for candidate in candidates:
            profile_data = load(candidate)
            if profile_data.get('id') == profile_id and profile_data.get('version') == version:
                raw = candidate.read_bytes()
                break
        else:
            raise ValidationError('execution receipt references an unregistered model profile')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def validate(receipt):
    verify_reviewed_trust_root()
    Draft202012Validator(load(SCHEMA)).validate(receipt)
    if receipt['model_profile_sha256'] != expected_model_profile_digest(receipt['profile']):
        raise ValidationError('execution receipt does not bind the registered Model Profile artifact')
    payload = dict(receipt); attestation = payload.pop('attestation')
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory); inp, sig = directory/'receipt.json', directory/'signature.bin'
        inp.write_bytes(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode())
        sig.write_bytes(base64.b64decode(attestation['signature_b64'], validate=True))
        if subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(PUBLIC_KEY),'-rawin','-in',str(inp),'-sigfile',str(sig)], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode:
            raise ValidationError('execution receipt has invalid harness attestation')
    checkpoint = receipt['budget_checkpoint']
    manifest = receipt['acceptance_gate_manifest']
    ticket_contract = receipt['ticket_acceptance_contract']
    verify_payload = dict(ticket_contract)
    verify_payload.pop('attestation')
    with tempfile.TemporaryDirectory() as directory:
        directory = pathlib.Path(directory); inp, sig = directory/'ticket-contract.json', directory/'signature.bin'
        inp.write_bytes(json.dumps(verify_payload, sort_keys=True, separators=(',', ':')).encode())
        sig.write_bytes(base64.b64decode(ticket_contract['attestation']['signature_b64'], validate=True))
        if subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(PUBLIC_KEY),'-rawin','-in',str(inp),'-sigfile',str(sig)], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode:
            raise ValidationError('ticket acceptance contract has invalid harness attestation')
    if ticket_contract['ticket_id'] != receipt['ticket_id']:
        raise ValidationError('ticket acceptance contract does not bind the execution ticket')
    if ticket_contract['acceptance_gate_manifest_sha256'] != 'sha256:' + hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest():
        raise ValidationError('execution manifest does not match the immutable TicketSpec acceptance contract')
    for field in ('ticket_id', 'evidence_sha256', 'skill_sha256'):
        if manifest[field] != receipt[field]:
            raise ValidationError('acceptance gate manifest %s must bind the execution receipt' % field)
    required_gates = {(gate['id'], gate['command_sha256']) for gate in manifest['gates']}
    recorded_gates = {(gate['id'], gate['command_sha256']) for gate in receipt['gates']}
    if len(required_gates) != len(manifest['gates']):
        raise ValidationError('acceptance gate manifest repeats a gate identity')
    if len(recorded_gates) != len(receipt['gates']):
        raise ValidationError('execution receipt repeats a gate identity')
    if required_gates != recorded_gates:
        raise ValidationError('execution receipt gate set does not exactly match the pinned acceptance gate manifest')
    if receipt['outcome'] == 'accepted' and any(gate['outcome'] != 'passed' for gate in receipt['gates']):
        raise ValidationError('accepted execution receipt includes a failed or unrun required gate')
    effective = checkpoint['effective_tokens']
    input_tokens = receipt['telemetry']['input_tokens']
    output_tokens = receipt['telemetry']['output_tokens']
    for field in ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens', 'provider_cost_usd', 'elapsed_ms'):
        call_values = [call['raw_counters'][field] for call in receipt['model_calls']]
        aggregate = receipt['telemetry'][field]
        if all(isinstance(value, (int, float)) for value in call_values):
            if not isinstance(aggregate, (int, float)) or aggregate != sum(call_values):
                raise ValidationError('telemetry.%s must equal the sum of per-call raw counters' % field)
        elif not isinstance(aggregate, dict) or aggregate.get('availability') != 'unavailable':
            raise ValidationError('telemetry.%s must be unavailable when a per-call raw counter is unavailable' % field)
    if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
        if not isinstance(effective, (int, float)) or effective != input_tokens + output_tokens:
            raise ValidationError('effective_tokens must equal input_tokens + output_tokens')
    if (isinstance(input_tokens, dict) or isinstance(output_tokens, dict)) and not isinstance(effective, dict):
        raise ValidationError('unavailable aggregate token telemetry requires unavailable effective_tokens')
    if isinstance(effective, dict) and checkpoint['status'] != 'telemetry_unavailable':
        raise ValidationError('unavailable effective_tokens requires telemetry_unavailable status')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt', type=pathlib.Path)
    args = parser.parse_args()
    validate(load(args.receipt))
    print('factory-ng receipt: pass')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ValidationError) as exc:
        print('factory-ng receipt: FAIL: %s' % exc, file=sys.stderr)
        raise SystemExit(1)


--- FILE: docs/factory-ng/model-profiles/v1/staged-baseline.json (sha256:570dd9a969b571cba6c16839010ea96f39eb80434880aff7b26fc2371f408f23) ---
{
  "schema": "factory.model-profile/v1",
  "id": "staged-baseline",
  "version": "1.0.0",
  "purpose": "The proven Map/Engine pipeline shape: deterministic evidence, constrained model output, harness-owned apply and gates.",
  "input_contract": {
    "ticket": "TicketSpec v1",
    "evidence_bundle": "immutable, digest recorded",
    "skill": "pinned by digest",
    "rendering": "structured text packet"
  },
  "output_contract": {
    "patch": "SEARCH/REPLACE or NEWFILE blocks accepted by scripts/map-pipeline-apply.py",
    "decision": ["NEEDS_PRIMITIVE", "SEMANTIC_GAP", "AMBIGUOUS", "MISMATCH"],
    "need": "at most one bounded NEED request before a patch/decision"
  },
  "authority": {
    "model_edits_workspace": false,
    "harness_applies_patch": true,
    "harness_owns_tests_and_gates": true,
    "commit_push_deploy": false
  },
  "budget_policy": {
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "warning_is_hard_stop": false,
    "max_patch_calls": 2
  },
  "receipt": "factory.execution-receipt/v1"
}


--- FILE: docs/factory-ng/model-profiles/v1/qwen-prepared-local.json (sha256:c3d7cebf5a8f9801c8d5f14761599b5f2d1f2664758776afce111fd36843c4c7) ---
{
  "schema": "factory.model-profile/v1",
  "id": "qwen-prepared-local",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "qwen-prepared-local-v1",
    "executable": "scripts/qwen-agentic-call.py",
    "engine": "qwen-agentic",
    "workflow": "prepared local tool loop; exact evidence is supplied before any repository read",
    "allowed_tools": ["read_file", "grep", "list_dir"],
    "filesystem": "read-only",
    "network": "none",
    "max_turns": 25,
    "thinking": "disabled by adapter",
    "output_markers": ["<<<", "@@@"]
  },
  "routing": {
    "best_for": ["classification", "evidence review", "small well-evidenced Map patch", "bounded local repair"],
    "escalate_when": ["evidence requests reveal a cross-layer design decision", "gate failure persists after one focused repair", "ticket needs Engine work"]
  },
  "telemetry": {
    "source": "adapter stderr token records",
    "measured": ["input", "output", "cache_read", "cache_write", "elapsed"],
    "unavailable": ["provider_cost", "reasoning"]
  }
}


--- FILE: docs/factory-ng/model-profiles/v1/qwen-prepared-direct.json (sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e) ---
{
  "schema": "factory.model-profile/v1",
  "id": "qwen-prepared-direct",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "qwen-prepared-direct-v1",
    "executable": "scripts/qwen-prepared-call.py",
    "engine": "qwen-prepared",
    "workflow": "no-tools completion from a prepared packet; at most one bounded NEED response or one focused repair, then harness-owned apply/gates",
    "allowed_tools": [],
    "filesystem": "read-only",
    "network": "none",
    "thinking": "disabled by adapter",
    "max_completion_tokens": 2000,
    "max_model_calls": 2
  },
  "routing": {
    "best_for": ["small evidence-complete Map patch", "deterministic wiring", "constrained local repair"],
    "do_not_use_when": ["the ticket needs repository discovery", "the packet has unresolved design alternatives", "cross-layer capability design is required"],
    "escalate_to": "qwen-prepared-local@1.0.0 or a stronger remote profile"
  },
  "telemetry": {
    "source": "adapter stderr token records",
    "measured": ["input", "output", "cache_read", "cache_write", "elapsed"],
    "unavailable": ["provider_cost", "reasoning"]
  }
}


--- FILE: docs/factory-ng/model-profiles/v1/codex-constrained.json (sha256:943cf989ed5cde418cc9d375d86aac0cc3846ba8a808e05247c824dfcdf63088) ---
{
  "schema": "factory.model-profile/v1",
  "id": "codex-constrained",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "codex-constrained-v1",
    "executable": "codex exec",
    "engine": "codex",
    "workflow": "read-only native coding session with block-only final output",
    "sandbox": "read-only",
    "allowed_tools": ["read_file", "grep", "list_dir"],
    "filesystem": "read-only",
    "network": "none",
    "max_turns": 1,
    "repair": "one focused retry only after a harness failure"
  },
  "routing": {
    "best_for": ["well-evidenced Map/Engine implementation", "focused gate repair"],
    "escalate_when": ["ticket contract demands broader architecture work"]
  },
  "telemetry": {
    "source": "Codex JSON turn.completed usage",
    "measured": ["input", "output", "cache_read", "cache_write", "reasoning", "elapsed"],
    "cost": "versioned local pricing policy"
  }
}


--- FILE: docs/factory-ng/model-profiles/v1/claude-staged.json (sha256:1db243c4ee115cc4a2fff55895e6065f6c3940aaeefbbcfc707409654f47652b) ---
{
  "schema": "factory.model-profile/v1",
  "id": "claude-staged",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "claude-staged-v1",
    "executable": "claude -p",
    "engine": "claude",
    "workflow": "old pipeline-compatible read-only block-output call",
    "allowed_tools": [],
    "filesystem": "read-only",
    "network": "none",
    "max_turns": 5,
    "repair": "one focused retry only after a harness failure"
  },
  "routing": {
    "best_for": ["well-evidenced Map/Engine implementation", "structured semantic decision"],
    "escalate_when": ["the ticket genuinely requires an approved exploration profile"]
  },
  "telemetry": {
    "source": "Claude JSON modelUsage aggregate",
    "measured": ["input", "output", "cache_read", "cache_write", "provider_cost", "elapsed"],
    "note": "nested provider model usage must be aggregated; top-level final-turn usage is insufficient"
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-child-profile-authority-override.json (sha256:659d80ba9a31d0f5915b2bd2dd8565c7d07fee1dec98f071c4489baf0413c82f) ---
{
  "schema": "factory.model-profile/v1",
  "id": "bad-child",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {},
  "routing": {},
  "telemetry": {},
  "authority": {
    "model_edits_workspace": true
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-child-profile-executable-escalation.json (sha256:47fa2bcf211af421318b3e87027eaae6a2ac12a515ea9a7cf72855e9c1f6cecf) ---
{
  "schema": "factory.model-profile/v1",
  "id": "unsafe-claude-child",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "claude-staged-v1",
    "executable": "bash -c 'modify workspace and push'",
    "engine": "claude",
    "workflow": "forged executable",
    "allowed_tools": [],
    "filesystem": "read-only",
    "network": "none",
    "max_turns": 1
  },
  "routing": {},
  "telemetry": {}
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-child-profile-tool-escalation.json (sha256:be32620851a1fc6a1604f746665e34f7995872b01fa42f4ec8f510ee9faafc51) ---
{
  "schema": "factory.model-profile/v1",
  "id": "bad-tool-child",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "claude-staged-v1",
    "executable": "claude -p",
    "allowed_tools": [
      "read_file",
      "shell"
    ],
    "filesystem": "read-only",
    "network": "none"
  },
  "routing": {},
  "telemetry": {}
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-accepted-without-harness-evidence.json (sha256:2c9d990d8fcbeb8194eeaa0b85e700355fd963c5e51ff15d7a93bb105dfee28c) ---
{
  "schema": "factory.execution-receipt/v1",
  "ticket_id": "ticket:sha256:2bea7bc0eb471117412dd15884fbb6cbac960727638cb70ec1c25a93c1f4a08e",
  "profile": "qwen-prepared-direct@1.0.0",
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1"
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2
  },
  "outcome": "accepted",
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-content-mismatched-gate-command.json (sha256:a92d19be97d68b3496ac603d187b137234c320bd12b7e2842ca8c2b5ed764ad5) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:63d234aea1dbfa133d709495791a125c8d028b2874abf5d11cb0c2523d467532",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "1K1pB9aZIfS6CllEpfehDCi/1MY3fMXxwegzL8gLSR3zi/t/cIKbZ8lqq5bskwomQBTRaFvrHysIcc86X79GAA=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-mismatched-call-aggregate.json (sha256:9a9783ca4fdad2f5bd244e86d499862793b6d909181b1f28c16bd9ca3a631b82) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:905da3d5f7b1a9ffe37a9a808f6f350a05dddf25ca4243ed017a4074fc93e78e",
  "ticket_id": "ticket:sha256:8c6be6b6986bd6f924fea86c914eeec7addca341b40e7f562a690194dad2f0c0",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 510000,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {},
    "post_change": {}
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "outcome": "accepted",
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-nonhex-digest.json (sha256:2c167dabcdbc718e024b0aa571a3030aab264d1893aaf3530b3a358cc49eb97e) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "B43Up10ndRKXQxrZA7DsSdxv/l834UY+1g0kKeSt9BpgiBgFV1Fw+JsKBIL6vP0pWag9lCXrwj37Od19kI0ODA=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-over-threshold-no-reflection.json (sha256:ffee9fbdd6cbe9670755e86d8be1f4ac6a8b28db0c9fc34fa40773104b928ef2) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:bb1168a0855bd4d27acb9e08d85336c4acd72b9fccb92f7d7cef3cae527ca169",
  "ticket_id": "ticket:sha256:90177429ead01909d54d286045fb874a9d61da60cfd7a3d58547c8843668f98d",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 510000,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 510000,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {},
    "post_change": {}
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 510001,
    "status": "target_exceeded"
  },
  "recorded_by": "factory-harness/v1",
  "outcome": "accepted",
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-partial-unavailable-aggregate.json (sha256:3a2b511ffa5d24f848b35b6556b7264c47e7d86c133e923c8539c396737ed970) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:f860080e9c6435d50cc00a40616b17c644421bb53ad9af58d53fb683d03c5d07",
  "ticket_id": "ticket:sha256:19a3ae7ee7641c2a6ca5967f9fa317de82a1f4a11422e933c3f835d2794b933d",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_tokens": {
          "availability": "unavailable",
          "reason": "provider did not report cache reads"
        },
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {},
    "post_change": {}
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 2,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "outcome": "accepted",
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-short-digest.json (sha256:acc915ddc3f93bf28a30c8fc7656d73365bfd7fd55bf2cf22620d5cb8df33afb) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:abc",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "B43Up10ndRKXQxrZA7DsSdxv/l834UY+1g0kKeSt9BpgiBgFV1Fw+JsKBIL6vP0pWag9lCXrwj37Od19kI0ODA=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-ticket-required-gate-omitted.json (sha256:3f8415a77927cc48d50e1b5ec2dcf27b54417d707ae1d304b18af227e87f46b9) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "7YVqVn1a5g6J+MVrBxciPlGE4TPt/m5G6TBuQWkdNyrtVoW4Y3UusS07Bgtmzdh+DMl7ARCjnsmHqHB2env4Bw=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e",
  "ticket_acceptance_contract": {
    "schema": "factory.ticket-acceptance/v1",
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "acceptance_gate_manifest_sha256": "sha256:6f882574e12aa852af7f7a41138fac3bdbf3ee09d9e8017eefb29d2383a0afe2",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "LmMrwk8QVh9pHnLJKF7yjEauNgaNoqyCQ6a08cfh7vgfPLoVmnM9Gfo5KqFbUOg2cOA+dpMHq+W8hmARZEFQCg=="
    }
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-execution-receipt-trailing-digest.json (sha256:26eac7730a009b9c02ce8fd3a52a4e002fb6bbc0cc35b6bb15cca7215daf2928) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "B43Up10ndRKXQxrZA7DsSdxv/l834UY+1g0kKeSt9BpgiBgFV1Fw+JsKBIL6vP0pWag9lCXrwj37Od19kI0ODA=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-profile-no-extends-authority.json (sha256:e0e5ddb1cb6f8ccbb5d08c46d7c91e02e7b0a9ef50b62cc097e6610488b3b809) ---
{
  "schema": "factory.model-profile/v1",
  "id": "rogue-root",
  "version": "1.0.0",
  "adapter": {},
  "routing": {},
  "telemetry": {},
  "authority": {
    "model_edits_workspace": true,
    "commit_push_deploy": true
  },
  "budget_policy": {
    "warning_is_hard_stop": true
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-accepted-missing-complete-evidence.json (sha256:7a66539227b5bba528aa82c558a21eee911e865d6747f371d2aec98362106363) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:cf6dae8ecd01ac041b151a430fb04b7d25215091bb67428bcc52349963506418",
  "attempt_id": "attempt:sha256:b9e0066d0d57fbc845c1c5e9662489aec049651a2f777d3d176d381d60e3f3a8",
  "change_class": "factory",
  "contract_change_scope": "amendment",
  "affected_contract_areas": [
    "model_profile"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:199c7fa539eb0754824c28de0455703fcbe62c513044e7144bb428fa43ba4613",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-adapter-path-evasion.json (sha256:6738e59c796e103b2cc3b2d802ad8db6d913a50830aa44c448e94c40c4b0454c) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "scripts/qwen-prepared-call.py"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:13eb8efe444d1001fb049a182c434f814f6db5d875f826f0ca5c87cb98fd808e",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:7b9b28600d01155f110ffcb9b9d3675e9c36a430fce42afd68fcf383945f7d84",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "Ks96WcEKf12oR/5csmXbuzhX7IY4RMevI0BuvaLed1toAlidGKzDcA5aB+BT2WvZifhkAbTgAIcQZbzx9p3vAg=="
        },
        "acceptance_gate_manifest_sha256": "sha256:bd336f6e090e33a90c38f30cb0e578205c9f7a66dc4a14aff94a9b3804f78a2a"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "scripts/qwen-prepared-call.py"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "1L+eqbxyiSdWO+CHJhmYebk8ea/EnEuU5PV8rc6wyjxJUQFoLrkxzOI2KGwpcIXDzBj94buqEpldG48ngjzkBw=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "PnzkR/Uuf2kWW2MDE1WngC4dF5g+NBCeFQvZQssqcDh4PLOOg5FNFj3k1py2lEhxZz23qop6xgbkdeefijEgBQ=="
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-amendment-wrong-reviewer.json (sha256:888e755ce1be32c811a6380707de2474640c8dd75f3a01748ef76a18d930d624) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d40c909aeb419c973ec44db592c26b49ed1eff257be09227c747f6cb1b5558c1",
  "attempt_id": "attempt:sha256:d6ecacf48bb46422d8a853edd9d40a3945cf24b6a43e25af802b1c9e65c619fb",
  "change_class": "factory",
  "contract_change_scope": "amendment",
  "affected_contract_areas": [
    "model_profile"
  ],
  "source_revision": "abc123",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:e9a76f2fac583d580e0a9424f9c77416aea04bf260c37e871d2f983736773057"
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-contract-path-evasion.json (sha256:c1782327ae542aa56a86a613d9d0370e12466bd7086f187589d30c290d77e85b) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:cdcb6eb8bd41cba44b770a0a27916dc566b57d62588dc2fc4429eaff0df6014f",
  "root_ids": [
    "ticket:sha256:9d18fce4396aba69509863c289f59c65e73e2048456eaceba6f327bb4f412ddb"
  ],
  "attempt_id": "attempt:sha256:5f6d6509929af569929de9abb5439b012b9bbf977f5ad8522f0287d8e09e564c",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "scripts/factory-ng-routing-policy.py"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:cbda98fc1e3d28de886958057384d95841ed143c3156259c8b1115a0ad863cf6",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-execution-binding-mismatch.json (sha256:e4f2201743fab38b66371e5aa873227eee6409a2481e48dc39cbcab560b374c0) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 999,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:13eb8efe444d1001fb049a182c434f814f6db5d875f826f0ca5c87cb98fd808e",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:7b9b28600d01155f110ffcb9b9d3675e9c36a430fce42afd68fcf383945f7d84",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "Ks96WcEKf12oR/5csmXbuzhX7IY4RMevI0BuvaLed1toAlidGKzDcA5aB+BT2WvZifhkAbTgAIcQZbzx9p3vAg=="
        },
        "acceptance_gate_manifest_sha256": "sha256:bd336f6e090e33a90c38f30cb0e578205c9f7a66dc4a14aff94a9b3804f78a2a"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "oxh3p9NtfimA2dpZ65Lhszb5cIa5wQ3RQuJuEK16UIQ6i4DdS1WA5PY7dG81Nw9VJGWYMZseryqZYGd3HfphDg=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "Jtwi4T5BeqtSEHabQHrPIZUVS5DS6WKnolt3hf+emMCx8BLht9JmVE0/AS2Dl7VXfILdITlf2lmStcJalHOdDw=="
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-execution-profile-replay.json (sha256:686047eee4753160ca0b6143b3be71f0479377c6d6746c2cff839ffb8e8797d0) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "claude-staged@1.0.0",
    "resolved_model": "claude",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:0810c8a183bef61a77d8486cf3b882bf9106a2561af500dce53c011bacdd1fea",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "5YND8i8Kbk4/q5Yi5EYT11fOnZ9qYYhyT6CpF5LpParAtvjIh1C4O/miqrKE7mPAQtpci+dI2m65GzT0lOo1DQ=="
        },
        "acceptance_gate_manifest_sha256": "sha256:f3a8717fadd97116bec4d659dbfd59023a2d5d43bc01a2299c99db91bfde2861",
        "review_subject_sha256": "sha256:0970945750c00c246f2a961db3ac3451aadc957ff48d87edfa8d3c073b4c0756"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "claude-staged@1.0.0",
    "model": {
      "provider": "anthropic",
      "resolved_model": "claude",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "whEGa6trE84ekMvE/TZpSieZvXP+dajYx4PXFib4UAjRgvo8qkKluDph4u6bJVTkZFl7wd2EsW32j+DtdB+8Dg=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:1db243c4ee115cc4a2fff55895e6065f6c3940aaeefbbcfc707409654f47652b"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "XAKubx10qCcRelvTvx1itIBgwv5DwWcGiV0mflpMcYtJqBtjCnNtXfNF4hI3+zZzohUPuZ0b4z//nTt5oY24DQ=="
  },
  "model_profile_sha256": "sha256:1db243c4ee115cc4a2fff55895e6065f6c3940aaeefbbcfc707409654f47652b"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-combined-reviewer.json (sha256:8b33c0952c5d0a58370f3c2fb3ee2cee33512abebb689b66139134e920574a9e) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:130db75996e82189e858d3eaa2e6eb9b769dd8b75b5e1ef2cc412dbaa54e3b45",
  "attempt_id": "attempt:sha256:f5553b73b1681bc9a696fd4684a9e323aefd8dcfa0d755952007f92187f587a8",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting"
  ],
  "source_revision": "abc123",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "sol-opus-review@1",
      "review_id": "review:sha256:058bd1de78f6107c9acafa2bc0ba842954867a78ec1359b825735b7ea244cf77",
      "review_attempt_id": "attempt:sha256:d5603e7d57d299fcf7d2a5fb24abe3f6e59b515727fe06e986b2b0d43ca5c57f",
      "review_sha256": "sha256:de8e94bcac942316465cac5eff6336afe37c51b615731d7122cefda2ffca9399"
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-duplicate-raw-review.json (sha256:70271bde932aa7edbe5858c4ccae41eeac68bdc30676909ff87c61fdd8bb860f) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting",
    "acceptance_semantics"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human@1",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:994e7392d807a7a953e600fa20871affd54323e57314ba203f8688d7da261c4e",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "rjghONH1xZZ78dxKUGXuPW5iUjbQHXriYyEeOW3i8NhmQYcUL/mX0rGWSTCABLdHO5H9Ei2FujvSgPycod+OAA=="
        },
        "raw_review_sha256": "sha256:e324180f285d1fa2104fce12da78493a07ca86830b151d92533b0561fcb328c2",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:0ac83a67251618780d3498c6616541ae1b94b13577d50173428d6b6314dee84f"
      }
    },
    {
      "decision": "accepted",
      "reviewer_profile": "claude-opus-review@1",
      "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
      "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
      "review_sha256": "sha256:3ad5671aab79619ce54ecd52aff2b8013aee6c84d1f512d665e19141bef1a029",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
        "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
        "reviewer_profile": "claude-opus-review@1",
        "provider": "anthropic",
        "resolved_model": "claude-opus-5",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "y4lIM/C73knHVlBuG8yUktrQYDn/P2LArDJRA2ICyKCn0jSCOG1+JrzLne1hRsZb5gvc8HH88xsFGi7SLQAhBw=="
        },
        "raw_review_sha256": "sha256:e324180f285d1fa2104fce12da78493a07ca86830b151d92533b0561fcb328c2",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:0ac83a67251618780d3498c6616541ae1b94b13577d50173428d6b6314dee84f"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
    "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
    "profile": "human@1",
    "model": {
      "provider": "operator",
      "resolved_model": "human",
      "adapter_version": "n/a"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "g4jhn4vkRfM02klVYK4noYoQ46CmO1Rh6064voAgtd12omxldj+mdIY71SUSkrfBUNadJWCWSSQ79cKTjhvVCA=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "ZM3mbAXErGzraCgmprCZzlWoTJR1S65GYwkX7vVn9meASk9NN1ES+Cc4PvA1swNndKad7qT0NCiSt4zaT/W9Cw=="
  },
  "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-duplicate-review.json (sha256:9530e5655b4be79145a9f3e8057c256f23fd62ee91460eaf5e1702f529c50556) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:c151c28fb5ca4255a2c90b6655ac9ab6a7f03e2e148ea709b069317811c724f7",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:d055f41b7008c61aa567867496f7b6a2adbb0103aefa41691885511fad55d955",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9676f693a52214ce8bcc8fb53d8a9d27ac40c5076866be2d02bc157d57282020",
      "review_attempt_id": "attempt:sha256:8ac0b2772a800b3e176030da5e0c8b8678ac5411ea530ae31be59611f7c9a851",
      "review_sha256": "sha256:74e56a0b7f5339dca602e342333565aa2eff4db046d378d20f38f6f191d290ae",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9676f693a52214ce8bcc8fb53d8a9d27ac40c5076866be2d02bc157d57282020",
        "review_attempt_id": "attempt:sha256:8ac0b2772a800b3e176030da5e0c8b8678ac5411ea530ae31be59611f7c9a851",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    },
    {
      "decision": "accepted",
      "reviewer_profile": "claude-opus-review@1",
      "review_id": "review:sha256:9676f693a52214ce8bcc8fb53d8a9d27ac40c5076866be2d02bc157d57282020",
      "review_attempt_id": "attempt:sha256:8ac0b2772a800b3e176030da5e0c8b8678ac5411ea530ae31be59611f7c9a851",
      "review_sha256": "sha256:7e427ead93868b615ef1f0385183a050ef38a7fecc8851c02538b9e84acb9edb",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9676f693a52214ce8bcc8fb53d8a9d27ac40c5076866be2d02bc157d57282020",
        "review_attempt_id": "attempt:sha256:8ac0b2772a800b3e176030da5e0c8b8678ac5411ea530ae31be59611f7c9a851",
        "reviewer_profile": "claude-opus-review@1",
        "provider": "anthropic",
        "resolved_model": "claude-opus-5",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-one-review.json (sha256:3ad2c3bdafad6fb66e84dfe3ef87e3ada3c3abcd03d82a0b17ec719c3c2e6ffb) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:c121173cb723579602adf98d1893d59a82a4a9134edb7cd4d2b80eb297b6c5fa",
  "attempt_id": "attempt:sha256:e325a904b5611671e8660aefcdc8c5deb3d6fd0338ce9b3fc1795ad80dd7cb0e",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting"
  ],
  "source_revision": "abc123",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:7d5048e19590b5fe18839df768cfb4f2c35a94e30ecea949ebe766d88f847f80"
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-high-impact-package-mismatch.json (sha256:acda48a5497edc9e77945234d9d5313d168fdf0bd69efa4b12ca1b480f458974) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:4016381a44b48ae62f73ca76f867a82796e5eca863c895adc0c339be72c1c1ee",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:2c263d27d536d706b48e43efa04a7ef97d6e7d8dfb251c54d4757e7211f51b9d",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting"
  ],
  "reviewed_package_sha256": "sha256:ffe04907a5e7e524caa765cd964adf65ce6b656fea6fad32dfdf082321e08688",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:199c7fa539eb0754824c28de0455703fcbe62c513044e7144bb428fa43ba4613",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    },
    {
      "decision": "accepted",
      "reviewer_profile": "claude-opus-review@1",
      "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
      "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
      "review_sha256": "sha256:30153754b314ee8a0382faad8fd9a98d623c7915570a9d96872207c232e859a3",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
        "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
        "reviewer_profile": "claude-opus-review@1",
        "provider": "anthropic",
        "resolved_model": "claude-opus-5",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-misclassified-token-accounting.json (sha256:afc6146eee399cb099eb1a92b98e5d787f8a04db16fb458a22fec2190d9e87cd) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:67858f50874d8394ae34122618640e7d684b3648d36b28003dc0610ffed439fe",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:5f2e99c42cd0a7d9bdaf25ee7ac746834aa7795eb829f856ee8181ac6b411625",
  "change_class": "factory",
  "contract_change_scope": "amendment",
  "affected_contract_areas": [
    "token_cost_accounting"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:199c7fa539eb0754824c28de0455703fcbe62c513044e7144bb428fa43ba4613",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1"
      }
    }
  ],
  "outcome": "accepted",
  "model_profile_sha256": "sha256:748bbeca29309cf5b9e6e8258114b22321cc19c375e98c97582bebac10f92fee"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-model-profile-content-replay.json (sha256:a2929afc706dd8940e570073cfe035f7b08acb8f40049635edea0eef54fda094) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:3f6949d62df777d409fd2936fc21e3c7f47801f23b6d62a98c09bb0c59e9f43e",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "QvovLFNI58IE0uQnfzIKLj6hajz/ACl+lkSSDidg5T8LU+E92fgwcgrvyXvH7aAsrHtM5WiCCcO0h8jwlJ39DQ=="
        },
        "acceptance_gate_manifest_sha256": "sha256:f3a8717fadd97116bec4d659dbfd59023a2d5d43bc01a2299c99db91bfde2861",
        "review_subject_sha256": "sha256:cef6d6b2f8f0067d4fed79d1c33d5e3504dac3724e43f892bc51703136478b51"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "W7umgM072+XAX85osfMLDBPkewUfcW0OCZErjLQx3y+EwuQVZD4Ne7H0oZF/w5RRsNOkRxjbLz/KyLhagW+8DA=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:32f3b01d4108967ee1e25454c12432ad8a602d84dbb3f8bf075cc776f67ddb92"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "WXfR9bL51SMzvHzFZcp9fHij9d99kkKcVWP85XjJnkYKb2hzIx3uuitYoGZt5SQVTBXOvzMfu48n1rP1E834Aw=="
  },
  "model_profile_sha256": "sha256:32f3b01d4108967ee1e25454c12432ad8a602d84dbb3f8bf075cc776f67ddb92"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-omitted-required-gate.json (sha256:e008f879a72371f365bf55d80730979e1c3427e9a616be26001d6f686693491d) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:7eebbf08bfdfcf8868d6dcc2d36e69f1d8c4fd8b4e6035aad30324830c72d6a9",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:7b9b28600d01155f110ffcb9b9d3675e9c36a430fce42afd68fcf383945f7d84",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "Ks96WcEKf12oR/5csmXbuzhX7IY4RMevI0BuvaLed1toAlidGKzDcA5aB+BT2WvZifhkAbTgAIcQZbzx9p3vAg=="
        },
        "acceptance_gate_manifest_sha256": "sha256:bd336f6e090e33a90c38f30cb0e578205c9f7a66dc4a14aff94a9b3804f78a2a"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "visible-unit",
        "command_sha256": "sha256:a824c32f8f1d4c4d1f478369e905590c87d45c9510f330230352e5a23b07ecde",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "tq7GR6XvTo+NMm5RjIus83iJowTcAujPp3JE8rrLuKuuxeIV8eZ2jrfoZWS0QYsI5VrG3yboGbVEo5fQjVQwDg=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "O1Tcr8Y2Bm/5E2MkTxHW+vARPKUho8YolpBZ75I3KwciMkFVfwozJQnpeVYYN5e3yDrGLbOJgqvXw/mrJgOSAA=="
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-ordinary-unsigned-review.json (sha256:96411d484cabc725b3c04267e3eec9125f989cec2b1e0fa3bdcfdece017e5fab) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:13eb8efe444d1001fb049a182c434f814f6db5d875f826f0ca5c87cb98fd808e",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:f3447aa484d08b58c90ba210e133ad305097d64435a16dc941aa973b398d1b16",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "oxh3p9NtfimA2dpZ65Lhszb5cIa5wQ3RQuJuEK16UIQ6i4DdS1WA5PY7dG81Nw9VJGWYMZseryqZYGd3HfphDg=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-review-reuses-execution-attempt.json (sha256:e0e06bdb2703bcb393aacc320ef21dc41edc051f1bc0beecb397bf13f8e3b721) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting",
    "acceptance_semantics"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human@1",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
      "review_sha256": "sha256:ea2b4c5f8d2de4406bf3311e71e3b7deec9aef72e94ac4ccfc5624cd4484263c",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "zlY4MMjqsSl32TiEOFvPMl2gJb3T289GcPvOgyljkiBRW7BAUB3kfaoUBZXYW/9OeMzNvfUwH/XhO3GWLywDCQ=="
        },
        "raw_review_sha256": "sha256:e324180f285d1fa2104fce12da78493a07ca86830b151d92533b0561fcb328c2",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:a0e872386d0c1e3872851e22cf3deea57b4659adad97adfc8d4e96a6dc08655a"
      }
    },
    {
      "decision": "accepted",
      "reviewer_profile": "claude-opus-review@1",
      "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
      "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
      "review_sha256": "sha256:e6e9c143fdb29ffe9ce36c8826d5ab358f6077884277b904f88719815c65e8dd",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
        "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
        "reviewer_profile": "claude-opus-review@1",
        "provider": "anthropic",
        "resolved_model": "claude-opus-5",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "S2LgQTUmkeQ8W4UOrRtesF9itAr+o+ojMoN9auKnxNusvnTcrg1lggAdk6alLKdF0sT3uE984hsep9TrusaUBw=="
        },
        "raw_review_sha256": "sha256:7b83d2aa432be8b2542d0bf2456b4b3cec1a20140d9afd7a7781c9431a1d3802",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:a0e872386d0c1e3872851e22cf3deea57b4659adad97adfc8d4e96a6dc08655a"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
    "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
    "profile": "human@1",
    "model": {
      "provider": "operator",
      "resolved_model": "human",
      "adapter_version": "n/a"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "AisXqac6EDm7xbo+DtebW+O1wfGBgrj4PQYo7bfg4n7DuP1zzBKA8inBbyne9LZ7DBMB4PQ8H3anB5zYtFnIBw=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2",
    "ticket_acceptance_contract": {
      "schema": "factory.ticket-acceptance/v1",
      "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
      "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
      "attestation": {
        "key_id": "factory-harness-review-v1",
        "algorithm": "ed25519",
        "signature_b64": "9BAAUYT5CAjkNwUAz/GYUBKIwj4viII2yEVU6qNdJMn8lcj/JE3YKcRu1xcaBongZbW8YrSPBy0HNJwLMcETDA=="
      }
    }
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "Rtx7VtOxoqRhbOSYznSdmR6Ryva6YCqK7c91QSlyCWC/HT/lHY+DC9WVB43L0/vKpzww/HteOYD+p04y1AOuDg=="
  },
  "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-provenance-review-subject-replay.json (sha256:4723d4fa9064f7a2cd6f273dd1aa682881b13817f3260a8563888893ed82b991) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:abfe15d1422bd29f2faca02e7e3249ab8931e5ef752b39607890ccfdb4f047bd",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:b38eb1c2dd0adb1b1f74563db586d27a459ba07477c682bdc8a262ca2eef8541",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "EI6APKXQDX070SUafby6T+crPxC0UWvJ+6994IciBuBmKoCPPegPLsnqABRRJdkVuqYd7e2HWpOu3snDyBdYCA=="
        },
        "acceptance_gate_manifest_sha256": "sha256:f3a8717fadd97116bec4d659dbfd59023a2d5d43bc01a2299c99db91bfde2861",
        "review_subject_sha256": "sha256:99e408c079c89d231ca74443b0ac22cf29f742ca36f2653d33e1264a41bb1d1b"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:abfe15d1422bd29f2faca02e7e3249ab8931e5ef752b39607890ccfdb4f047bd",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "+Wc1DB4qxtAkWOPin+AYtn/j+5RoQAzYvHPuQJhbeKyLLK0sw5cPhkc+jAtRiJGnPUy643iD9VXtG+OGvJF9Cg=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "2CL5rHzGI+t72l0wRlsBnXAwZ1tF6PaRiHwX0RT3hVgJ6i4yiIVlV+L7pjiJK+XcMUe0aF+/3HkH6YL15rMcCg=="
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/invalid-rca-model-profile-no-counterfactual.json (sha256:eb7e1e9834bf4472c2febbdcd270559740b065c9d5e2365a757249a833b16ed2) ---
{
  "schema": "factory.root-cause-analysis/v1",
  "incident_id": "inc-002",
  "provenance_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "primary_cause": "model_profile",
  "evidence": [
    "A visible test passed."
  ],
  "corrective_ticket_ids": [],
  "status": "open"
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-child-profile-readonly-tools.json (sha256:936221dd2253abed4911d8e630af4d222b6eecf32054d5374a598f46bb101061) ---
{
  "schema": "factory.model-profile/v1",
  "id": "valid-readonly-child",
  "version": "1.0.0",
  "extends": "staged-baseline@1.0.0",
  "adapter": {
    "adapter_id": "claude-staged-v1",
    "executable": "claude -p",
    "allowed_tools": [
      "read_file",
      "grep"
    ],
    "filesystem": "read-only",
    "network": "none"
  },
  "routing": {},
  "telemetry": {}
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-execution-receipt-over-threshold.json (sha256:aea7cc1e536c6ad450b8761a36a91cf9b77a223e66f2287cc6ec6a29005cb350) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:be00f577990cbf3c1c55f63154860ca16a2a5a9cfa9bd70a3decf2be541713c6",
  "ticket_id": "ticket:sha256:b508140c60455823bfe6e61b3c8f8f128cb60d46a5bf8a14400c92ea2e9fa1b2",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 510000,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 510000,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {},
    "post_change": {}
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 510001,
    "status": "reflection_opened",
    "reflection_ticket_id": "ticket:sha256:9749c0ca3102c8a1a609eb193af7c66bad40d6056843103f225b642c23a098fb"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "sRu52Dm4K4ztL4AXC1/GsVPjK53tj0ViIRuf0g9Hc3A8Wjor2LRqrOYLzMuRrZF7BLWJM6FXCNGxNESRVU1YBw=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:fbcaae16932edb3c09406f7c1945561b8f4384ebc7600f7d3765a6640a7f46e0"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:b508140c60455823bfe6e61b3c8f8f128cb60d46a5bf8a14400c92ea2e9fa1b2",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e",
  "ticket_acceptance_contract": {
    "schema": "factory.ticket-acceptance/v1",
    "ticket_id": "ticket:sha256:b508140c60455823bfe6e61b3c8f8f128cb60d46a5bf8a14400c92ea2e9fa1b2",
    "acceptance_gate_manifest_sha256": "sha256:d9a579c757dc4fca34e12a6154b3864258268065daddac8f757e676838b6c2d1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "Xn8VAcmWR0f2/4mYwx7nNmXfbebBkjDhsC+Z8GM3lPK5Wc3BcAjounLhzOWsPNVSLHSbInYn6+j8iFSAxa/pDA=="
    }
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-execution-receipt.json (sha256:80cda1bc2eec48437a312a64f1ae3d505f6475c9a40c4ab94f2c17ebcdb62f58) ---
{
  "schema": "factory.execution-receipt/v1",
  "attempt_id": "attempt:sha256:12b6697b4daf538d57e967eeb8a1229f169521f79df2f7ecb6af7fd974e73a25",
  "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
  "profile": "qwen-prepared-direct@1.0.0",
  "model": {
    "provider": "local",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "source_revision": "abc123",
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model_calls": [
    {
      "id": "call-1",
      "raw_counters": {
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": {
          "availability": "unavailable",
          "reason": "provider does not report reasoning"
        },
        "provider_cost_usd": {
          "availability": "unavailable",
          "reason": "local provider has no invoice"
        },
        "elapsed_ms": 20
      }
    }
  ],
  "telemetry": {
    "input_tokens": 10,
    "output_tokens": 2,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": {
      "availability": "unavailable",
      "reason": "provider does not report reasoning"
    },
    "provider_cost_usd": {
      "availability": "unavailable",
      "reason": "local provider has no invoice"
    },
    "elapsed_ms": 20
  },
  "tool_counts": {
    "tool_calls": 0,
    "need_requests": 0,
    "repair_calls": 0
  },
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "changed_paths": [
    "scripts/paragraph/reparse.py"
  ],
  "scope": {
    "baseline": {
      "mapped": 1
    },
    "post_change": {
      "mapped": 2
    }
  },
  "gates": [
    {
      "id": "fixture-gate",
      "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "outcome": "passed"
    }
  ],
  "budget_checkpoint": {
    "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
    "ordinary_target_effective_tokens": 200000,
    "warning_reflection_effective_tokens": 500000,
    "effective_tokens": 12,
    "status": "within_target"
  },
  "recorded_by": "factory-harness/v1",
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "2l9FRGe3txDpJYZjtB7qMMb5bzlEMth5uVYl/g3a38aVZRxY1y7X3fTid/3ezkGgOeDYzMERjRINMIVF/xf6AA=="
  },
  "outcome": "accepted",
  "root_ids": [
    "ticket:sha256:e59b591878013479c9fd1f1d42e8fd01e070667a9df48ae5e5cefda3e9389bdd"
  ],
  "result_commit": "abc1234",
  "acceptance_gate_manifest": {
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
      }
    ]
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e",
  "ticket_acceptance_contract": {
    "schema": "factory.ticket-acceptance/v1",
    "ticket_id": "ticket:sha256:4a574b58f4c35dbcfe3a14dd654231e911a78bb330fd98976edc2d7314db924e",
    "acceptance_gate_manifest_sha256": "sha256:ca450633a43468ff426a4e7c9ef76ffdfd68450ef79315b44563498477ba7c69",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "pZI9u+hqIMN0Zsoj2VZipmeOlKJT/JtBQ1apGWRjyi4c0o9RUjc/I/WUfWjhS8xCBcq+OSpY0Wv8lJiKbbgwBw=="
    }
  }
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-provenance-high-impact.json (sha256:7395a9fa2a11e608d447a6a91395c03c49f8aa1d0d1c8332ad741a150aa74e3b) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
  "root_ids": [
    "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
  ],
  "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
  "change_class": "factory",
  "contract_change_scope": "high_impact",
  "affected_contract_areas": [
    "token_cost_accounting",
    "acceptance_semantics"
  ],
  "reviewed_package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "human@1",
    "resolved_model": "human",
    "adapter_version": "n/a"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "codex-sol-review@1",
      "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
      "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
      "review_sha256": "sha256:a72b98fd713d56817e8615c9ddcf840b09f4286c305dffaf3271afcc5bff456b",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:9cb45c44f1e8e5410abad0be23d4296afad691a605d308dee702a94990ee5034",
        "review_attempt_id": "attempt:sha256:4bce3b5689a34a58c8005aa2bf949edf3ed1bb870bd3fb22d598b9e2d8f81d16",
        "reviewer_profile": "codex-sol-review@1",
        "provider": "openai",
        "resolved_model": "gpt-5.6-sol",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "Em+gwDUptmGZu1gBlU1h1QbHC0eEC/OCKT5Tm0OFsdDf6UAN/IwbjbbbA28oxPhb9haSrF6OJTAzzGNafh6gAg=="
        },
        "raw_review_sha256": "sha256:e324180f285d1fa2104fce12da78493a07ca86830b151d92533b0561fcb328c2",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:a0e872386d0c1e3872851e22cf3deea57b4659adad97adfc8d4e96a6dc08655a"
      }
    },
    {
      "decision": "accepted",
      "reviewer_profile": "claude-opus-review@1",
      "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
      "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
      "review_sha256": "sha256:e6e9c143fdb29ffe9ce36c8826d5ab358f6077884277b904f88719815c65e8dd",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:75899635121aa897dda5f56b061b749d6210b55da5e3ccf7a387dd57d428c2a9",
        "review_attempt_id": "attempt:sha256:f57fc2572c7e53a389153c78ab629644a291e1d1d297969e0e9996f209b7985a",
        "reviewer_profile": "claude-opus-review@1",
        "provider": "anthropic",
        "resolved_model": "claude-opus-5",
        "package_sha256": "sha256:7ce46af1a52f756b09bf3140b72b8321127dd05f6f027dc65defb509e7e48590",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "S2LgQTUmkeQ8W4UOrRtesF9itAr+o+ojMoN9auKnxNusvnTcrg1lggAdk6alLKdF0sT3uE984hsep9TrusaUBw=="
        },
        "raw_review_sha256": "sha256:7b83d2aa432be8b2542d0bf2456b4b3cec1a20140d9afd7a7781c9431a1d3802",
        "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
        "review_subject_sha256": "sha256:a0e872386d0c1e3872851e22cf3deea57b4659adad97adfc8d4e96a6dc08655a"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:af9c9c2c0795bed2b4deb6488f87a763b762c8ce788d3295fb8e85e6d0152009",
    "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
    "profile": "human@1",
    "model": {
      "provider": "operator",
      "resolved_model": "human",
      "adapter_version": "n/a"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "docs/factory-ng/change-provenance-and-rca-contract-v1.md"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "AisXqac6EDm7xbo+DtebW+O1wfGBgrj4PQYo7bfg4n7DuP1zzBKA8inBbyne9LZ7DBMB4PQ8H3anB5zYtFnIBw=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:eacd2e712b8ea2f9c93087bc0394b9015d09a4f0dda57f224a2e7dd729e4dca8"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2",
    "ticket_acceptance_contract": {
      "schema": "factory.ticket-acceptance/v1",
      "ticket_id": "ticket:sha256:3efc56a8a0866dceafcc4a521cbb5d7c0fe1c888d39e45267f1e582fcbd5dd4a",
      "acceptance_gate_manifest_sha256": "sha256:106c74b2676db395240b65c18efaae7fa4172cb250e53206564b01c18057f0ef",
      "attestation": {
        "key_id": "factory-harness-review-v1",
        "algorithm": "ed25519",
        "signature_b64": "9BAAUYT5CAjkNwUAz/GYUBKIwj4viII2yEVU6qNdJMn8lcj/JE3YKcRu1xcaBongZbW8YrSPBy0HNJwLMcETDA=="
      }
    }
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "C37Yxfy/AU3vaRi2glZ5SibB5QQDVfByenphqfiTJuOniQyJyw1hr2li8QCz8etP8hEP98tX3L6qXXB8uTnRAg=="
  },
  "model_profile_sha256": "sha256:2e11ac845e422b5d38ed70c64877f5e4a0e4123e4a755b4eb30ca4911fb6efd2"
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-provenance-refactor-qwen-review.json (sha256:edb7ec4b4e6aa49a4e572829ec00ff474af8efd75e97cfc8db813a59c184a596) ---
{
  "schema": "factory.change-provenance/v1",
  "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
  "root_ids": [
    "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
  ],
  "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
  "change_class": "refactor",
  "contract_change_scope": "none",
  "source_revision": "abc123",
  "result_commit": "abc1234",
  "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "model": {
    "profile": "qwen-prepared-direct@1.0.0",
    "resolved_model": "qwen",
    "adapter_version": "1.0.0"
  },
  "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "telemetry": {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "provider_cost_usd": 0,
    "elapsed_ms": 1
  },
  "changed_paths": [
    "backend/cards/converter.go"
  ],
  "scope_measurement": {
    "baseline": {},
    "post_change": {}
  },
  "gate_receipts_sha256": "sha256:a3249a18529cf4d65c365c3a30a3ca8aecb5586860582fd7eabea74ca7036210",
  "reviews": [
    {
      "decision": "accepted",
      "reviewer_profile": "qwen-independent-review@1",
      "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
      "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
      "review_sha256": "sha256:6adce3dcf488c28a76b54e6df4e0b4f99b05bbb59505fea979b549ca89a44cff",
      "review_receipt": {
        "schema": "factory.review-receipt/v1",
        "review_id": "review:sha256:e2d85a7d1db63e384d87469f594a62202b037545edf31bf0f6f723305cbae51c",
        "review_attempt_id": "attempt:sha256:60e4fca42430a245cb097a978e28c7c1b5de2de872e66cf9d4e99368ac0c4400",
        "reviewer_profile": "qwen-independent-review@1",
        "provider": "local",
        "resolved_model": "qwen",
        "package_sha256": "sha256:c1938cd0eb1933d1cecf50bab9b196245baaeff043a4a4f7099d92be1367f9d0",
        "decision": "accepted",
        "recorded_by": "factory-harness/v1",
        "raw_review_sha256": "sha256:6f2dd1fc59f7e77f54af469a88f6271047922a79c0e25ae24191c4ff0a9e71b0",
        "attestation": {
          "key_id": "factory-harness-review-v1",
          "algorithm": "ed25519",
          "signature_b64": "8fBR4N7ZzFzDiZzOc4f38XU9sGogMCljPuFsWE9X8uJrcZKLIUXXXnbYAeEyShR/Mzmn3IPDXyqRUGakAFj+AQ=="
        },
        "acceptance_gate_manifest_sha256": "sha256:f3a8717fadd97116bec4d659dbfd59023a2d5d43bc01a2299c99db91bfde2861",
        "review_subject_sha256": "sha256:da2a2921d12e662bf73decdb3b80899b1c1739f23e3dce0507cf62776ca96923"
      }
    }
  ],
  "outcome": "accepted",
  "execution_receipt": {
    "schema": "factory.execution-receipt/v1",
    "attempt_id": "attempt:sha256:d0edae9a14ca0a55543044497c50bce14535937dca2f4a4ca0438f75932468f6",
    "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
    "profile": "qwen-prepared-direct@1.0.0",
    "model": {
      "provider": "local",
      "resolved_model": "qwen",
      "adapter_version": "1.0.0"
    },
    "source_revision": "abc123",
    "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "adapter_command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "model_calls": [
      {
        "id": "bound-fixture-call",
        "raw_counters": {
          "input_tokens": 1,
          "output_tokens": 1,
          "cache_read_tokens": 0,
          "cache_write_tokens": 0,
          "reasoning_tokens": 0,
          "provider_cost_usd": 0,
          "elapsed_ms": 1
        }
      }
    ],
    "telemetry": {
      "input_tokens": 1,
      "output_tokens": 1,
      "cache_read_tokens": 0,
      "cache_write_tokens": 0,
      "reasoning_tokens": 0,
      "provider_cost_usd": 0,
      "elapsed_ms": 1
    },
    "tool_counts": {
      "tool_calls": 0,
      "need_requests": 0,
      "repair_calls": 0
    },
    "patch_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
    "changed_paths": [
      "backend/cards/converter.go"
    ],
    "scope": {
      "baseline": {},
      "post_change": {}
    },
    "gates": [
      {
        "id": "fixture-gate",
        "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
        "outcome": "passed"
      }
    ],
    "budget_checkpoint": {
      "calculation": "input_tokens + output_tokens; cache/read-write and reasoning counters retained separately to avoid double-counting",
      "ordinary_target_effective_tokens": 200000,
      "warning_reflection_effective_tokens": 500000,
      "effective_tokens": 2,
      "status": "within_target"
    },
    "recorded_by": "factory-harness/v1",
    "attestation": {
      "key_id": "factory-harness-review-v1",
      "algorithm": "ed25519",
      "signature_b64": "/v+EyR6OztegeKDi6s/htWkYi/Pop7y7kDxvTFj8pNBOE1BMmjhmJfZvC8v7I3ZtROH4ydTLINvbBQTSW2vdBQ=="
    },
    "outcome": "accepted",
    "root_ids": [
      "ticket:sha256:7201819707c82660b39cbb196ff07cdfeecf943b3c7a9d6b2125e72736a0e1a5"
    ],
    "result_commit": "abc1234",
    "acceptance_gate_manifest": {
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "evidence_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "skill_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
      "gates": [
        {
          "id": "fixture-gate",
          "command_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124"
        }
      ]
    },
    "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e",
    "ticket_acceptance_contract": {
      "schema": "factory.ticket-acceptance/v1",
      "ticket_id": "ticket:sha256:d8ac83c663a3258a39f177780f6d840706497ac1c47da22d1da575eaadf08022",
      "acceptance_gate_manifest_sha256": "sha256:f3a8717fadd97116bec4d659dbfd59023a2d5d43bc01a2299c99db91bfde2861",
      "attestation": {
        "key_id": "factory-harness-review-v1",
        "algorithm": "ed25519",
        "signature_b64": "4P6/+hETqusZGvmh9QZc58OExPuqEapEKphVsVWeQNSVX1x3hDcoDrYrTjtjfEgWK+9PJcDk0eCqLFPlOcKhBw=="
      }
    }
  },
  "attestation": {
    "key_id": "factory-harness-review-v1",
    "algorithm": "ed25519",
    "signature_b64": "hYL94+xdgQjKzwnSR8aScpsr2aT6CRjxKw16NDDafL6KJYz551LR1ZcT0V6KnoBFWyiIMT2hT7mGCjfQyBNZAg=="
  },
  "model_profile_sha256": "sha256:db12b731a010832db032bd354f47cac81a710e05f822e484e3e7809df309b35e"
}


--- FILE: docs/factory-ng/fixtures/contract-review/valid-rca-model-profile.json (sha256:b43fd68c11591cb042067f87cdf7909ba54f31e6543d2576494d3f064e3a5201) ---
{
  "schema": "factory.root-cause-analysis/v1",
  "incident_id": "inc-001",
  "provenance_sha256": "sha256:67e9bc3cfd2163c2978358dfe00d2f912cd4ee0c99f077c3583b39b48aebb124",
  "primary_cause": "model_profile",
  "evidence": [
    "Hidden holdout fails despite correct ticket and evidence pack."
  ],
  "model_profile_causal_claim": true,
  "counterfactual_evidence": [
    "Independent reproduction with a compliant patch passes the same holdout."
  ],
  "corrective_ticket_ids": [
    "ticket:sha256:a6b471b7ca9f21b1e203b480b2d7c46332fd0e6e8064e37e4d11e5c4666878be"
  ],
  "status": "open"
}
