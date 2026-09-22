#!/usr/bin/env python3
"""Knowledge retrieval regressions with real HTTP, SQLite and Go parsing."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from factory_ng_knowledge import (search, resolve_candidate, describe, lookup_context,
                                 discover_capability, capability_queries, capability_assessment)
from factory_ng_symbols import symbols, resolve
from factory_ng_context import requested_context

OPS=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,OPS/'scripts'/name)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class KnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.repo=Path(self.tmp.name)/'repo'; self.repo.mkdir()
        self.game=self.repo/'backend/game'; self.game.mkdir(parents=True)
        self.file=self.game/'draw.go'
        self.file.write_text('''package game
// DrawCardsWithEvent is mentioned here before its declaration.
type GameState struct{}
type Player struct{}
// DrawCardsWithEvent draws cards and fires an event for every draw.
func (gs *GameState) DrawCardsWithEvent(n int) { _ = "}" }
func (p *Player) DrawCards(n int) {}
// handleTrackCardsDrawn records the cards drawn this turn.
func (gs *GameState) handleTrackCardsDrawn() {}
func amount(kind string) int {
 switch kind {
 case "cards_drawn_this_turn": return 1
 case "other": return 0
 }
 return 0
}
// AddCounters places counters on a creature.
func AddCounters() {}
''')
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Test','-c','user.email=test@local','commit','-qm','fixture'],check=True)
        self.service=load('card-knowledge-service.py')
        self.service.REPO=str(self.repo); self.service.DB=str(Path(self.tmp.name)/'kb.db')
        self.service.TRACE_PATH=str(Path(self.tmp.name)/'service.jsonl')
        db,self.service.COUNTS=self.service.build_index(); db.close()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.service.H)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True); thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.base='http://127.0.0.1:%d'%self.server.server_port

    def test_draw_alias_finds_event_entrypoint_and_qualified_identity(self):
        result=search('draw_cards','test',kind='engine',base=self.base)
        names=[r['qualified'] for r in result['candidates']]
        self.assertEqual(names[0],'game.GameState.DrawCardsWithEvent')
        self.assertIn('game.Player.DrawCards',names)
        self.assertNotIn('game.AddCounters',names)

    def test_missing_generated_label_still_discovers_named_existing_parts(self):
        result=discover_capability({'key':'invented_missing_feature', 'specification':{
            'required_behavior':'Use DrawCardsWithEvent and AddCounters for the existing parts.'}},
            'test', base=self.base)
        self.assertEqual(result['lookups'][0]['status'],'not_found')
        self.assertEqual(result['status'],'found')
        self.assertEqual(result['semantic_coverage'],'unverified')
        names={r['name'] for r in result['candidates']}
        self.assertTrue({'DrawCardsWithEvent','AddCounters'}.issubset(names))
        self.assertLessEqual(len(result['lookups']),6)
        self.assertTrue(all('discovery_role' in r for r in result['lookups']))

    def test_query_plan_does_not_send_whole_requirement_or_unbounded_words(self):
        plan=capability_queries({'key':'damage_recipient_attacked_target','specification':{
            'required_behavior':'Check resolveRecipientFromEventCard and CastSpellWithTargets; '+ 'ordinary prose '*100}})
        self.assertIn(('damage','operation_only'),plan)
        self.assertIn(('resolveRecipientFromEventCard','requirement_symbol'),plan)
        self.assertLessEqual(len(plan),5)
        self.assertTrue(all('ordinary prose' not in q for q,_ in plan))

    def test_assessment_is_a_claim_not_a_semantic_gate(self):
        reply='CAPABILITY_ASSESSMENT: '+json.dumps({'classification':'reuse','existing_symbols':['game.DrawCards'],
            'remaining_gap':'none','verification':'TestShape_Draw public path'})
        self.assertEqual(capability_assessment(reply)['status'],'worker_claim_requires_gates')
        self.assertIsNone(capability_assessment('VERDICT: AMBIGUOUS'))
        self.assertEqual(capability_assessment('CAPABILITY_ASSESSMENT: {bad}')['status'],'invalid')

    def test_map_packet_receives_current_engine_source_after_dependency(self):
        candidate=search('DrawCardsWithEvent','test',kind='engine',base=self.base)['candidates'][0]
        self.file.write_text('// moved\n'*15+self.file.read_text().replace('_ = "}"','_ = "current handoff"'))
        paragraph=self.repo/'scripts/paragraph'; paragraph.mkdir(parents=True)
        (paragraph/'reparse.py').write_text('def map_atom(*args, **kwargs): return None\ndef load_card(name): return {"text":"Draw a card."}\ndef reparse_card(card): return {"eligible":True,"misses":[]}\n')
        ticket=Path(self.tmp.name)/'map.json'
        ticket.write_text(json.dumps({'schema':'factory.ticket-spec/v1','work_type':'map','id':'ticket:test/v1','title':'handoff',
            'evidence':[{'path':candidate['path'],'symbol':candidate}], 'scope':{'allowed_paths':[]},
            'execution':{'parser_probes':[{'function':'reparse_card','card':'Test'}]}}))
        result=subprocess.run(['python3',str(OPS/'scripts/map-ticket-spec-pack.py'),'--ticket-spec',str(ticket),'--repo',str(self.repo)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('current handoff',result.stdout)
        self.assertIn('func (gs *GameState) DrawCardsWithEvent',result.stdout)
        self.assertIn('read-only evidence',result.stdout)

    def test_history_fallback_is_explicit_and_keeps_topic_together(self):
        first=search('cards_drawn_this_turn_counter_amount','test',kind='engine',base=self.base)
        self.assertEqual(first['status'],'not_found')
        result=search('cards_drawn_this_turn_counter_amount','test',kind='engine',base=self.base,fallback=True)
        self.assertEqual(result['strategy'],'explicit_leading_terms')
        self.assertTrue(any(r['name']=='cards_drawn_this_turn' for r in result['candidates']))
        self.assertFalse(any(r['name']=='AddCounters' for r in result['candidates']))
        self.assertTrue(all(' OR ' not in q for q in result['fts_queries']))

    def test_resolution_uses_changed_checkout_not_indexed_lines_or_body(self):
        row=search('DrawCardsWithEvent','test',kind='engine',base=self.base)['candidates'][0]
        self.file.write_text('// inserted\n'*80+self.file.read_text().replace('_ = "}"','_ = "current body"'))
        resolved=resolve(self.repo,row)
        self.assertEqual(resolved['start'],row['start']+80)
        self.assertIn('current body',resolved['excerpt'])
        self.assertNotIn('mentioned here',resolved['excerpt'])
        self.assertTrue(resolved['sha256'].startswith('sha256:'))

    def test_deleted_symbol_is_unresolved_not_an_arbitrary_window(self):
        row=search('DrawCardsWithEvent','test',kind='engine',base=self.base)['candidates'][0]
        self.file.write_text('package game\nfunc Different() {}\n')
        self.assertEqual(resolve(self.repo,row)['status'],'unresolved')

    def test_source_does_not_escape_checkout(self):
        self.assertEqual(symbols(self.repo,['../../etc/passwd']),[])
        (self.game/'escape.go').symlink_to('/etc/passwd')
        self.assertEqual(symbols(self.repo,['backend/game/escape.go']),[])

    def test_trace_records_query_candidates_selection_revision_and_actual_excerpt(self):
        trace=Path(self.tmp.name)/'attempt.jsonl'
        with lookup_context({'KB_TRACE_FILE':str(trace),'KB_TICKET':'ticket:test/v1','KB_ATTEMPT':'attempt-1'}):
            lookup=search('draw_cards','packet',kind='engine',base=self.base)
            resolve_candidate(self.repo,lookup['candidates'][0],lookup['request_id'],'packet')
        events=[json.loads(line) for line in trace.read_text().splitlines()]
        self.assertEqual(events[0]['request']['q'],'draw_cards')
        self.assertEqual(events[0]['ticket'],'ticket:test/v1')
        self.assertEqual(events[1]['request_id'],events[0]['request']['request_id'])
        self.assertIn('DrawCardsWithEvent',events[1]['resolution']['excerpt'])
        service_event=json.loads(Path(self.service.TRACE_PATH).read_text().splitlines()[0])
        self.assertEqual(service_event['request']['attempt'],'attempt-1')

    def test_service_error_and_search_miss_are_distinct(self):
        miss=search('DefinitelyAbsentSymbol','test',base=self.base)
        error=search('DrawCards','test',base='http://127.0.0.1:1')
        self.assertEqual(miss['status'],'not_found')
        self.assertEqual(error['status'],'service_error')
        self.assertIn('does not establish',describe(miss))
        self.assertIn('not evidence',describe(error))

    def test_producer_uses_service_and_resolves_real_declaration(self):
        producer=load('factory-ng-produce-capability-dependency.py')
        with mock.patch.object(producer,'SOURCE',self.repo),mock.patch.dict(os.environ,{'KB_URL':self.base}):
            result=producer.knowledge_hits({'key':'cards_drawn_this_turn_counter_amount'})
        self.assertTrue(any(r.get('symbol',{}).get('name')=='cards_drawn_this_turn' for r in result))
        self.assertTrue(all(r.get('lookup_trace') for r in result))
        self.assertTrue(all(r.get('sha256') for r in result))

    def test_need_uses_same_declaration_resolver(self):
        text=requested_context('NEED: backend/game/draw.go: DrawCardsWithEvent',self.repo)
        self.assertIn('func (gs *GameState) DrawCardsWithEvent',text)
        self.assertNotIn('mentioned here',text)

    def test_failed_refresh_retains_previous_snapshot(self):
        with mock.patch.object(self.service,'_build_index',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError): self.service.build_index()
        result=search('DrawCardsWithEvent','test',base=self.base)
        self.assertEqual(result['status'],'found')

    def test_new_revision_refreshes_discovery_on_request(self):
        self.file.write_text(self.file.read_text()+'\nfunc BrandNewOperation() {}\n')
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Test','-c','user.email=test@local','commit','-qam','new symbol'],check=True)
        result=search('BrandNewOperation','test',base=self.base)
        self.assertEqual(result['status'],'found')
        self.assertFalse(result['index_stale'])

    def test_qualified_query_selects_one_receiver(self):
        self.file.write_text(self.file.read_text()+'\nfunc (gs *GameState) DrawCards(n int) {}\n')
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Test','-c','user.email=test@local','commit','-qam','second receiver'],check=True)
        db,_=self.service.build_index(); db.close()
        result=search('game.Player.DrawCards','test',base=self.base)
        self.assertEqual([c['qualified'] for c in result['candidates']],['game.Player.DrawCards'])

    def test_mcp_source_tool_reads_current_worker_checkout(self):
        mcp=load('kb-mcp-server.py')
        row=search('DrawCardsWithEvent','test',base=self.base)['candidates'][0]
        with mock.patch.object(mcp.Path,'cwd',return_value=self.repo):
            response=mcp.handle({'id':1,'method':'tools/call','params':{'name':'read_source','arguments':{'symbol_id':row['symbol_id']}}})
        self.assertIn('func (gs *GameState)',response['result']['content'][0]['text'])

    def test_producer_defers_when_service_is_down(self):
        producer=load('factory-ng-produce-capability-dependency.py')
        with mock.patch.dict(os.environ,{'KB_URL':'http://127.0.0.1:1'}):
            with self.assertRaisesRegex(RuntimeError,'defer production'):
                producer.knowledge_hits({'key':'draw_cards'})


if __name__=='__main__': unittest.main()
