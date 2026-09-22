"""Explicit operator resolution still binds accepted evidence and patch content."""
import contextlib
import io
import json
import sys
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('integrator',Path(__file__).with_name('factory-ng-integrate.py'))
integrator=importlib.util.module_from_spec(spec);spec.loader.exec_module(integrator)

class ResolutionTest(unittest.TestCase):
    def test_binding_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.patch';new=root/'new.patch'
            old.write_text('original');new.write_text('resolved')
            observation={'ticket':{'sha256':'ticket-hash'},'execution':{'candidate_patch':'old.patch','candidate_patch_sha256':integrator.digest(old)}}
            resolution={'original_patch_sha256':integrator.digest(old),'ticket_sha256':'ticket-hash','patch':'new.patch','patch_sha256':integrator.digest(new),'source_revision':'base','reason':'Reviewed insertion collision'}
            calls=[]
            def git(cwd,*args,**kwargs):
                calls.append(args)
                return {'exit_code':1 if args[:3]==('apply','--reverse','--check') else 0,'stdout':'','stderr':'','elapsed_ms':1}
            with patch.object(integrator,'OPS',root),patch.object(integrator,'git',side_effect=git):
                gates=[];integrator.apply_candidate(observation,root,gates,resolution)
                self.assertIn(('am','--3way',str(new)),calls)
                self.assertEqual(gates[0]['id'],'operator-reviewed-resolution')
                for field in ('original_patch_sha256','ticket_sha256','patch_sha256'):
                    with self.subTest(field=field),self.assertRaises(RuntimeError):
                        integrator.apply_candidate(observation,root,[],dict(resolution,**{field:'wrong'}))
                new.write_text('tampered')
                with self.assertRaises(RuntimeError):integrator.apply_candidate(observation,root,[],resolution)

    def test_resolution_is_not_selected_implicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.patch';old.write_text('original')
            observation={'execution':{'candidate_patch':'old.patch','candidate_patch_sha256':integrator.digest(old)}}
            calls=[]
            def git(cwd,*args,**kwargs):
                calls.append(args)
                return {'exit_code':1 if args[:3]==('apply','--reverse','--check') else 0,'stdout':'','stderr':'','elapsed_ms':1}
            with patch.object(integrator,'OPS',root),patch.object(integrator,'git',side_effect=git):
                integrator.apply_candidate(observation,root,[])
            self.assertIn(('am','--3way',str(old)),calls)

    def test_reviewed_wave_checks_final_composition_and_fails_closed(self):
        self.check_composed_waves(reviewed=True)

    def test_automatic_wave_checks_final_composition_and_fails_closed(self):
        self.check_composed_waves(reviewed=False)

    def check_composed_waves(self, reviewed):
        for count, failing in ((1, False), (2, False), (2, True), (3, False)):
            with self.subTest(count=count, failing=failing, reviewed=reviewed), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source';(source/'corpus').mkdir(parents=True)
                (source/'corpus/AtomicCards.json.gz').write_bytes(b'corpus')
                policy=root/'policy.json';policy.write_text(json.dumps({'integration':{'automatic':True}}))
                manifest=root/'manifest.json';manifest.write_text(json.dumps({'schema':'factory.reviewed-merge-resolutions/v1','resolutions':{'ticket:one/v1':{'reviewed':True}}}))
                args=['integrate']
                if reviewed:
                    args+=['--reviewed-resolutions',str(manifest)]
                for i in range(count):
                    obs=root/('obs%d.json'%i)
                    obs.write_text(json.dumps({'schema':'factory.observation-receipt/v1','outcome':'accepted','ticket':{'id':'ticket:item%d/v1'%i}}))
                    args+=['--receipt',str(obs)]
                events=[];commands=[]
                def git(cwd,*args,**kwargs):
                    commands.append(args)
                    if args[0]=='clone':
                        (Path(args[-1])/'corpus').mkdir(exist_ok=True)
                    return {'exit_code':0,'stdout':'a'*40,'stderr':'','elapsed_ms':1}
                def apply(obs,clone,gates,resolution=None):events.append(('apply',obs['ticket']['id']))
                def semantic(obs,clone,gates):
                    events.append(('semantic',obs['ticket']['id']))
                    # A later patch invalidates the first ticket: checking its
                    # earlier prefix is insufficient to protect publication.
                    return not (failing and obs['ticket']['id']=='ticket:item0/v1')
                def call(*args,**kwargs):return {'exit_code':0,'stdout':'','stderr':'','elapsed_ms':1}
                with contextlib.ExitStack() as stack:
                    for name,value in [('OPS',root),('SOURCE',source),('RUNS',root/'runs'),('POLICY',policy)]:stack.enter_context(patch.object(integrator,name,value))
                    stack.enter_context(patch.object(integrator,'source_problem',return_value=None))
                    stack.enter_context(patch.object(integrator,'lock',side_effect=lambda name, **kwargs:io.StringIO()))
                    stack.enter_context(patch.object(integrator,'git',side_effect=git))
                    stack.enter_context(patch.object(integrator,'apply_candidate',side_effect=apply))
                    stack.enter_context(patch.object(integrator,'semantic_gates',side_effect=semantic))
                    stack.enter_context(patch.object(integrator,'call',side_effect=call))
                    cached=stack.enter_context(patch.object(integrator,'cached_gate',side_effect=lambda *a,**kw:call()))
                    stack.enter_context(patch.object(sys,'argv',args));stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    result=integrator.main()
                self.assertEqual([e[0] for e in events[:count]],['apply']*count, [p.read_text() for p in (root/'runs').glob('*.json')])
                self.assertEqual(result,1 if failing else 0)
                if failing:
                    self.assertFalse(any(c[0]=='merge' for c in commands))
                    self.assertEqual(cached.call_count,0)
                    receipt=json.loads(next((root/'runs').glob('*.json')).read_text())
                    self.assertEqual(receipt['outcome'],'full_gate_failed')
                    self.assertFalse(receipt['source']['pushed'])
                else:
                    self.assertEqual(sum(e[0]=='semantic' for e in events),count)
                    self.assertIn('full-sharded-suite',[c.args[0] for c in cached.call_args_list])

if __name__=='__main__':unittest.main()
