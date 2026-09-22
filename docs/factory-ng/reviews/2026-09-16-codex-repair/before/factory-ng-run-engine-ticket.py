#!/usr/bin/env python3
"""Run one bounded Map or Engine TicketSpec through a registered remote profile.

The adapter is read-only; only this harness applies strict edit blocks and
runs the TicketSpec's declared gates.  It records an observation receipt and
never touches the canonical checkout, pushes, or integrates a candidate.
"""
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from factory_ng_receipts import write_receipt
from factory_ng_verification import (VerificationPaused, require_compilation, save_proposal, load_proposal, restore_proposal)
from factory_ng_vocabulary import engine_registration_gate
from factory_ng_context import requested_context, preparation_problems, failure_detail, source_path, render_regions
from factory_ng_knowledge import lookup_context, capability_assessment
from factory_ng_investigation import evidence_gap, investigation_prompt, validate_evidence, EVIDENCE_INSTRUCTIONS
from factory_ng_safety import (source_problem, final_gates_pass, test_json_command,
                               require_executed_test, decoded_output, source_wait_receipt)

OPS = Path(__file__).resolve().parents[1]
SOURCE = Path('/opt/development/test/openmagic')
RUNS = OPS / 'docs/factory-ng/runs'
CANDIDATES = OPS / 'docs/factory-ng/candidates'
AUTHENTICATION_EXIT = 75
OPENROUTER_RATE_LIMIT_EXIT = 76
from factory_ng_provider_failure import CAPACITY_EXIT, CAPACITY_OUTCOME
PROFILE_ENGINES = {
    'claude-staged@1.0.0': 'claude',
    'codex-constrained@1.0.0': 'codex',
    'codex-constrained@1.1.0': 'codex',
    'minimax-prepared-direct@1.0.0': 'openrouter',
    'qwen-prepared-local@1.0.1': 'qwen-agentic',
    'claude-agentic@1.0.0': 'claude-agentic',
    'claude-agentic-test@1.0.0': 'claude-agentic-test',
}
MINIMAX_PROFILE = 'minimax-prepared-direct@1.0.0'
QWEN_AGENTIC_PROFILE = 'qwen-prepared-local@1.0.1'
CLAUDE_AGENTIC_PROFILE = 'claude-agentic@1.0.0'
CLAUDE_AGENTIC_TEST_PROFILE = 'claude-agentic-test@1.0.0'
AGENTIC_PROFILES = (QWEN_AGENTIC_PROFILE, CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE)
# claude-agentic-test is a comparison sibling of claude-agentic (same staged-
# baseline authority, engine loop, and packet contract; adds a PreToolUse
# bulk-read shunt and an okf-agent-memory MCP trial) — everywhere the harness
# special-cases CLAUDE_AGENTIC_PROFILE it must treat this the same way.
CLAUDE_AGENTIC_LIKE_PROFILES = (CLAUDE_AGENTIC_PROFILE, CLAUDE_AGENTIC_TEST_PROFILE)
REMOTE_CONSTRAINED_PROFILES = ('claude-staged@1.0.0', 'codex-constrained@1.0.0')

def digest(value): return 'sha256:' + hashlib.sha256(value).hexdigest()
def file_digest(path): return digest(Path(path).read_bytes())
def stamp(): return time.strftime('%Y-%m-%dT%H%M%SZ', time.gmtime())

def call(command, cwd, stdin=None, timeout=1200, env=None):
    start = time.monotonic()
    try:
        p = subprocess.run(command, cwd=cwd, input=stdin, text=True, capture_output=True,
                           timeout=timeout, env=env)
        return {'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
                'elapsed_ms': round((time.monotonic()-start)*1000)}
    except subprocess.TimeoutExpired as exc:
        return {'exit_code': 124, 'stdout': decoded_output(exc.stdout), 'stderr': decoded_output(exc.stderr) + '\nCommand timed out after %d seconds.' % timeout,
                'elapsed_ms': round((time.monotonic()-start)*1000)}

def counters(stderr, elapsed):
    hit = re.findall(r'tokens: in=(\d+) out=(\d+) cache_r=(\d+) cache_w=(\d+)', stderr)
    if not hit:
        unknown = {'availability':'unavailable', 'reason':'adapter emitted no token counter'}
        return {'input_tokens':unknown,'output_tokens':unknown,'cache_read_tokens':unknown,
                'cache_write_tokens':unknown,'reasoning_tokens':unknown,
                'provider_cost_usd':{'availability':'unavailable','reason':'provider cost unavailable'},'elapsed_ms':elapsed}
    inn,out,read,write = map(int, hit[-1])
    return {'input_tokens':inn,'output_tokens':out,'cache_read_tokens':read,'cache_write_tokens':write,
            'reasoning_tokens':{'availability':'unavailable','reason':'adapter aggregates reasoning into output when applicable'},
            'provider_cost_usd':{'availability':'unavailable','reason':'local adapter has no versioned pricing record'},'elapsed_ms':elapsed}

def merge_telemetry(total, addition):
    for key in ('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','elapsed_ms'):
        if isinstance(total.get(key),int) and isinstance(addition.get(key),int):
            total[key] += addition[key]
        else:
            total[key] = {'availability':'unavailable', 'reason':'at least one model call omitted this counter'}

def repair_available(profile, telemetry):
    # Claude staged declares two patch calls and at most one NEED. A NEED
    # response is context discovery, not a patch proposal. Other qualified
    # profiles keep their existing two-total-call restriction.
    return (not telemetry.get('bounded_repair_attempted') and
            (profile == 'claude-staged@1.0.0' or not telemetry.get('need_continuation_attempted')))


