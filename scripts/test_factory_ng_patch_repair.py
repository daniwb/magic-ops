import tempfile
import unittest
from pathlib import Path

from factory_ng_patch_repair import rejected_patch_context, protocol_repair_prompt


class PatchRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'backend/game/effect.go'
        self.path.parent.mkdir(parents=True)

    def reply(self, search):
        return '<<<FILE backend/game/effect.go\n<<<SEARCH\n%s\n===REPLACE\nnew\n>>>END\n' % search

    def test_ambiguous_search_supplies_distinguishing_context_for_both_matches(self):
        self.path.write_text('func First() {\n\told()\n}\n' + '\n' * 40 + 'func Second() {\n\told()\n}\n')
        context = rejected_patch_context(self.root, self.reply('\told()'))
        self.assertIn('func First()', context)
        self.assertIn('func Second()', context)

    def test_wrong_whitespace_gets_exact_source_without_modification(self):
        source = '// header\n' * 500 + 'func Real() {\n\told()\n}\n'
        self.path.write_text(source)
        prompt = protocol_repair_prompt('packet', self.root, self.reply('func Real() {\n    old()\n}'),
                                        'SEARCH text not found', 'codex-constrained@1.1.0')
        self.assertIn('func Real() {\n\told()', prompt)
        self.assertIn('Read-only source tools remain available', prompt)
        self.assertIn('Do not return NEED', prompt)
        self.assertIn('===REPLACE', prompt)
        self.assertEqual(self.path.read_text(), source)

    def test_malformed_delimiters_can_still_identify_source_evidence(self):
        self.path.write_text('func Real() {\n\told()\n}\n')
        reply = self.reply('\told()').replace('===REPLACE', '===').replace('>>>END', '<<<END')
        self.assertIn('func Real()', rejected_patch_context(self.root, reply))

    def test_read_budget_and_symlink_boundary(self):
        self.path.write_text('\n'.join('line%d' % i for i in range(1000)))
        context = rejected_patch_context(self.root, self.reply('line500'), line_budget=20)
        self.assertLessEqual(len(context.splitlines()), 23)
        secret = self.root / 'secret.go'
        secret.write_text('secret value')
        self.path.unlink()
        self.path.symlink_to(secret)
        # Within-repo symlinks remain source_path's existing policy. Escapes do not.
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'secret.go'
            target.write_text('outside secret')
            self.path.unlink()
            self.path.symlink_to(target)
            self.assertEqual(rejected_patch_context(self.root, self.reply('outside secret')), '')

    def test_staged_profile_retains_no_tools_and_final_verdict(self):
        prompt = protocol_repair_prompt('', self.root, '', '', 'claude-staged@1.0.0')
        self.assertIn('no tool calls', prompt)
        self.assertIn('VERDICT: AMBIGUOUS', prompt)


if __name__ == '__main__':
    unittest.main()
