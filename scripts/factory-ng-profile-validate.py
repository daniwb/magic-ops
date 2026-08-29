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
