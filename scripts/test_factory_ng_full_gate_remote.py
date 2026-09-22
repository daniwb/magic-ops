"""Full-gate result binding, confined patch import, and fallback behavior."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import factory_ng_full_gate_remote as remote


class FullGateRemoteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clone = self.root / 'source'; self.clone.mkdir()
        remote.git(self.clone, 'init', '-q')
        remote.git(self.clone, 'config', 'user.name', 'Test')
        remote.git(self.clone, 'config', 'user.email', 'test@local')
        self.card = self.clone / 'backend/data/carddb/a.json'; self.card.parent.mkdir(parents=True)
        self.card.write_text('{"old":true}\n'); (self.clone / 'engine.go').write_text('original\n')
        remote.git(self.clone, 'add', '.'); remote.git(self.clone, 'commit', '-qm', 'base')
        self.commands = [(name, ['check', name], 1800) for name in ['reparse-flip','reparse-import','go-build','game-tests','focused-go','full-sharded-suite']]
        self.manifest = {'revision': remote.git(self.clone,'rev-parse','HEAD'),
                         'tree': remote.git(self.clone,'rev-parse','HEAD^{tree}'), 'commands': self.commands}
        self.out = self.root / 'out'; self.out.mkdir()
        self.result = {'schema': 'factory.remote-full-gate/v1', 'manifest_sha256':'manifest-hash',
                       'input_revision': self.manifest['revision'], 'input_tree': self.manifest['tree'],
                       'outcome':'passed', 'gates':[{'id':key,'command':' '.join(argv),'outcome':'passed',
                                                  'exit_code':0,'elapsed_ms':1} for key,argv,_ in self.commands]}
        self.card.write_text('{"new":true}\n')
        self.make_patch()
        self.enterContext(patch.object(remote, 'STATUS', self.root / 'status.json'))

    def make_patch(self):
        remote.git(self.clone, 'add', '-A')
        data=remote.invoke(['git','-C',self.clone,'diff','--cached','--binary','--full-index','HEAD']).encode()
        (self.out/'carddb.patch').write_bytes(data)
        self.result.update(patch_sha256=remote.digest(data),result_tree=remote.git(self.clone,'write-tree'))
        remote.git(self.clone,'reset','--hard',self.manifest['revision'])
        self.save()

    def save(self): (self.out/'result.json').write_text(json.dumps(self.result))
    def receive(self): return remote.import_result(self.clone,self.out,self.manifest,'manifest-hash')
    def assert_clean(self):
        self.assertEqual(remote.git(self.clone,'status','--porcelain'),'')
        self.assertEqual(remote.git(self.clone,'rev-parse','HEAD'),self.manifest['revision'])

    def test_real_git_patch_roundtrip_binds_generated_tree_without_commit(self):
        self.receive()
        self.assertEqual(self.card.read_text(),'{"new":true}\n')
        self.assertEqual(remote.git(self.clone,'write-tree'),self.result['result_tree'])
        self.assertEqual(remote.git(self.clone,'rev-parse','HEAD'),self.manifest['revision'])

    def test_rejects_missing_gate_and_changed_command(self):
        self.result['gates'].pop(); self.save()
        with self.assertRaisesRegex(ValueError,'missing required'): self.receive()
        self.assert_clean()
        self.result['gates'][0]['command']='skip everything'; self.save()
        with self.assertRaisesRegex(ValueError,'command or order'):self.receive()

    def test_rejects_wrong_manifest_input_tree_and_patch_hash(self):
        for key in ['manifest_sha256','input_revision','input_tree','patch_sha256']:
            with self.subTest(key=key):
                old=self.result[key];self.result[key]='wrong';self.save()
                with self.assertRaises(ValueError):self.receive()
                self.assert_clean();self.result[key]=old

    def test_wrong_result_tree_rolls_back_before_fallback(self):
        self.result['result_tree']='wrong';self.save()
        with self.assertRaisesRegex(ValueError,'generated tree mismatch'):self.receive()
        self.assert_clean();self.assertEqual(self.card.read_text(),'{"old":true}\n')

    def test_rejects_patch_outside_carddb_even_with_matching_hash_and_tree(self):
        (self.clone/'engine.go').write_text('malicious\n');self.make_patch()
        with self.assertRaisesRegex(ValueError,'outside card data'):self.receive()
        self.assert_clean();self.assertEqual((self.clone/'engine.go').read_text(),'original\n')

    def test_rejects_symlink_generated_file(self):
        self.card.unlink();self.card.symlink_to('../../../engine.go');self.make_patch()
        with self.assertRaisesRegex(ValueError,'paths or modes'):self.receive()
        self.assert_clean();self.assertFalse(self.card.is_symlink())

    def test_red_gate_is_preserved_and_never_falls_back_to_hide_failure(self):
        self.result['gates']=self.result['gates'][:3]
        self.result['gates'][-1].update(outcome='failed',exit_code=1)
        self.result['outcome']='failed';self.save();self.receive();self.assert_clean()
        local=Mock(return_value=True);gates=[]
        with patch.object(remote,'execute_remote',return_value=self.result):
            passed,execution=remote.run_with_fallback(self.clone,gates,'tag',self.settings(),local_runner=local,commands=self.commands)
        self.assertFalse(passed);local.assert_not_called();self.assertEqual(len(gates),3)
        self.assertEqual(execution['full_gate_host'],'test@host')

    def settings(self):return {'integration':{'remote':{'enabled':True,'host':'test@host','image':'pinned','cpus':[0,1],'go_parallelism':2}}}

    def test_transport_failure_falls_back_and_backs_off_next_attempt(self):
        local=Mock(return_value=True)
        with patch.object(remote,'execute_remote',side_effect=OSError('offline')) as execute:
            for _ in range(2):
                passed,execution=remote.run_with_fallback(self.clone,[],'tag',self.settings(),local_runner=local,commands=self.commands)
                self.assertTrue(passed);self.assertEqual(execution['full_gate_host'],'local');self.assert_clean()
        self.assertEqual(execute.call_count,1);self.assertEqual(local.call_count,2)

    def semantic_prefix(self):
        spec={'id':'composed-ticket-2','command':'python3 check.py','ticket_id':'ticket:a/v1'}
        self.manifest['semantic_gates']=[spec]
        self.result['gates'].insert(0,dict(spec,outcome='passed',exit_code=0,elapsed_ms=1))
        self.save()

    def test_semantic_contract_cannot_be_omitted_or_reassigned(self):
        self.semantic_prefix()
        self.result['gates'][0]['ticket_id']='ticket:other/v1';self.save()
        with self.assertRaisesRegex(ValueError,'semantic gate identity'):self.receive()
        self.result['gates'].pop(0);self.save()
        with self.assertRaisesRegex(ValueError,'semantic gate identity'):self.receive()
        self.assert_clean()

    def test_semantic_failure_blocks_full_gate_and_patch_import(self):
        self.semantic_prefix()
        self.result['gates']=self.result['gates'][:1]
        self.result['gates'][0].update(outcome='failed',exit_code=1)
        self.result['outcome']='failed';self.save()
        self.assertEqual(self.receive()['outcome'],'failed');self.assert_clean()

    def test_changed_semantic_measurement_rejects_remote_acceptance(self):
        self.semantic_prefix()
        relative='docs/factory-ng/measurements/input.json'
        path=self.root/relative;path.parent.mkdir(parents=True);path.write_text('original')
        self.manifest['input_hashes']={relative:remote.digest(path.read_bytes())}
        path.write_text('changed')
        with patch.object(remote,'OPS',self.root):
            with self.assertRaisesRegex(ValueError,'semantic input changed'):self.receive()
        self.assert_clean()

    def test_cache_retry_must_pass_the_same_command(self):
        original=self.result['gates'][2]
        retry=dict(original,id=original['id']+'-cache-retry',classification='isolated_cache_retry')
        original.update(outcome='infrastructure_retry',exit_code=1,classification='cache_artifact_disappeared')
        self.result['gates'].insert(3,retry);self.save();self.receive()
        retry['command']='different'
        with self.assertRaisesRegex(ValueError,'invalid retry'):remote.validate_gates(self.result,self.manifest)

if __name__=='__main__':unittest.main()