def should_attempt_repair(model, applied, telemetry, profile=None):
    return (model.get('exit_code') == 0 and applied.get('exit_code') in (5, 6) and
            repair_available(profile, telemetry))

def model_environment(raw_artifact, dotenv=None):
    """Build the adapter environment, loading only the gitignored provider key.

    Legacy pipeline lanes source ``.env`` before starting, while Factory NG's
    supervised Python runner does not.  Parse the one required value directly
    so OpenRouter workers behave the same without executing dotenv contents as
    shell code or copying unrelated secrets into the child environment.
    """
    environment = os.environ.copy()
    path = Path(dotenv) if dotenv is not None else OPS / '.env'
    if not environment.get('OPENROUTER_API_KEY') and path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            stripped = line.strip()
            if stripped.startswith('export '):
                stripped = stripped[7:].lstrip()
            name, separator, value = stripped.partition('=')
            if separator and name.strip() == 'OPENROUTER_API_KEY':
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
                    value = value[1:-1]
                if value:
                    environment['OPENROUTER_API_KEY'] = value
                break
    environment['PIPE_RAW_ARTIFACT'] = str(raw_artifact)
    stem = str(raw_artifact)
    for suffix in ('.gate-repair.raw.json','.continuation.raw.json','.repair.raw.json','.raw.json'):
        if stem.endswith(suffix):
            stem=stem[:-len(suffix)]
            break
    environment['KB_TRACE_FILE']=stem+'.lookup.jsonl'
    environment['KB_ATTEMPT']=Path(stem).name
    return environment

