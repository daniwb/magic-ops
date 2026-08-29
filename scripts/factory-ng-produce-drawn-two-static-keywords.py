#!/usr/bin/env python3
"""Produce one exact, runtime-backed static condition Map ticket."""
import argparse, hashlib, json, subprocess
from pathlib import Path

OPS=Path(__file__).resolve().parents[1]; TICKETS=OPS/'docs/factory-ng/tickets'
SKILL=OPS/'docs/factory-ng/skills/v1/implement-map-class/SKILL.md'
TICKET_ID='ticket:map.static-condition-drawn-two-keywords/v3'
PHRASE="you've drawn two or more cards this turn"
MEMBERS=('Foggy Swamp Hunters','Spinehorn Minotaur','Trench Stalker','Gnarled Sage','Evangel of Synthesis','Eyekite')

def sha(p): return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def rev(repo): return subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
def exists(directory):
    for p in directory.glob('*.json'):
        try:
            if json.loads(p.read_text()).get('id')==TICKET_ID:return str(p)
        except (OSError,ValueError):pass

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',type=Path,default=Path('/opt/development/test/openmagic')); ap.add_argument('--ticket-dir',type=Path,default=TICKETS); a=ap.parse_args(); repo=a.repo.resolve()
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True): ap.error('ground-truth checkout must be clean')
    parser=repo/'scripts/paragraph/reparse.py'; runtime=repo/'backend/game/condition.go'
    if 'case "you_drew_cards":' not in runtime.read_text():
        print(json.dumps({'schema':'factory.ticket-production/v1','status':'needs_primitive','ticket_id':TICKET_ID,'reason':'runtime lacks happened/you_drew_cards'})); return
    duplicate=exists(a.ticket_dir)
    if duplicate:
        print(json.dumps({'schema':'factory.ticket-production/v1','status':'duplicate_ticket','ticket_id':TICKET_ID,'ticket_path':duplicate})); return
    rows=[]
    for name in MEMBERS:
        shard=repo/'backend/data/carddb'/(name[0].lower()+'.json'); card=json.loads(shard.read_text())[name]
        if PHRASE not in card.get('text','').lower():
            print(json.dumps({'schema':'factory.ticket-production/v1','status':'ground_truth_changed','ticket_id':TICKET_ID,'card':name})); return
        rows.append({'name':name,'text_sha256':'sha256:'+hashlib.sha256(card['text'].encode()).hexdigest(),'all_miss_shapes':['static_conditional'],'details':[PHRASE]})
    measurement={'schema':'factory.targeted-demand/v1','shape':'static_conditional','member_count':len(rows),'review_cards_scanned':len(rows),'members':rows,'source':{'repository':str(repo),'revision':rev(repo),'parser_sha256':sha(parser)}}
    ticket={'schema':'factory.ticket-spec/v1','id':TICKET_ID,'title':'Map the exact drawn-two-cards static keyword condition','work_type':'map','lifecycle':'ready_for_observation','parents':['ticket:factory.evidence.static-conditional/v1'],'supersedes':'ticket:map.static-condition-drawn-two-keywords/v2','source':{'repository':str(repo),'revision':rev(repo),'clean':True},'skill':{'name':'implement-map-class','path':str(SKILL.relative_to(OPS)),'sha256':sha(SKILL)},'scope':{'allowed_paths':['scripts/paragraph/reparse.py','scripts/paragraph/test_static_condition_drawn_two.py'],'forbidden_paths':['backend/','backend/data/','scripts/paragraph/slotparse_oneshot.py']},'evidence':[{'path':'docs/factory-ng/measurements/static-condition-drawn-two-keywords-v3.json','fact':'Six pinned static keyword/pump cards share the exact drawn-two condition.'},{'path':'backend/game/condition.go','sha256':sha(runtime),'anchor':'483-540','fact':'The existing happened/you_drew_cards runtime condition uses the turn counter and amount.'},{'path':'scripts/paragraph/reparse.py','sha256':sha(parser),'anchor':'10652-10941','fact':'parse_static_condition is the narrow Map seam.'}],'required_behavior':["Map exactly `you've drawn two or more cards this turn` to {kind: happened, what: you_drew_cards, amount: 2}.",'The six pinned cards no longer have a static_conditional miss.','Do not generalize other draw quantities, windows, actors, or effects.','Do not edit Engine, converter, corpus data, or use card-name special cases.'],'gates':['cd scripts/paragraph && python3 -m unittest test_static_condition_drawn_two','git diff --check','git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_drawn_two.py','python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/docs/factory-ng/measurements/static-condition-drawn-two-keywords-v3.json'],'execution':{'mode':'isolated_clone_observation_only','selected_profile':'qwen-prepared-direct@1.0.2','selection_reason':'A six-card, one-tuple parser-only change with a proven runtime representation fits the validated prepared Qwen Map profile.','parser_probes':[{'function':'parse_static_condition','text':PHRASE},{'function':'parse_static_condition','text':"you've drawn one card this turn"},{'function':'parse_static_condition','text':"an opponent has drawn two or more cards this turn"}],'effective_token_target':200000,'warning_reflection_threshold':500000,'automatic_stop':False,'model_may_not_commit_push_deploy_or_mutate_live_tickets':True},'on_failure':'Record a receipt; a missing draw-history behavior is a separate Engine TicketSpec.'}
    print(json.dumps({'schema':'factory.ticket-production/v1','status':'ready','measurement':measurement,'ticket':ticket},indent=2,sort_keys=True))
if __name__=='__main__':main()
