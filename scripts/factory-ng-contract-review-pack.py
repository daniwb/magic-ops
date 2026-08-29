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
    'docs/factory-ng/binding-skills-v1.json',
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