def validated_capability(reply):
    """Extract the one atomic Map dependency and revalidate its Oracle facts."""
    module_path = OPS / 'scripts/capability-contract.py'
    spec = importlib.util.spec_from_file_location('factory_ng_capability_contract', module_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    value = module.extract(reply)
    module.validate_oracle(value, str(SOURCE))
    return value

def supports_profile(ticket, profile):
    execution=ticket.get('execution',{})
    compatible=execution.get('compatible_profiles')
    if profile in CLAUDE_AGENTIC_LIKE_PROFILES:
        return False  # Agentic can supply evidence, never implement a Factory ticket.
    if execution.get('profile_policy') == 'exact':
        return isinstance(compatible, list) and profile in compatible
    if profile == 'codex-constrained@1.1.0':
        return (isinstance(compatible, list) and profile in compatible) or supports_profile(ticket, 'codex-constrained@1.0.0')
    if not compatible:
        preferred=execution.get('selected_profile')
        remote=[QWEN_AGENTIC_PROFILE,'claude-staged@1.0.0','minimax-prepared-direct@1.0.0',
                'codex-constrained@1.0.0']
        if ticket.get('work_type')=='engine' or int(ticket.get('production',{}).get('retry_generation',0))>0:
            compatible=[preferred]+remote
        else:
            compatible=[preferred,'qwen-prepared-direct@1.0.2']+remote
    if profile == MINIMAX_PROFILE and ticket.get('work_type') != 'map':
        return False
    if profile == QWEN_AGENTIC_PROFILE and ticket.get('work_type') != 'engine':
        return False
    if profile in compatible:
        return True
    if profile == 'claude-staged@1.0.0' and any(p in CLAUDE_AGENTIC_LIKE_PROFILES for p in compatible):
        return True
    # Preserve immutable pre-registration TicketSpecs while allowing the new
    # qualified no-tools remote profile through the same constrained harness.
    return (((profile == MINIMAX_PROFILE and ticket.get('work_type') == 'map') or
             (profile == QWEN_AGENTIC_PROFILE and ticket.get('work_type') == 'engine')) and
            any(item in compatible for item in REMOTE_CONSTRAINED_PROFILES))

def ticket_gate(command, clone, ticket):
    """Execute the small documented TicketSpec gate shorthands truthfully."""
    started = time.monotonic()
    if ((command.startswith('git status --porcelain ') and ' only ' in command) or
            (command.startswith('git diff --name-only ') and ' only ' in command)):
        names = call(['git','status','--porcelain'],clone,timeout=30)
        changed = [line[3:] for line in names['stdout'].splitlines() if len(line)>3]
        allowed = set(ticket.get('scope',{}).get('allowed_paths',[]))
        ok = bool(changed) and set(changed).issubset(allowed)
        return {'exit_code':0 if ok else 1,'stdout':'changed='+','.join(changed),'stderr':'',
                'elapsed_ms':round((time.monotonic()-started)*1000)}
    suffix = ' reports zero remaining pinned members'
    executable = command[:-len(suffix)] if command.endswith(suffix) else command
    no_output = ' produces no output'
    if executable.endswith(no_output):
        executable = executable[:-len(no_output)]
    shell_command = ['bash','-lc',test_json_command(executable)]
    if re.search(r'\bgo\s+(build|test|vet)\b', executable):
        shell_command = [str(OPS/'scripts/go-cache-run.sh'),'exec',*shell_command]
    gate_env = dict(os.environ, PATH='/usr/local/go/bin:' + os.environ.get('PATH', ''))
    # Match the full integration build allowance under the shared two-CPU cap.
    gate_timeout = 1800 if re.search(r'\bgo\s+(build|test|vet)\b', executable) else 720
    result = call(shell_command,clone,timeout=gate_timeout,env=gate_env)
    require_executed_test(executable, result)
    if command.endswith(suffix) and result['exit_code']==0:
        try:
            measured = json.loads(result['stdout'])
            if measured.get('member_count') != 0:
                result['exit_code']=1; result['stderr']+='\npinned remeasurement is not zero'
            if ticket.get('work_type') == 'map' and measured.get('pinned_unresolved_count', 0):
                result['exit_code']=1; result['stderr']+='\npinned Map card still fails complete parsing; removing one miss category is insufficient'
        except json.JSONDecodeError:
            result['exit_code']=1; result['stderr']+='\npinned remeasurement did not return JSON'
    if no_output in command and result['exit_code']==0 and result['stdout'].strip():
        result['exit_code']=1; result['stderr']+='\ncommand produced output'
    return result

class PreparationFailure(ValueError):
    pass


def check_candidate(ticket, clone):
    names = call(['git', 'status', '--porcelain'], clone, timeout=30)
    changed = [line[3:] for line in names['stdout'].splitlines() if len(line) > 3]
    allowed = set(ticket['scope']['allowed_paths'])
    scope_ok = names['exit_code'] == 0 and bool(changed) and set(changed).issubset(allowed)
    gates = [{'id': 'scope', 'outcome': 'passed' if scope_ok else 'failed',
              'detail': 'changed=' + ','.join(changed)}]
    if not scope_ok:
        return gates, changed
    require_compilation()
    if ticket.get('work_type') == 'engine' and 'backend/game/ability_effects.go' in changed:
        gates.append(engine_registration_gate(ticket, clone))
        if gates[-1]['outcome'] == 'failed':
            return gates, changed
    for index, command in enumerate(ticket.get('gates', [])):
        require_compilation()
        result = ticket_gate(command, clone, ticket)
        gates.append({'id': 'ticket-gate-%d' % index, 'command': command,
                      'outcome': 'passed' if result['exit_code'] == 0 else 'failed',
                      'elapsed_ms': result['elapsed_ms'],
                      'detail': failure_detail(result)})
        if result['exit_code'] != 0:
            # Repair the current failure before doing expensive downstream
            # checks. A repaired candidate must rerun the entire gate list.
            break
    return gates, changed


def gate_repair_prompt(packet, clone, ticket, gates, changed):
    failed = '\n'.join(g.get('command', g['id']) + '\n' + g.get('detail', '')
                       for g in gates if g['outcome'] == 'failed')
    sections, budget = [], 500
    # Error locations identify the current candidate lines, not the original
    # pack's pre-patch text. NEWFILE proposals are now existing files.
    locations = {}
    for relative, line in re.findall(r'([\w/.-]+\.(?:go|py)):(\d+)', failed):
        if relative.startswith(('game/', 'cards/')):
            relative = 'backend/' + relative
        locations.setdefault(relative, []).append(int(line))
    # A misnamed existing test can produce no file:line diagnostic. Include
    # editable test files so a no-tools correction does not have to guess.
    test_context = ([p for p in ticket.get('scope', {}).get('allowed_paths', []) if p.endswith('_test.go')]
                    if 'executed no passing tests' in failed else [])
    diff = call(['git', 'diff', '--unified=8', '--no-ext-diff', '--', *changed], clone, timeout=30)
    hunks = {}
    relative = None
    for line in diff['stdout'].splitlines():
        if line.startswith('+++ b/'):
            relative = line[6:]
        match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
        if match and relative:
            lo, count = int(match[1]), int(match[2] or 1)
            if count: hunks.setdefault(relative, []).append((lo, lo + count - 1))
    for relative in list(dict.fromkeys(list(hunks) + list(locations) + test_context + changed)):
        path = source_path(clone, relative)
        if not path or budget <= 0:
            continue
        lines = path.read_text().splitlines()
        if relative in hunks:
            ranges = hunks[relative]
        elif relative in locations:
            lo = max(1, min(locations[relative]) - 12)
            hi = min(len(lines), max(locations[relative]) + 20)
            ranges = [(lo, hi)]
        else:
            ranges = [(1, min(len(lines), 120))]
        for lo, hi in ranges:
            if budget <= 0: break
            section, used = render_regions(relative, path.read_text(), '%d-%d' % (lo, hi), min(180, budget))
            sections.append(section)
            budget -= used
    return (packet + '\n\n## ONE COMPILE/TEST REPAIR\n'
            'Your first patch is already applied. Correct the CURRENT candidate using incremental '
            'SEARCH/REPLACE blocks. Files you created now exist: do not repeat NEWFILE blocks. '
            'Keep every original required behavior and gate, including test names and assertions. '
            'Do not disable, skip, remove or weaken required tests. Correct a misnamed candidate test '
            'to the required selector while preserving its assertions. No more NEED requests or tools.\n'
            'Exact failed gate and diagnostics:\n' + failed +
            '\n\nCurrent candidate source (takes precedence over the original packet):\n' +
            '\n\n'.join(sections) + '\nReturn only the bounded correction or an honest verdict.\n')


def failure_category(outcome, gates, preparation=()):
    if preparation:
        return 'preparation_contract'
    if outcome.startswith('accepted'):
        return None
    failed = [g for g in gates if g['outcome'] == 'failed' and g['id'] != 'initial-patch-apply']
    detail = '\n'.join(g.get('detail', '') for g in failed)
    if any(g['id'] == 'scope' for g in failed):
        return 'edit_scope'
    if 'VERDICT: AMBIGUOUS' in detail:
        return 'missing_evidence'
    if 'VERDICT: FRAMEWORK' in detail:
        return 'framework_claim'
    if re.search(r'build failed|undefined:|undefined \(|redeclared|cannot use|not enough arguments|wrong type', detail):
        return 'compile_or_vet'
    if any(g['id'] in ('patch-apply', 'gate-repair-apply') for g in failed):
        return 'model_response'
    if any(g['id'].startswith('ticket-gate-') for g in failed):
        return 'candidate_gate'
    return 'infrastructure' if outcome.startswith('infrastructure_failed') else outcome


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ticket',required=True,type=Path); ap.add_argument('--worker',required=True)
    ap.add_argument('--model',required=True); ap.add_argument('--profile',required=True)
    ap.add_argument('--resume-proposal', type=Path)
    ap.add_argument('--defer-verification', action='store_true')
    args=ap.parse_args(); attempt_started=time.monotonic(); ticket_path=args.ticket.resolve(); ticket=json.loads(ticket_path.read_text())
    if ticket.get('schema')!='factory.ticket-spec/v1' or ticket.get('work_type') not in ('map','engine'): ap.error('Map or Engine TicketSpec required')
    engine=PROFILE_ENGINES.get(args.profile)
    if not engine: ap.error('unsupported Engine profile')
    if not supports_profile(ticket,args.profile): ap.error('worker profile is not compatible with TicketSpec')
    problem = source_problem(SOURCE)
    if problem:
        print(json.dumps(source_wait_receipt(ticket_path, ticket, args.worker, args.profile, args.model, RUNS, OPS, problem)))
        return
    slug=ticket['id'].removeprefix('ticket:').replace('/','-').replace('.','-'); RUNS.mkdir(parents=True,exist_ok=True); CANDIDATES.mkdir(parents=True,exist_ok=True)
    identity = {'worker': args.worker, 'model': args.model, 'profile': args.profile}
    proposal = load_proposal(args.resume_proposal, ticket_path, identity) if args.resume_proposal else None
    raw=RUNS/(stamp()+'-'+slug+'-'+engine+'.raw.json'); receipt=RUNS/(stamp()+'-'+slug+'-'+engine+'.json')
    if proposal:
        raw = OPS / proposal['context']['raw_path']
    repair_raw=raw.with_name(raw.name.replace('.raw.json','.repair.raw.json'))
    continuation_raw=raw.with_name(raw.name.replace('.raw.json','.continuation.raw.json'))
    packet_artifact=raw.with_name(raw.name.replace('.raw.json','.packet.txt'))
    context_artifact=raw.with_name(raw.name.replace('.raw.json','.context.txt'))
    lookup_artifact=raw.with_name(raw.name.replace('.raw.json','.lookup.jsonl'))
    clone=Path(tempfile.mkdtemp(prefix='factory-ng-'+slug+'-',dir='/tmp'))
    outcome='infrastructure_failed'; gates=[]; changed=[]; result_commit='unavailable'; candidate_patch=None; capability=None
    attempt_history=[]; assessments=[]; model_calls=0; telemetry={}; preparation=[]; investigation=None; unresolved_evidence=None
    gate_repair_raw=raw.with_name(raw.name.replace('.raw.json','.gate-repair.raw.json'))
    investigation_raw=raw.with_name(raw.name.replace('.raw.json','.investigation.raw.json'))
    investigation_packet=raw.with_name(raw.name.replace('.raw.json','.investigation.packet.txt'))
    investigation_context=raw.with_name(raw.name.replace('.raw.json','.investigation.context.txt'))
    investigation_resume=raw.with_name(raw.name.replace('.raw.json','.investigation-resume.raw.json'))
    lookup_env=dict(os.environ,KB_TRACE_FILE=str(lookup_artifact),KB_TICKET=ticket['id'],KB_ATTEMPT=raw.stem)
    def model_env(artifact):
        value=model_environment(artifact)
        value.pop('PIPE_FACTORY_CODEX_HOST_ACCESS', None)
        if args.profile == 'codex-constrained@1.1.0':
            value['PIPE_FACTORY_CODEX_HOST_ACCESS'] = '1'
        value.update({k:lookup_env[k] for k in ('KB_TRACE_FILE','KB_TICKET','KB_ATTEMPT')})
        return value
    model_timeout=1900 if args.profile in CLAUDE_AGENTIC_LIKE_PROFILES else 1260
    apply_cmd=[sys.executable,str(OPS/'scripts/map-pipeline-apply.py')]
    if ticket['work_type']=='engine': apply_cmd.append('--allow-game')
    try:
        clone_result=call(['git','clone','--quiet','--no-hardlinks',str(SOURCE),str(clone)],OPS,timeout=180)
        if clone_result['exit_code']!=0: raise RuntimeError('clone failed')
        pinned=call(['git','checkout','--detach',ticket['source']['revision']],clone,timeout=60)
        if pinned['exit_code']!=0: raise RuntimeError('pinned revision checkout failed: '+pinned['stderr'])
        preparation = preparation_problems(ticket, clone)
        if preparation:
            raise PreparationFailure(json.dumps(preparation, sort_keys=True))
        if proposal:
            context = restore_proposal(proposal, clone)
            model, apply, packet = context['model'], context['apply'], context['packet']
            telemetry, gates = context['telemetry'], context['gates']
            model_calls, assessments = context['model_calls'], context['assessments']
            attempt_history = context['attempt_history']
            investigation = context.get('investigation')
            unresolved_evidence = context.get('unresolved_evidence')
        else:
            packer = OPS / 'scripts' / ('engine-pipeline-pack.py' if ticket['work_type']=='engine' else 'map-ticket-spec-pack.py')
            pack_command=[sys.executable,str(packer),'--ticket-spec',str(ticket_path),'--repo',str(clone)]
            if ticket['work_type']=='engine' and engine != 'codex' and args.profile not in AGENTIC_PROFILES:
                pack_command.append('--no-tools')
            if ticket['work_type']=='map' and engine == 'codex':
                pack_command.append('--read-only-tools')
            packet=call(pack_command,OPS,timeout=180,env=lookup_env)
            if packet['exit_code']!=0: raise RuntimeError('packet failed: '+packet['stderr'][-300:])
            packet['stdout'] += ('\n\n## TICKET CONTRACT (enforced verbatim by the harness)\n'
                                     'scope.allowed_paths (edit nothing else):\n%s\n\ngates:\n%s\n' % (
                                         '\n'.join('- '+p for p in ticket.get('scope',{}).get('allowed_paths',[])),
                                         '\n'.join('- '+g for g in ticket.get('gates',[]))))
            packet['stdout'] += ('\nrequired behavior:\n' +
                                 '\n'.join('- ' + rule for rule in ticket.get('required_behavior', [])))
            if args.profile == 'claude-staged@1.0.0':
                packet['stdout'] += '\n' + EVIDENCE_INSTRUCTIONS
            packet['stdout'] += ('\n## Vocabulary handoff\n'
                'Every new public ExecuteAbilityEffect case must be registered with regEffect in an '
                'allowed registry_*.go file, with executor and runtime test metadata. The registry '
                'literal is frozen. Parser-emitted effects must already be registered. '
                'The harness checks this before acceptance, in addition to every original gate.\n')
            packet['stdout'] += ('\nCompilation and testing are controlled separately by the dashboard. '
                                 'Do not run compilers, tests, benchmarks or generated test executables. '
                                 'Use source reads and return your proposed edit blocks; the harness owns validation.\n')
            packet_artifact.write_text(packet['stdout'])
            model_timeout=1900 if args.profile in CLAUDE_AGENTIC_LIKE_PROFILES else 1260
            env=model_env(raw)
            model=call([sys.executable,str(OPS/'scripts/model_call.py'),'--engine',engine,'--model',args.model,'--tier',ticket['work_type']],clone,stdin=packet['stdout'],timeout=model_timeout,env=env)
            assessment = capability_assessment(model['stdout'])
            if assessment: assessments.append(dict(assessment, stage='initial'))
            if not raw.exists(): raw.write_text(model['stdout'])
            model_calls = 1
            telemetry=counters(model['stderr'],model['elapsed_ms'])
            with lookup_context(lookup_env):
                continuation = requested_context(model['stdout'],clone,ticket) if ticket['work_type']=='engine' or args.profile == 'claude-staged@1.0.0' else ''
            if continuation:
                context_artifact.write_text(continuation)
                continuation_prompt = (packet['stdout'] + '\n\n## REQUESTED CONTINUATION (one round)\n' +
                                       continuation + '\n\nNow return the complete edit blocks or bounded verdict. '
                                       'Do not emit another NEED request.\n')
                continuation_env=model_env(continuation_raw)
                continued=call([sys.executable,str(OPS/'scripts/model_call.py'),'--engine',engine,
                                '--model',args.model,'--tier',ticket['work_type']],clone,
                               stdin=continuation_prompt,timeout=model_timeout,env=continuation_env)
                assessment = capability_assessment(continued['stdout'])
                if assessment: assessments.append(dict(assessment, stage='continuation'))
                if not continuation_raw.exists(): continuation_raw.write_text(continued['stdout'])
                merge_telemetry(telemetry,counters(continued['stderr'],continued['elapsed_ms']))
                telemetry['need_continuation_attempted']=True
                gates.append({'id':'need-continuation','outcome':'passed',
                              'detail':'resolved %d bounded source request(s)' % len(re.findall(r'^NEED:',model['stdout'],re.M))})
                model=continued
                model_calls += 1
            gap = evidence_gap(model, args.profile)
            if gap and ticket.get('execution', {}).get('profile_policy') != 'exact':
                # Exploration only after an explicit staged evidence failure. It
                # shares this physical lease and never gets patch/apply authority.
                attempt_history.append({'stage': 'staged_evidence_failure', 'evidence_gap': gap})
                prompt = investigation_prompt(ticket, gap)
                investigation_packet.write_text(prompt)
                investigation_env = model_env(investigation_raw)
                investigation_env['PIPE_FACTORY_INVESTIGATION'] = '1'
                investigated = call([sys.executable, str(OPS/'scripts/model_call.py'), '--engine', 'claude-agentic',
                                     '--model', args.model, '--tier', ticket['work_type']], clone,
                                    stdin=prompt, timeout=360, env=investigation_env)
                if not investigation_raw.exists(): investigation_raw.write_text(investigated['stdout'])
                investigation_usage = counters(investigated['stderr'], investigated['elapsed_ms'])
                merge_telemetry(telemetry, investigation_usage)
                model_calls += 1
                telemetry['agentic_investigation_attempted'] = True
                investigation = {'profile': CLAUDE_AGENTIC_PROFILE, 'gap': gap, 'telemetry': investigation_usage,
                                 'status': 'unresolved', 'max_turns': 12, 'timeout_seconds': 300}
                try:
                    if investigated['exit_code'] != 0:
                        raise ValueError('evidence investigation did not finish successfully')
                    clean = call(['git', 'status', '--porcelain'], clone, timeout=30)
                    head = call(['git', 'rev-parse', 'HEAD'], clone, timeout=30)
                    if clean['exit_code'] or clean['stdout'].strip() or head['stdout'].strip() != ticket['source']['revision']:
                        raise ValueError('read-only investigation changed its checkout')
                    evidence, anchors = validate_evidence(investigated['stdout'], clone)
                    investigation_context.write_text(evidence)
                    investigation.update(status='evidence_supplied', sources=anchors)
                except (ValueError, OSError) as exc:
                    investigation['reason'] = str(exc)
                    # Do not spend the coding-repair allowance on an evidence
                    # response or retry the investigator in an unbounded loop.
                    model = {'exit_code': 0, 'stdout': 'VERDICT: AMBIGUOUS\nREASON: unresolved staged evidence gap.\n'}
                else:
                    resumed_prompt = (packet['stdout'] + '\n\n## HARNESS-VERIFIED SOURCE AFTER EVIDENCE INVESTIGATION\n' +
                                      evidence + '\n\nThe investigator supplied references only. You remain the staged implementer. '
                                      'Use the original scope and gates. Return the patch or an honest bounded verdict; '
                                      'no further NEED or investigation rounds.\n')
                    model = call([sys.executable, str(OPS/'scripts/model_call.py'), '--engine', engine,
                                  '--model', args.model, '--tier', ticket['work_type']], clone,
                                 stdin=resumed_prompt, timeout=model_timeout, env=model_env(investigation_resume))
                    if not investigation_resume.exists(): investigation_resume.write_text(model['stdout'])
                    merge_telemetry(telemetry, counters(model['stderr'], model['elapsed_ms']))
                    model_calls += 1
                    assessment = capability_assessment(model['stdout'])
                    if assessment: assessments.append(dict(assessment, stage='after_investigation'))
                    if evidence_gap(model, args.profile):
                        investigation['status'] = 'staged_still_missing_evidence'
                        model = {'exit_code': 0, 'stdout': 'VERDICT: AMBIGUOUS\nREASON: evidence still insufficient after the single investigation.\n'}
            elif gap:
                # An exact-profile cohort remains unassisted; no invisible
                # exploration spending may contaminate its comparison.
                unresolved_evidence = gap
                attempt_history.append({'stage': 'staged_evidence_failure', 'evidence_gap': gap})
                model = {'exit_code': 0, 'stdout': 'VERDICT: AMBIGUOUS\nREASON: staged evidence gap; exact-profile ticket forbids agentic assistance.\n'}
            apply_cmd=[sys.executable,str(OPS/'scripts/map-pipeline-apply.py')]
            if ticket['work_type']=='engine': apply_cmd.append('--allow-game')
            apply=call(apply_cmd,clone,stdin=model['stdout'],timeout=60)
            if should_attempt_repair(model, apply, telemetry, args.profile):
                gates.append({'id':'initial-patch-apply','outcome':'failed',
                              'detail':(apply['stdout']+apply['stderr'])[-800:]})
                repair_prompt = (packet['stdout'] + '\n\n## ONE BOUNDED REPAIR\nYour previous answer was:\n' +
                                 model['stdout'] + '\n\nThe strict patch harness rejected it with:\n' +
                                 (apply['stdout']+apply['stderr'])[-1600:] +
                                 '\nReturn one complete corrected answer in the original OUTPUT FORMAT. '
                                 'Use NEWFILE for paths that do not exist. No prose or tool calls.\n')
                repair_env=model_env(repair_raw)
                repaired=call([sys.executable,str(OPS/'scripts/model_call.py'),'--engine',engine,
                               '--model',args.model,'--tier',ticket['work_type']],clone,
                              stdin=repair_prompt,timeout=model_timeout,env=repair_env)
                assessment = capability_assessment(repaired['stdout'])
                if assessment: assessments.append(dict(assessment, stage='protocol_repair'))
                if not repair_raw.exists(): repair_raw.write_text(repaired['stdout'])
                repair_telemetry=counters(repaired['stderr'],repaired['elapsed_ms'])
                merge_telemetry(telemetry,repair_telemetry)
                telemetry['bounded_repair_attempted']=True
                model=repaired
                model_calls += 1
                apply=call(apply_cmd,clone,stdin=model['stdout'],timeout=60)
        if model['exit_code'] == CAPACITY_EXIT:
            gates.append({'id':'provider-capacity', 'outcome':'failed',
                          'detail':'Selected model is at capacity; no proposal was produced. Bounded infrastructure backoff applies.'})
            outcome=CAPACITY_OUTCOME
        elif model['exit_code'] == OPENROUTER_RATE_LIMIT_EXIT:
            gates.append({'id':'provider-rate-limit', 'outcome':'failed',
                          'detail':'OpenRouter returned 429; no candidate was attempted.'})
            outcome='infrastructure_failed_rate_limited'
        elif model['exit_code'] == AUTHENTICATION_EXIT:
            gates.append({'id':'provider-authentication', 'outcome':'failed',
                          'detail':'Provider OAuth session is unavailable; no candidate was attempted.'})
            outcome='infrastructure_failed_authentication'
        else:
            gates.append({'id':'patch-apply','outcome':'passed' if apply['exit_code']==0 else 'failed','detail':(apply['stdout']+apply['stderr'])[-800:]})
        if model['exit_code'] not in (AUTHENTICATION_EXIT, OPENROUTER_RATE_LIMIT_EXIT, CAPACITY_EXIT, 0):
            outcome='infrastructure_failed'
            gates.append({'id':'provider-call', 'outcome':'failed',
                          'detail':'Provider call exited %s; see retained raw response. %s' % (
                              model['exit_code'], model.get('stderr', '')[-1200:])})
        elif model['exit_code'] in (AUTHENTICATION_EXIT, OPENROUTER_RATE_LIMIT_EXIT, CAPACITY_EXIT):
            pass
        elif apply['exit_code']==4:
            verdict = re.search(r'\bVERDICT:\s*([A-Z_]+)', model['stdout'])
            if verdict and verdict.group(1) == 'NEEDS_PRIMITIVE' and ticket['work_type'] == 'map':
                try:
                    capability = validated_capability(model['stdout'])
                    outcome = 'blocked_by_capability'
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    outcome = 'invalid_capability_demand'
                    gates.append({'id':'capability-contract','outcome':'failed','detail':str(exc)[-800:]})
            else:
                outcome='parked'
        elif apply['exit_code']!=0:
            apply_text=(apply['stdout']+apply['stderr']).lower()
            outcome=('infrastructure_failed_model_protocol'
                     if 'no edit blocks' in apply_text or 'no verdict' in apply_text
                     else 'gate_failed')
        elif apply['exit_code']==0:
            if args.defer_verification:
                raise VerificationPaused('Queued for combined focused verification.')
            candidate_gates, changed = check_candidate(ticket, clone)
            if (args.profile in ('claude-staged@1.0.0', 'codex-constrained@1.1.0') and
                    repair_available(args.profile, telemetry) and
                    candidate_gates[0]['outcome'] == 'passed' and
                    any(g['outcome'] == 'failed' for g in candidate_gates[1:])):
                attempt_history.append({'stage': 'before_gate_repair', 'gates': candidate_gates})
                prompt = gate_repair_prompt(packet['stdout'], clone, ticket, candidate_gates, changed)
                repaired=call([sys.executable,str(OPS/'scripts/model_call.py'),'--engine',engine,
                               '--model',args.model,'--tier',ticket['work_type']],clone,
                              stdin=prompt,timeout=model_timeout,env=model_env(gate_repair_raw))
                assessment = capability_assessment(repaired['stdout'])
                if assessment: assessments.append(dict(assessment, stage='gate_repair'))
                if not gate_repair_raw.exists(): gate_repair_raw.write_text(repaired['stdout'])
                merge_telemetry(telemetry,counters(repaired['stderr'],repaired['elapsed_ms']))
                telemetry['bounded_repair_attempted']=True
                telemetry['gate_repair_attempted']=True
                model_calls += 1
                repaired_apply = (call(apply_cmd,clone,stdin=repaired['stdout'],timeout=60)
                                  if repaired['exit_code'] == 0 else repaired)
                gates.append({'id':'gate-repair-apply',
                              'outcome':'passed' if repaired_apply['exit_code']==0 else 'failed',
                              'detail':failure_detail(repaired_apply)})
                if repaired_apply['exit_code'] == 0:
                    candidate_gates, changed = check_candidate(ticket, clone)
                elif repaired_apply['exit_code'] == 4 and ticket['work_type'] == 'map' and re.search(r'\bVERDICT:\s*NEEDS_PRIMITIVE\b', repaired.get('stdout', '')):
                    # A failed Map candidate can reveal a real Engine gap in
                    # its one correction. Preserve the failed gates, but route
                    # the validated dependency instead of losing the verdict.
                    try:
                        capability = validated_capability(repaired['stdout'])
                    except (OSError, ValueError, json.JSONDecodeError) as exc:
                        gates.append({'id': 'capability-contract', 'outcome': 'failed', 'detail': str(exc)[-800:]})
            gates.extend(candidate_gates)
            if final_gates_pass(gates):
                call(['git','add','-A'],clone,timeout=60)
                commit=call(['git','-c','user.name=Factory NG','-c','user.email=factory-ng@local','commit','-m','factory-ng: supervised engine observation'],clone,timeout=60)
                if commit['exit_code']==0:
                    outcome='accepted_for_dependent_observation'
                    exported=call(['git','format-patch','-1','--stdout','HEAD'],clone,timeout=60)
                    if exported['exit_code']==0:
                        candidate_patch=CANDIDATES/(stamp()+'-'+slug+'.patch'); candidate_patch.write_text(exported['stdout'])
                    else:
                        outcome='infrastructure_failed_candidate_export'
                        gates.append({'id':'candidate-export','outcome':'failed','detail':exported['stderr'][-800:]})
                else: gates.append({'id':'candidate-commit','outcome':'failed','detail':commit['stderr'][-800:]})
            else: outcome='blocked_by_capability' if capability is not None else 'gate_failed'
        result_commit=call(['git','rev-parse','HEAD'],clone,timeout=30)['stdout'].strip()
    except VerificationPaused:
        context = {'raw_path': str(raw.relative_to(OPS)), 'model': model, 'apply': apply,
                   'packet': packet, 'telemetry': telemetry, 'gates': gates,
                   'model_calls': model_calls, 'assessments': assessments,
                   'attempt_history': attempt_history, 'investigation': investigation,
                   'unresolved_evidence': unresolved_evidence}
        try:
            pending = save_proposal(CANDIDATES, clone, ticket_path, identity, context)
        except ValueError as exc:
            # Scope/empty-patch rejection is a terminal gate result. Exceptions
            # raised inside this handler do not reach the sibling except blocks.
            outcome = 'gate_failed'
            gates.append({'id': 'proposal-contract', 'outcome': 'failed', 'detail': str(exc)})
        except Exception as exc:
            outcome = 'infrastructure_failed'
            gates.append({'id': 'proposal-save', 'outcome': 'failed', 'detail': str(exc)})
        else:
            shutil.rmtree(clone, ignore_errors=True)
            print(json.dumps({'status': 'verification_pending', 'ticket_id': ticket['id'],
                              'worker': args.worker, 'proposal': str(pending.relative_to(OPS)),
                              'reason': 'Patch saved without acceptance; awaiting focused verification.'}))
            return
    except PreparationFailure as exc:
        outcome='preparation_failed'
        gates.append({'id':'preparation-contract','outcome':'failed','detail':str(exc)})
        raw.write_text('Model not called: '+str(exc)+'\n')
        telemetry={key:0 for key in ('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','elapsed_ms')}
    except Exception as exc:
        outcome='infrastructure_failed'
        gates.append({'id':'runner','outcome':'failed','detail':str(exc)})
        if not raw.exists(): raw.write_text('runner failure: %s\n'%exc)
        telemetry=telemetry or {'input_tokens':{'availability':'unavailable','reason':'runner failed before model'},'output_tokens':{'availability':'unavailable','reason':'runner failed before model'},'cache_read_tokens':{'availability':'unavailable','reason':'runner failed before model'},'cache_write_tokens':{'availability':'unavailable','reason':'runner failed before model'},'reasoning_tokens':{'availability':'unavailable','reason':'runner failed before model'},'provider_cost_usd':{'availability':'unavailable','reason':'runner failed before model'},'elapsed_ms':0}
    telemetry['model_calls']=model_calls
    gate_ms = sum(g.get('elapsed_ms', 0) for g in gates)
    gate_ms += sum(g.get('elapsed_ms', 0) for attempt in attempt_history for g in attempt.get('gates', []))
    telemetry['stage_times'] = {
        'attempt_wall_ms': round((time.monotonic() - attempt_started) * 1000),
        'model_ms': telemetry.get('elapsed_ms'),
        'candidate_gate_ms': gate_ms,
        'compilation_ms': {'availability': 'unavailable', 'reason': 'go test includes package compilation; not separately timed'},
    }
    source_changed=bool(subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],text=True).strip())
    artifacts=[{'path':str(raw.relative_to(OPS)),'sha256':file_digest(raw)}]
    for path, kind in ((packet_artifact, 'prepared_packet'), (context_artifact, 'requested_context'), (lookup_artifact, 'knowledge_trace')):
        if path.exists(): artifacts.append({'path':str(path.relative_to(OPS)),'sha256':file_digest(path),'kind':kind})
    if continuation_raw.exists(): artifacts.append({'path':str(continuation_raw.relative_to(OPS)),'sha256':file_digest(continuation_raw),'kind':'need_continuation'})
    if gate_repair_raw.exists(): artifacts.append({'path':str(gate_repair_raw.relative_to(OPS)),'sha256':file_digest(gate_repair_raw),'kind':'gate_repair'})
    if repair_raw.exists(): artifacts.append({'path':str(repair_raw.relative_to(OPS)),'sha256':file_digest(repair_raw),'kind':'bounded_repair'})
    for path, kind in ((investigation_raw, 'agentic_investigation'), (investigation_packet, 'investigation_packet'),
                       (investigation_context, 'investigation_source'), (investigation_resume, 'staged_after_investigation')):
        if path.exists(): artifacts.append({'path':str(path.relative_to(OPS)),'sha256':file_digest(path),'kind':kind})
    value={'schema':'factory.observation-receipt/v1','ticket':{'id':ticket['id'],'path':str(ticket_path.relative_to(OPS)),'sha256':file_digest(ticket_path)},'skill':ticket['skill'],'model':{'profile':args.profile,'resolved_model':args.model,'worker':args.worker,'telemetry':telemetry},'execution':{'mode':'isolated_clone_observation_only','source_revision':ticket['source']['revision'],'source_tree_changed':source_changed,'candidate_commit':result_commit,'candidate_clone':str(clone)},'raw_artifacts':artifacts,'gates':gates,'outcome':outcome,'integration':'eligible_full_gate' if outcome=='accepted_for_dependent_observation' else 'observation_only','next_action':'The controller will integrate an accepted candidate under the configured full-gate policy.'}
    value['attempt_history']=attempt_history
    value['capability_assessments']=assessments
    value['failure_category']=failure_category(outcome, gates, preparation)
    if unresolved_evidence:
        value['failure_category'] = 'missing_source_context'
        value['evidence_failure'] = unresolved_evidence
    if investigation:
        value['investigation'] = investigation
    if preparation:
        value['preparation_problems']=preparation
        value['next_action']='Issue a corrected successor TicketSpec; do not retry this immutable scope/test contract.'
    if outcome == 'infrastructure_failed_authentication':
        value['reason']='Provider OAuth session expired or could not be refreshed.'
        value['next_action']='The controller will refund this dispatch, pause the worker, and retain the ticket for a later compatible worker.'
    if outcome == 'infrastructure_failed_rate_limited':
        value['reason']='OpenRouter returned HTTP 429; the shared provider cooldown is active.'
        value['next_action']='The controller will refund this dispatch and retain the ticket until OpenRouter cooldown expires.'
    if capability:
        value['capability_demand']=capability
        value['next_action']='The dependency producer will compile this validated atomic demand into an Engine TicketSpec.'
    if candidate_patch:
        value['execution']['candidate_patch']=str(candidate_patch.relative_to(OPS)); value['execution']['candidate_patch_sha256']=file_digest(candidate_patch)
        value['next_action']='Factory NG may integrate this durable patch under its configured full-gate policy.'
    write_receipt(receipt, value)
    result={'status':outcome,'ticket_id':ticket['id'],'worker':args.worker,'receipt':str(receipt.relative_to(OPS))}
    if value.get('reason'): result['reason']=value['reason']
    print(json.dumps(result))
    if candidate_patch is not None or outcome!='accepted_for_dependent_observation': shutil.rmtree(clone,ignore_errors=True)

if __name__=='__main__': main()
