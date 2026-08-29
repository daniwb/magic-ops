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


def validate_provenance(fixture_name, must_pass, expected_error=None):
    result = subprocess.run(
        ['python3', str(OPS / 'scripts/factory-ng-provenance-validate.py'), str(FIXTURES / fixture_name)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if (result.returncode == 0) != must_pass:
        expectation = 'pass' if must_pass else 'fail'
        raise AssertionError('%s must %s provenance relationship validation: %s' % (fixture_name, expectation, result.stderr))
    if expected_error and expected_error not in result.stderr:
        raise AssertionError('%s must fail for %r, got: %s' % (fixture_name, expected_error, result.stderr))


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


def validate_binding_skill_path_evasion():
    spec = importlib.util.spec_from_file_location('factory_ng_provenance_validate_test', OPS / 'scripts/factory-ng-provenance-validate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = load(FIXTURES / 'skill-path-evasion.json')['changed_paths']
    if 'skill_contract' not in module.derived_contract_areas(paths):
        raise AssertionError('a path-pinned binding Skill must be classified as a Factory contract change')


def main():
    validate_review_package_fixture_coverage()
    validate_external_trust_material_binding()
    validate_binding_skill_path_evasion()
    validate('factory.root-cause-analysis-v1.schema.json', 'valid-rca-model-profile.json', True)
    validate('factory.root-cause-analysis-v1.schema.json', 'invalid-rca-model-profile-no-counterfactual.json', False)
    validate('factory.root-cause-analysis-v1.schema.json', 'invalid-rca-unsupported-model-profile-claim.json', False)
    validate('factory.root-cause-analysis-v1.schema.json', 'invalid-rca-empty-counterfactual-evidence.json', False)
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
    validate_provenance('invalid-provenance-review-gate-manifest-replay.json', False, 'accepted review receipt does not bind the execution acceptance-gate manifest')
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
    validate_provenance('invalid-provenance-review-subject-replay.json', False, 'does not bind the exact reviewed execution subject')
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-execution-profile-replay.json', True)
    validate_provenance('invalid-provenance-execution-profile-replay.json', False, 'accepted provenance model_profile_sha256 does not bind its harness execution receipt')
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-model-profile-content-replay.json', True)
    validate_provenance('invalid-provenance-model-profile-content-replay.json', False, 'execution receipt does not bind the registered Model Profile artifact')
    validate('factory.change-provenance-v1.schema.json', 'invalid-provenance-high-impact-duplicate-raw-review.json', True)
    validate_provenance('invalid-provenance-high-impact-duplicate-raw-review.json', False, 'high-impact accepted reviews reuse one raw review artifact')
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
