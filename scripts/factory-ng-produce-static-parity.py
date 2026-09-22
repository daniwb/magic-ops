#!/usr/bin/env python3
"""Produce exact parser parity tickets for static rules with live engine paths."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

from factory_ng_paths import SOURCE

OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / 'docs/factory-ng/tickets'
SKILL = OPS / 'docs/factory-ng/skills/v1/implement-map-class/SKILL.md'
PARSER = 'scripts/paragraph/reparse.py'

# Every entry is an exact Oracle clause family already implemented by the
# native card parser and its associated game path.  We only bridge the
# paragraph reparser; no new engine primitive is implied.
CATEGORIES = {
    'aura-lock': ("enchanted creature can't attack or block", 'cant_attack_or_block',
                  'patternEnchantedCreatureCantAttackOrBlock', 'Pacifism-class Aura lock'),
    'cant-attack-block-alone': ("~ can't attack or block alone", 'cant_attack_or_block_alone',
                                 'patternThisCreatureCantAttackOrBlockAlone', 'Ember Beast-class self restriction'),
    'cant-attack-alone': ("~ can't attack alone", 'cant_attack_alone',
                           'SetCantAttackAlone', 'self attack-alone restriction'),
    'spell-limit': ("each player can't cast more than one spell each turn", 'spell_limit',
                    'patternEachPlayerCantCastMoreThanOneSpellPerTurn', 'one-spell-per-turn rule'),
    'opponents-enter-tapped': ("creatures your opponents control enter tapped", 'opponents_creatures_enter_tapped',
                                'patternOpponentsCreaturesEnterTapped', 'opponent creature entry replacement'),
    'opponents-cant-cast': ("your opponents can't cast spells during your turn", 'opponents_cant_cast_spells',
                             'patternOpponentsCantCastSpellsDuringYourTurn', 'opponent casting restriction'),
    'one-blocker': ("~ can't be blocked by more than one creature", 'cant_be_blocked_by_multiple',
                    'patternThisCreatureCantBeBlockedByMultiple', 'one-blocker combat restriction'),
    'walls-evasion': ("~ can't be blocked by walls", 'cant_be_blocked_by_walls',
                      'patternThisCreatureCantBeBlockedByCreatureType', 'Walls-only evasion restriction'),
    'creature-spells-uncounterable': ("creature spells you control can't be countered", 'creature_spells_cant_be_countered',
                                      'patternCreatureSpellsYouControlCantBeCountered', 'creature-spell counter restriction'),
}
# Batches preserve the exact same semantic family but keep its evidence packet
# and patch surface small enough for the prepared local profile.
for suffix in ('a', 'b', 'c'):
    CATEGORIES['aura-lock-' + suffix] = CATEGORIES['aura-lock']
for suffix in ('a', 'b'):
    CATEGORIES['one-blocker-' + suffix] = CATEGORIES['one-blocker']

def sha(path): return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
def emit(status, ticket_id, **extra):
    print(json.dumps({'schema':'factory.ticket-production/v1','status':status,'ticket_id':ticket_id,**extra}, indent=2, sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--category', choices=sorted(CATEGORIES), required=True)
    ap.add_argument('--repo', type=Path, default=SOURCE); ap.add_argument('--ticket-dir', type=Path, default=TICKETS)
    a=ap.parse_args(); repo=a.repo.resolve(); slug=a.category; phrase,effect,marker,meaning=CATEGORIES[slug]
    ticket_id='ticket:map.static-parity-%s/v1' % slug
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True): ap.error('ground truth must be clean')
    for p in a.ticket_dir.glob('*.json'):
        try:
            if json.loads(p.read_text()).get('id') == ticket_id: emit('duplicate_ticket',ticket_id,ticket_path=str(p)); return
        except (OSError,ValueError): pass
    native=repo/'backend/cards/patterns_static.go'
    if marker not in native.read_text(): emit('runtime_evidence_missing',ticket_id,marker=marker); return
    sys.path.insert(0,str((repo/PARSER).parent)); import reparse
    rows=[]
    for shard in sorted((repo/'backend/data/carddb').glob('*.json')):
        data=json.loads(shard.read_text())
        if not isinstance(data,dict): continue
        for name,card in data.items():
            if not isinstance(card,dict) or card.get('status')!='review': continue
            misses=reparse.reparse_card(card).get('misses',[])
            details=[d for k,d in misses if k=='static_unmapped' and phrase in d.lower()]
            if details:
                rows.append({'name':name,'text_sha256':'sha256:'+hashlib.sha256(card['text'].encode()).hexdigest(),
                             'all_miss_shapes':['static_unmapped'],'details':details})
    if len(rows)<2: emit('no_safe_candidate',ticket_id,member_count=len(rows)); return
    rows.sort(key=lambda row: row['name'])
    if slug.startswith('aura-lock-'):
        part = {'a': 0, 'b': 1, 'c': 2}[slug[-1]]
        rows = [row for index, row in enumerate(rows) if index % 3 == part]
    elif slug.startswith('one-blocker-'):
        part = {'a': 0, 'b': 1}[slug[-1]]
        rows = [row for index, row in enumerate(rows) if index % 2 == part]
    rev=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    measurement_path='docs/factory-ng/measurements/static-parity-%s-v1.json' % slug
    measurement={'schema':'factory.targeted-demand/v1','shape':'static_unmapped','member_count':len(rows),'review_cards_scanned':len(rows),'members':rows,
                 'source':{'repository':str(repo),'revision':rev,'parser_sha256':sha(repo/PARSER)}}
    test='scripts/paragraph/test_static_parity_%s.py' % slug
    ticket={'schema':'factory.ticket-spec/v1','id':ticket_id,'title':'Map exact static parity: %s' % meaning,
      'work_type':'map','lifecycle':'ready_for_observation','parents':['ticket:factory.evidence.static-parity/v1'],
      'production':{'producer':'static-parity-%s' % slug,'key':'static-parity:%s:v1' % slug,'predicted_class_unlock':len(rows)},
      'source':{'repository':str(repo),'revision':rev,'clean':True},
      'skill':{'name':'implement-map-class','path':str(SKILL.relative_to(OPS)),'sha256':sha(SKILL)},
      'scope':{'allowed_paths':[PARSER,test],'forbidden_paths':['backend/','backend/data/','scripts/paragraph/slotparse_oneshot.py']},
      'evidence':[{'path':measurement_path,'fact':'%d pinned cards retain the exact static miss %r.'%(len(rows),phrase)},
        {'path':'backend/cards/patterns_static.go','sha256':sha(native),'fact':'Existing native parser/runtime path %s implements the %s.'%(marker,meaning)}],
      'required_behavior':['Map only the exact static clause family %r to the existing %s behavior.'%(phrase,effect),
        'Every pinned card must lose this exact static_unmapped miss without changing other clauses.',
        'Do not change engine, converter, registry, corpus data, or map any adjacent wording.'],
      'gates':['cd scripts/paragraph && python3 -m unittest test_static_parity_%s'%slug,'git diff --check',
        'git status --porcelain adds or changes only %s and %s'%(PARSER,test),
        'python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/%s reports zero remaining pinned members'%measurement_path],
      'execution':{'mode':'isolated_clone_observation_only','selected_profile':'qwen-prepared-direct@1.0.2',
        'compatible_profiles':['qwen-prepared-direct@1.0.2','claude-staged@1.0.0','codex-constrained@1.1.0'],
        'selection_reason':'Exact static parity over an existing native parser/runtime path.','effective_token_target':200000,'warning_reflection_threshold':500000,'automatic_stop':False,
        'model_may_not_commit_push_deploy_or_mutate_live_tickets':True},
      'on_failure':'Record a receipt; any missing native behavior is a separate Engine TicketSpec.'}
    emit('ready',ticket_id,measurement=measurement,ticket=ticket)
if __name__=='__main__': main()
