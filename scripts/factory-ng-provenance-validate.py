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
BINDING_SKILLS = OPS / 'docs/factory-ng/binding-skills-v1.json'


def load(path):
    return json.loads(path.read_text())


def registered_adapter_paths():
    paths = set()
    for profile_path in (OPS / 'docs/factory-ng/model-profiles/v1').glob('*.json'):
        executable = load(profile_path).get('adapter', {}).get('executable', '')
        if executable.startswith('scripts/'):
            paths.add(executable)
    return paths


def binding_skill_paths():
    """Return the versioned, path-pinned set of Skills that bind workers."""
    return {entry['path'] for entry in load(BINDING_SKILLS)['skills']}


def derived_contract_areas(paths):
    """Classify paths independently of producer-supplied change labels."""
    areas = set()
    adapters = registered_adapter_paths()
    skills = binding_skill_paths()
    for path in paths:
        areas.update(FACTORY_CONTRACT_PATHS.get(path, set()))
        if path.startswith(FACTORY_NG_PREFIX) and not path.startswith(FACTORY_NG_NON_CONTRACT_PREFIXES):
            areas.add('acceptance_semantics')
        if path.startswith(FACTORY_SCRIPT_PREFIX) and path not in FACTORY_SCRIPT_NON_CONTRACTS:
            areas.add('acceptance_semantics')
        if path in adapters:
            areas.add('integration_authority')
        if path in skills:
            areas.add('skill_contract')
        if path.startswith(FACTORY_CONTRACT_PREFIXES) or path in FACTORY_CONTRACT_FILES:
            if path.startswith('docs/factory-ng/model-profiles/v1/'):
                areas.add('model_profile')
            elif path.startswith('docs/factory-ng/review-attestation-keys/'):
                areas.add('integration_authority')
            elif path.startswith('docs/factory-ng/fixtures/contract-review/'):
                areas.add('acceptance_semantics')
            else:
                areas.add('provenance_rca')
    return areas


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
    derived_areas = derived_contract_areas(record.get('changed_paths', []))
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
