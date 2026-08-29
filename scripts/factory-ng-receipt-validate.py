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
