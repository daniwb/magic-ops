import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import factory_ng_qwen_evidence as evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo/'backend/game').mkdir(parents=True)
        (self.repo/'backend/game/zone.go').write_text('package game\ntype Zone struct { Cards []*Card }\nfunc (z *Zone) RemoveCard(cardID string) (*Card, error) { return nil, nil }\n')
        (self.repo/'backend/game/player.go').write_text('package game\ntype Player struct { Library *Zone }\n')
        (self.repo/'backend/cards').mkdir()
        (self.repo/'backend/cards/registry.go').write_text('package cards\ntype Primitive struct { Executor string; ShapeTest string }\nfunc regEffect(name string, p Primitive) {}\n')

    def test_index_hints_are_resolved_in_checkout_and_missing_registry_rows_fall_back(self):
        def search(query, *args, **kwargs):
            if query=='RemoveCard':
                return {'status':'found','candidates':[{'name':'RemoveCard','path':'backend/game/zone.go',
                    'symbol_id':'backend/game/zone.go::game.Zone.RemoveCard','start':999,'signature':'wrong cached signature'}]}
            return {'status':'not_found','candidates':[]}
        with patch.object(evidence, 'search', side_effect=search) as lookup:
            result=evidence.api_evidence(self.repo)
        self.assertEqual(lookup.call_count,8)
        self.assertIn('RemoveCard(cardID string)',result)
        self.assertIn('Library *Zone',result)
        self.assertIn('ShapeTest string',result)
        self.assertIn('regEffect(name string, p Primitive)',result)
        self.assertNotIn('wrong cached signature',result)

    def test_database_outage_uses_local_declarations_without_repeated_http_waits(self):
        with patch.object(evidence, 'search', return_value={'status':'service_error','candidates':[]}) as lookup:
            result=evidence.api_evidence(self.repo)
        self.assertEqual(lookup.call_count,1)
        self.assertIn('Library *Zone',result)

    def test_untrusted_database_path_cannot_escape_read_roots(self):
        with patch.object(evidence, 'search', return_value={'status':'found','candidates':[
            {'name':'Zone','path':'../../secret.go','symbol_id':'../../secret.go::secret.Zone'}]}):
            result=evidence.api_evidence(self.repo)
        self.assertNotIn('secret.go',result)

    def test_enforced_source_line_budget(self):
        with patch.object(evidence,'MAX_LINES',1),patch.object(evidence,'search',return_value={'status':'not_found','candidates':[]}):
            result=evidence.api_evidence(self.repo)
        self.assertEqual(sum(1 for l in result.splitlines() if l[:5].strip().isdigit()),1)

    def test_scope_inventory_exposes_existing_file_and_missing_named_test(self):
        (self.repo/'backend/game/shape_test.go').write_text('package game\nfunc TestWrong(t *testing.T) {}\n')
        ticket={'scope':{'allowed_paths':['backend/game/zone.go','backend/game/shape_test.go']},
                'gates':["cd backend && go test ./game -run '^TestRequired$' -count=1"]}
        result=evidence.scope_inventory(self.repo,ticket)
        self.assertIn('EXISTS (SEARCH/REPLACE only): backend/game/zone.go',result)
        self.assertIn('Required test TestRequired: NOT declared',result)
        (self.repo/'backend/game/shape_test.go').write_text('package game\nfunc TestRequired(t *testing.T) {}\n')
        self.assertIn('Required test TestRequired: declared',evidence.scope_inventory(self.repo,ticket))

if __name__=='__main__':unittest.main()
