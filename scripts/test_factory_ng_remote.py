"""Remote evidence import, transport fallback, and confined artifact paths."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_factory_ng_focused_batch as fixtures
import factory_ng_verification as verification


class RemoteVerificationTests(unittest.TestCase):
    def test_bundle_export_recovery_is_bound_to_proposal_manifest_and_one_allowance(self):
        root = self.fixture.root
        entry = self.fixture.proposal('a', 'a.txt', 'new\n')
        result_path = root/'state/factory-ng-job-output/remote.json'
        result_path.parent.mkdir(parents=True)
        member = {'status': 'verification_pending', 'proposal': entry['proposal'],
                  'verification_remote_failed': True,
                  'reason': "Remote verification unavailable; retained for local checks: Command ['git', 'bundle', 'create', 'source.bundle'] timed out after 300 seconds"}
        payload = {'ticket_results': {'a': member}}
        result_path.write_text(json.dumps(payload))
        manifest_path = result_path.with_suffix('.manifest.json'); manifest_path.write_text(json.dumps([entry]))
        job = {'state': 'awaiting_verification', 'ticket_path': entry['ticket_path'],
               'proposal': entry['proposal'], 'result_path': str(result_path.relative_to(root)),
               'worker': entry['identity']['worker'], 'model': entry['identity']['model'],
               'dispatch_profile': entry['identity']['profile'], 'verification_remote_failed': True,
               'attempts': 2, 'verification_attempts': 3, 'failed_profiles': ['historical']}
        for change in ({'state': 'working'}, {'proposal': 'wrong.json'}, {'superseded_by': 'new'}):
            with self.subTest(change=change):
                self.assertEqual(verification.recover_bundle_export_fallbacks(root, {'a': dict(job, **change)}, 'now'), [])
        original_reason = member['reason']; member['reason'] = 'Remote verification unavailable; retained for local checks: SSH unavailable'
        result_path.write_text(json.dumps(payload))
        self.assertEqual(verification.recover_bundle_export_fallbacks(root, {'a': dict(job)}, 'now'), [])
        member['reason'] = original_reason; result_path.write_text(json.dumps(payload))
        manifest_path.write_text(json.dumps([dict(entry, identity=dict(entry['identity'], model='wrong'))]))
        self.assertEqual(verification.recover_bundle_export_fallbacks(root, {'a': dict(job)}, 'now'), [])
        manifest_path.write_text(json.dumps([entry]))
        self.assertEqual(verification.recover_bundle_export_fallbacks(root, {'a': job}, 'now'), ['a'])
        self.assertNotIn('verification_remote_failed', job)
        self.assertEqual((job['attempts'], job['verification_attempts'], job['failed_profiles']), (2, 3, ['historical']))
        self.assertEqual(job['remote_bundle_export_recovery']['result_sha256'], verification.checksum(result_path.read_bytes()))
        job['verification_remote_failed'] = True
        self.assertEqual(verification.recover_bundle_export_fallbacks(root, {'a': job}, 'later'), [])

    def test_incremental_source_bundle_preserves_pinned_commit_and_requires_baseline(self):
        root = self.fixture.root
        source = root/'bundle-source'; source.mkdir()
        def git(repo, *args):
            return subprocess.check_output(['git', '-C', str(repo), *map(str, args)], text=True, stderr=subprocess.PIPE).strip()
        git(source, 'init', '-q')
        (source/'a').write_text('base\n'); git(source, 'add', '.')
        git(source, '-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '-qm', 'base')
        base = git(source, 'rev-parse', 'HEAD')
        mirror = root/'mirror.git'; subprocess.run(['git','clone','--quiet','--bare',str(source),str(mirror)],check=True)
        (source/'a').write_text('new\n')
        git(source, '-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '-qam', 'next')
        revision = git(source, 'rev-parse', 'HEAD')
        staging = root/'bundle-stage'; staging.mkdir()
        with patch.object(self.m, 'SOURCE', source), patch.object(self.m, 'ssh', return_value=base+'\n'):
            self.m.export_source_bundle(staging, revision, self.settings, str(mirror))
        bundle = staging/'source.bundle'
        self.assertIn(base.encode(), bundle.read_bytes().split(b'\n\n', 1)[0])
        empty = root/'empty.git'; subprocess.run(['git','init','--quiet','--bare',str(empty)],check=True)
        result = subprocess.run(['git','-C',str(empty),'bundle','verify',str(bundle)],capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        git(mirror, 'fetch', bundle, 'refs/heads/pinned:refs/heads/snapshot')
        self.assertEqual(git(mirror, 'rev-parse', 'refs/heads/snapshot'), revision)
        self.assertEqual(git(mirror, 'show', revision+':a'), 'new')
        full = root/'full-stage'; full.mkdir()
        with patch.object(self.m, 'SOURCE', source), patch.object(self.m, 'ssh', side_effect=subprocess.CalledProcessError(1, ['git'])):
            self.m.export_source_bundle(full, revision, self.settings, str(mirror))
        git(empty, 'fetch', full/'source.bundle', 'refs/heads/pinned:refs/heads/snapshot')
        self.assertEqual(git(empty, 'rev-parse', 'refs/heads/snapshot'), revision)

    def setUp(self):
        self.fixture = fixtures.FocusedBatchTest(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.m = fixtures.load('factory-ng-verify-remote')
        self.enterContext(patch.object(self.m, 'OPS', self.fixture.root))
        self.enterContext(patch.object(self.m, 'STATUS', self.fixture.root / 'remote-status.json'))
        self.settings = {'host': 'test@owned-host', 'root': '/data/factory-ng', 'image': 'sha256:test'}

    def remote_output(self):
        self.fixture.proposal('a', 'a.txt', 'new\n')
        self.fixture.proposal('b', 'b.txt', 'new-b\n')
        result = self.fixture.verify()
        out = self.fixture.root / 'out'
        out.mkdir()
        for item in result.values():
            receipt_path = self.fixture.root / item['receipt']
            receipt = json.loads(receipt_path.read_text())
            for relative in [item['receipt'], receipt['execution']['candidate_patch']]:
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(self.fixture.root / relative, target)
        (out / 'result.json').write_text(json.dumps({'ticket_results': result}))
        return out, result

    def test_corrected_proposal_exports_repair_evidence_with_hashes_and_history(self):
        root = self.fixture.root
        entry = self.fixture.proposal('a', 'a.txt', 'new\n')
        artifact = root/'docs/factory-ng/runs/repair.json'
        artifact.parent.mkdir(parents=True); artifact.write_text('{"result":"bounded correction"}')
        value = json.loads((root/entry['proposal']).read_text())
        value['context'] = {'model_calls': 2, 'telemetry': {'bounded_repair_attempted': True},
                            'attempt_history': [{'stage': 'before_gate_repair', 'gates': [{'outcome': 'failed'}]}],
                            'repair_artifacts': [{'path': str(artifact.relative_to(root)),
                                'sha256': verification.checksum(artifact.read_bytes()), 'kind': 'gate_repair'}]}
        (root/entry['proposal']).write_text(json.dumps(value))
        accepted = self.fixture.verify()['a']
        receipt = json.loads((root/accepted['receipt']).read_text())
        self.assertEqual(receipt['attempt_history'], value['context']['attempt_history'])
        self.assertEqual(receipt['model']['telemetry']['model_calls'], 2)
        self.assertIn(value['context']['repair_artifacts'][0], receipt['raw_artifacts'])
        (root/'scripts').mkdir(); (root/'scripts/fixture.py').write_text('# fixture')
        policy = root/'export-policy.json'; policy.write_text('{"integration":{}}')
        staging = root/'export'; staging.mkdir()
        with patch.object(self.m, 'POLICY', policy):
            self.m.export_job([entry], staging, dict(self.settings, cpus=[0, 1]))
        relative = str(artifact.relative_to(root))
        self.assertEqual((staging/'ops'/relative).read_bytes(), artifact.read_bytes())
        self.assertEqual(json.loads((staging/'input-checksums.json').read_text())[relative],
                         verification.checksum(artifact.read_bytes()))
        artifact.write_text('changed after proposal publication')
        another = root/'export-again'; another.mkdir()
        with self.assertRaisesRegex(ValueError, 'repair artifact path or hash mismatch'):
            self.m.export_job([entry], another, dict(self.settings, cpus=[0, 1]))

    def test_real_receipts_roundtrip_preserves_all_gates_and_adds_host(self):
        out, results = self.remote_output()
        (self.fixture.root / 'docs/factory-ng/runs').rmdir()
        payload = self.m.import_results(self.fixture.entries, out, self.settings)
        self.assertEqual(payload['ticket_results'], results)
        for item in results.values():
            receipt = json.loads((self.fixture.root / item['receipt']).read_text())
            self.assertEqual(receipt['execution']['verification_host'], self.settings['host'])
            self.assertEqual(len(receipt['execution']['verified_ticket_ids']), 2)

    def test_invalid_member_prevents_publication_of_entire_batch(self):
        out, results = self.remote_output()
        receipt_path = out / results['b']['receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['gates'] = [g for g in receipt['gates'] if g['id'] != 'ticket-gate-0']
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'omitted a required gate'):
            self.m.import_results(self.fixture.entries, out, self.settings)
        self.assertFalse(list((self.fixture.root / 'docs/factory-ng/runs').glob('*.json')))

    def test_rejects_corrupt_patch_and_changed_local_input(self):
        out, results = self.remote_output()
        receipt = json.loads((out / results['a']['receipt']).read_text())
        patch_path = out / receipt['execution']['candidate_patch']
        original = patch_path.read_bytes()
        patch_path.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'patch hash mismatch'):
            self.m.import_results(self.fixture.entries, out, self.settings)
        patch_path.write_bytes(original)
        (self.fixture.root / self.fixture.entries[0]['ticket_path']).write_text('{}')
        with self.assertRaises((ValueError, KeyError)):
            self.m.import_results(self.fixture.entries, out, self.settings)

    def test_paths_cannot_escape_artifact_root(self):
        for relative in ('../../private', '/etc/passwd'):
            with self.assertRaises(ValueError):
                self.m.path_under(self.fixture.root, relative)
        (self.fixture.root / 'escape').symlink_to('/etc')
        with self.assertRaises(ValueError):
            self.m.path_under(self.fixture.root, 'escape/passwd')

    def test_transport_failure_preserves_proposal_and_backs_off_host(self):
        entry = self.fixture.proposal('a', 'a.txt', 'new\n')
        with patch.object(self.m, 'export_job', side_effect=OSError('SSH unavailable')), \
             patch.object(self.m, 'ssh'):
            result = self.m.verify([entry], self.settings)['ticket_results']['a']
        self.assertEqual(result['status'], 'verification_pending')
        self.assertEqual(result['proposal'], entry['proposal'])
        self.assertTrue(result['verification_remote_failed'])
        self.assertNotIn('verification_isolate', result)
        self.assertGreater(json.loads(self.m.STATUS.read_text())['retry_after_epoch'], 0)

    def test_failed_composition_gets_remote_isolation_before_local_model_repair(self):
        self.fixture.proposal('a', 'a.txt', 'new\n')
        self.fixture.proposal('b', 'b.txt', 'new-b\n')
        out = self.fixture.root / 'failed-out'; out.mkdir()
        for count in (2, 1):
            entries = self.fixture.entries[:count]
            results = {e['ticket_id']: {'status': 'verification_pending', 'proposal': e['proposal'],
                'verification_isolate': True, 'reason': 'Batch could not pass; verify individually: a failed'} for e in entries}
            (out / 'result.json').write_text(json.dumps({'ticket_results': results}))
            imported = self.m.import_results(entries, out, self.settings)['ticket_results']
            for result in imported.values():
                self.assertEqual(bool(result.get('verification_remote_failed')), count == 1)
                self.assertTrue(result['verification_isolate'])
                self.assertNotIn('receipt', result)

    def test_old_batch_fallback_recovery_is_bound_and_never_resets_attempts(self):
        entry = self.fixture.proposal('a', 'a.txt', 'new\n')
        root = self.fixture.root
        output = root / 'state/factory-ng-job-output/batch.json'; output.parent.mkdir(parents=True)
        result = {'status': 'verification_pending', 'proposal': entry['proposal'],
                  'verification_isolate': True, 'verification_remote_failed': True,
                  'reason': 'Batch could not pass; verify individually: another member failed'}
        output.write_text(json.dumps({'ticket_results': {'a': result, 'other': result}}))
        job = {'state': 'awaiting_verification', 'proposal': entry['proposal'], 'ticket_path': entry['ticket_path'],
               'worker': 'w', 'dispatch_profile': 'p', 'model': 'model', 'attempts': 3,
               'failed_profiles': ['old'], 'verification_isolate': True, 'verification_remote_failed': True,
               'result_path': str(output.relative_to(root))}
        self.assertEqual(verification.recover_remote_batch_fallbacks(root, {'a': job}, 'now'), ['a'])
        self.assertNotIn('verification_remote_failed', job)
        self.assertEqual(job['attempts'], 3); self.assertEqual(job['failed_profiles'], ['old'])
        self.assertEqual(job['proposal'], entry['proposal'])
        self.assertEqual(job['remote_batch_isolation_recovery']['result_sha256'], verification.checksum(output.read_bytes()))
        job['verification_remote_failed'] = True
        self.assertEqual(verification.recover_remote_batch_fallbacks(root, {'a': job}, 'later'), [])
        job.pop('remote_batch_isolation_recovery')
        for change in ('working', 'different-proposal', 'single-member', 'corrupt-proposal'):
            candidate = dict(job)
            output.write_text(json.dumps({'ticket_results': {'a': result, 'other': result}}))
            if change == 'working': candidate['state'] = 'working'
            if change == 'different-proposal': candidate['proposal'] = 'other.json'
            if change == 'single-member': output.write_text(json.dumps({'ticket_results': {'a': result}}))
            if change == 'corrupt-proposal': (root / entry['proposal']).write_text('{}')
            self.assertEqual(verification.recover_remote_batch_fallbacks(root, {'a': candidate}, 'later'), [])
            self.assertTrue(candidate['verification_remote_failed'])

    def test_remote_policy_tracks_manual_switch_without_integration_authority(self):
        target = self.fixture.root / 'export'
        (target / 'config').mkdir(parents=True)
        settings = dict(self.settings, cpus=list(range(8)))
        policy = self.fixture.root / 'controller-policy.json'
        with patch.object(self.m, 'POLICY', policy):
            for enabled in (False, True):
                policy.write_text(json.dumps({'compilation': {'enabled': enabled},
                                              'integration': {'automatic': True},
                                              'resources': {'cpu_affinity': [6, 11, 12, 19]}}))
                self.m.write_remote_policy(target, settings)
                remote = json.loads((target / 'config/factory-ng-policy.json').read_text())
                self.assertEqual(remote['compilation']['enabled'], enabled)
                self.assertFalse(remote['integration']['automatic'])
                self.assertEqual(remote['resources']['cpu_affinity'], list(range(8)))

    def test_export_includes_referenced_measurements_without_unrelated_files(self):
        relative = 'docs/factory-ng/measurements/members.json'
        member = self.fixture.root / relative
        member.parent.mkdir(parents=True)
        member.write_text('{"members": ["example"]}')
        entry = self.fixture.proposal('a', 'a.txt', 'new\n', gates=[
            'python3 measure.py --members-from /opt/development/magic-ops/' + relative])
        (self.fixture.root / 'scripts').mkdir()
        (self.fixture.root / '.env').write_text('PRIVATE=not-exported')
        policy = self.fixture.root / 'controller-policy.json'
        policy.write_text('{"compilation":{"enabled":true},"integration":{"automatic":true}}')
        target = self.fixture.root / 'transport'
        target.mkdir()
        with patch.object(self.m, 'POLICY', policy):
            self.m.export_job([entry], target, dict(self.settings, cpus=[0, 1]))
        self.assertEqual((target / 'ops' / relative).read_bytes(), member.read_bytes())
        self.assertFalse((target / 'ops/.env').exists())
        checksums = json.loads((target / 'input-checksums.json').read_text())
        self.assertEqual(checksums[relative], self.m.checksum(member.read_bytes()))

    def test_changed_measurement_prevents_import(self):
        out, _ = self.remote_output()
        relative = 'members.json'
        member = self.fixture.root / relative
        member.write_text('before')
        checksums = {relative: self.m.checksum(member.read_bytes())}
        member.write_text('after')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.m.import_results(self.fixture.entries, out, self.settings, checksums)


if __name__ == '__main__':
    unittest.main()
