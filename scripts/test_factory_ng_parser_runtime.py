import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

from factory_ng_parser_runtime import PatternCache, prepare_parser, corpus_snapshot, parser_code_stamp
from factory_ng_producer_cache import ProducerCache


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'scripts/paragraph').mkdir(parents=True)
        (self.root / 'corpus').mkdir()
        (self.root / 'backend/data/carddb').mkdir(parents=True)
        self.code = self.root / 'scripts/paragraph/reparse.py'; self.code.write_text('# parser\n')
        self.keywords = self.root / 'corpus/Keywords.json'; self.keywords.write_text('{}')
        self.shard = self.root / 'backend/data/carddb/a.json'
        self.card = {'name': 'A', 'status': 'review', 'type': 'Land', 'sub_types': ['Desert'], 'text': 'Draw a card.'}
        self.shard.write_text(json.dumps({'A': self.card}))
        self.cache = ProducerCache(self.root / 'cache.sqlite3'); self.addCleanup(self.cache.close)

    def parser(self):
        return types.SimpleNamespace(REGISTERED={'draw'}, __file__=str(self.code))

    def test_regex_public_operations_flags_groups_bytes_and_callbacks(self):
        facade = PatternCache(4)
        for pattern, string in [(r'(a+)', 'Aa ab'), (b'(a+)', b'aa ab'), (re.compile('(a+)'), 'aa ab')]:
            for name in ('match', 'fullmatch', 'search'):
                a = getattr(re, name)(pattern, string); b = getattr(facade, name)(pattern, string)
                self.assertEqual(None if a is None else (a.span(), a.groups()), None if b is None else (b.span(), b.groups()))
            for name in ('split', 'findall'):
                self.assertEqual(getattr(re, name)(pattern, string), getattr(facade, name)(pattern, string))
            self.assertEqual([m.span() for m in re.finditer(pattern, string)], [m.span() for m in facade.finditer(pattern, string)])
            for name in ('sub', 'subn'):
                self.assertEqual(getattr(re, name)(pattern, lambda m:m[0], string, count=1),
                                 getattr(facade, name)(pattern, lambda m:m[0], string, count=1))
        self.assertEqual(facade.findall('a', 'Aa', re.I), ['A','a'])
        with self.assertRaises(ValueError):facade.compile(re.compile('a'), re.I)
        with self.assertRaises(re.error):facade.compile('[')
        for i in range(20):facade.compile(str(i))
        self.assertLessEqual(facade.cached_compile.cache_info().currsize, 4)
        for _ in range(2):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):facade.compile('a',re.DEBUG)
            self.assertTrue(out.getvalue())

    def test_only_parser_modules_receive_facade(self):
        parser = types.ModuleType('fixture_parser');parser.__file__=str(self.code);parser.re=re
        other = types.ModuleType('unrelated');other.__file__=str(self.root/'outside.py');other.re=re
        with mock.patch.dict(sys.modules, fixture_parser=parser, unrelated=other):
            prepare_parser(self.root, parser, self.cache)
        self.assertIsInstance(parser.re,PatternCache)
        self.assertIs(other.re,re)
        self.assertIs(sys.modules['re'],re)

    def test_fingerprint_tracks_inputs_but_not_commit_tests_or_card_status(self):
        _,first,_=prepare_parser(self.root,self.parser(),self.cache)
        (self.root/'scripts/paragraph/test_example.py').write_text('# unrelated test')
        self.card['status']='auto';self.shard.write_text(json.dumps({'A':self.card}))
        _,same,_=prepare_parser(self.root,self.parser(),self.cache)
        self.assertEqual(first,same)
        for path,content in [(self.code,'# changed parser'),(self.keywords,'{"changed":true}'),
                             (self.root/'scripts/paragraph/support.py','# new imported support')]:
            path.write_text(content)
            _,changed,_=prepare_parser(self.root,self.parser(),self.cache)
            self.assertNotEqual(same,changed);same=changed
        parser=self.parser();parser.REGISTERED.add('new_effect')
        _,changed,_=prepare_parser(self.root,parser,self.cache);self.assertNotEqual(same,changed)
        self.card['sub_types']=['Forest'];self.shard.write_text(json.dumps({'A':self.card}))
        _,changed2,_=prepare_parser(self.root,parser,self.cache);self.assertNotEqual(changed,changed2)

    def test_shard_edit_replacement_and_removal_visible_after_reopen(self):
        cards,stamp=corpus_snapshot(self.root,self.cache);self.assertEqual(cards[0][0],'A')
        self.cache.checkpoint()
        reopened=ProducerCache(self.root/'cache.sqlite3')
        try:
            with mock.patch.object(Path,'read_text',side_effect=AssertionError('unchanged shard reread')):
                self.assertEqual(corpus_snapshot(self.root,reopened)[0],cards)
        finally:reopened.close()
        st=self.shard.stat();self.card['text']='Mill a card.';self.shard.write_text(json.dumps({'A':self.card}))
        os.utime(self.shard,ns=(st.st_atime_ns,st.st_mtime_ns))
        self.assertEqual(corpus_snapshot(self.root,self.cache)[0][0][1]['text'],'Mill a card.')
        self.assertEqual(corpus_snapshot(self.root,self.cache)[1],stamp)
        replacement=self.shard.with_suffix('.new');self.card['text']='Replacement text.'
        replacement.write_text(json.dumps({'A':self.card}));replacement.replace(self.shard)
        self.assertEqual(corpus_snapshot(self.root,self.cache)[0][0][1]['text'],'Replacement text.')
        self.shard.unlink();self.assertEqual(corpus_snapshot(self.root,self.cache)[0],[])

    def test_exact_vocab_tables_reused_across_processes(self):
        calls=[]
        def parser():
            p=self.parser();p._SUBTYPE_VOCAB=None;p._LAND_SUBTYPE_VOCAB=None;p._SUBTYPE_WORDS_CACHE=None
            def vocab():calls.append('vocab');p._SUBTYPE_VOCAB={'desert':'Desert','extra':'Extra'}
            def land(_):calls.append('land');p._LAND_SUBTYPE_VOCAB={'Desert'}
            def words():calls.append('words');p._SUBTYPE_WORDS_CACHE={'desert'}
            p.subtype_vocab=vocab;p.subtype_is_land=land;p._subtype_words=words
            return p
        p=parser();_,stamp,_=prepare_parser(self.root,p,self.cache)
        other=ProducerCache(self.root/'cache.sqlite3')
        try:
            p2=parser();_,stamp2,_=prepare_parser(self.root,p2,other)
        finally:other.close()
        self.assertEqual(calls,['vocab','land','words']);self.assertEqual(stamp,stamp2)
        self.assertEqual(p2._SUBTYPE_VOCAB,p._SUBTYPE_VOCAB)
        self.assertEqual(p2._LAND_SUBTYPE_VOCAB,p._LAND_SUBTYPE_VOCAB)

    def test_parse_results_shared_across_lanes_and_unrelated_revisions(self):
        spec=importlib.util.spec_from_file_location('scan_producer',Path(__file__).with_name('factory-ng-produce-build-plan.py'))
        p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
        parser=self.parser();parser.reparse_card=mock.Mock(return_value={'misses':[]})
        cards,stamp,_=prepare_parser(self.root,parser,self.cache)
        args=(self.root,parser,[],{}, {}, self.cache)
        p.discover_fresh_example(*args,revision='commit-one',snapshot=cards,parser_stamp=stamp)
        p.discover_fresh_example(*args,revision='commit-two',snapshot=cards,parser_stamp=stamp,lane='repair')
        p.discover_fresh_example(*args,revision='commit-two',snapshot=cards,parser_stamp=stamp,max_misses=6)
        self.assertEqual(parser.reparse_card.call_count,1)
        self.card['text']='A changed clause.';self.shard.write_text(json.dumps({'A':self.card}))
        cards,stamp2,_=prepare_parser(self.root,parser,self.cache)
        self.assertEqual(stamp,stamp2)
        p.discover_fresh_example(*args,revision='commit-three',snapshot=cards,parser_stamp=stamp2)
        self.assertEqual(parser.reparse_card.call_count,2)

    def test_ticket_history_is_cached_but_live_jobs_and_versions_are_not_stale(self):
        spec=importlib.util.spec_from_file_location('producer',Path(__file__).with_name('factory-ng-produce-build-plan.py'))
        p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
        tickets=self.root/'tickets';tickets.mkdir();jobs=self.root/'jobs.json';jobs.write_text('{"jobs":{}}')
        t=tickets/'one.json';t.write_text(json.dumps({'id':'ticket:map.a/v1','production':{'key':'key'},'large_payload':'irrelevant'}))
        h=p.production_history(tickets,jobs,self.cache)
        self.assertEqual(p.next_ticket_id(tickets,'map.a',h),'ticket:map.a/v2')
        jobs.write_text(json.dumps({'jobs':{'ticket:map.a/v1':{'state':'completed'}}}))
        original=Path.read_text
        def read(path,*a,**kw):
            if path==t:raise AssertionError('unchanged ticket reread')
            return original(path,*a,**kw)
        with mock.patch.object(Path,'read_text',read):h=p.production_history(tickets,jobs,self.cache)
        self.assertEqual(h['key'][0]['state'],'completed')
        (tickets/'two.json').write_text(json.dumps({'id':'ticket:map.a/v7','supersedes':'ticket:map.a/v1'}))
        h=p.production_history(tickets,jobs,self.cache)
        self.assertTrue(h['key'][0]['superseded']);self.assertEqual(p.next_ticket_id(tickets,'map.a',h),'ticket:map.a/v8')

if __name__=='__main__':unittest.main()
