#!/usr/bin/env python3
"""worker_ctl.py — single control point for the pipeline-lane worker family
(p1, pipe-codex, pipe-qwen, pipe-ox, pipe-ox2). Replaces the launch-*.sh
restart-loop scripts' scattered env-var defaults with one config file
(config/workers.json) and one CLI.

    worker_ctl.py list                    # configured workers + live status
    worker_ctl.py start <name> [--override key=val ...]
    worker_ctl.py stop <name>
    worker_ctl.py restart <name>
    worker_ctl.py status [--json]

Each worker still just runs pipeline-lane.sh <name> with env vars set —
this script only replaces *how those env vars get chosen*. The claim/
heartbeat/report loop, gate/bugfix-round/commit/push machinery, and pace
gates are untouched.
"""
import argparse, dataclasses, json, os, subprocess, sys, time

OPS = os.environ.get("OPS", "/opt/development/magic-ops")
CONFIG_PATH = os.path.join(OPS, "config/workers.json")
ORCH = "/tmp/orch"
DISPATCHER = os.environ.get("DISPATCHER", "http://localhost:9999")


@dataclasses.dataclass
class WorkerConfig:
    name: str
    engine: str  # claude | codex | qwen-agentic | openrouter | openrouter-agentic
    model: str
    base_url: str = ""
    max_tokens: int = 8000
    reasoning_tokens: int = 3000
    max_turns: int = 25          # agentic loop turns
    claude_max_turns: int = 5    # claude CLI's own --max-turns (unrelated knob)
    max_need_rounds: int = 4     # staged NEED-region round cap


def load_workers() -> dict[str, WorkerConfig]:
    with open(CONFIG_PATH) as f:
        rows = json.load(f)
    known = {f.name for f in dataclasses.fields(WorkerConfig)}
    workers = {}
    for row in rows:
        unknown = set(row) - known
        if unknown:
            raise ValueError(f"{row.get('name','?')}: unknown config keys {unknown}")
        workers[row["name"]] = WorkerConfig(**row)
    return workers


def apply_overrides(cfg: WorkerConfig, overrides: list[str]) -> WorkerConfig:
    cfg = dataclasses.replace(cfg)
    fieldtypes = {f.name: f.type for f in dataclasses.fields(cfg)}
    for kv in overrides:
        key, _, val = kv.partition("=")
        if key not in fieldtypes:
            raise ValueError(f"unknown override key {key!r}")
        cast = int if fieldtypes[key] is int else str
        setattr(cfg, key, cast(val))
    return cfg


# Engine -> env vars pipeline-lane.sh/map-pipeline.sh/engine-pipeline.sh read.
# This table is the single place that knows the env-var vocabulary — everything
# else just calls it.
def env_for(cfg: WorkerConfig) -> dict:
    env = {"PIPE_MODEL": cfg.model}
    if cfg.engine == "claude":
        env["PIPE_MAX_TURNS"] = str(cfg.claude_max_turns)
    elif cfg.engine == "codex":
        env["PIPE_ENGINE"] = "codex"
    elif cfg.engine == "qwen-agentic":
        env.update({
            "PIPE_ENGINE": "qwen-agentic",
            "PIPE_BASE_URL": cfg.base_url,
            "PIPE_AGENTIC_MAX_TURNS": str(cfg.max_turns),
            "PIPE_MAX_TOKENS_CAP": str(cfg.max_tokens),
        })
    elif cfg.engine == "openrouter":
        env.update({
            "PIPE_ENGINE": "openrouter",
            "PIPE_MAX_TOKENS_CAP": str(cfg.max_tokens),
            "PIPE_REASONING_TOKENS": str(cfg.reasoning_tokens),
            "PIPE_MAX_NEED_ROUNDS": str(cfg.max_need_rounds),
        })
    elif cfg.engine == "openrouter-agentic":
        env.update({
            "PIPE_ENGINE": "openrouter-agentic",
            "PIPE_MAX_TOKENS_CAP": str(cfg.max_tokens),
            "PIPE_REASONING_TOKENS": str(cfg.reasoning_tokens),
            "PIPE_AGENTIC_MAX_TURNS": str(cfg.max_turns),
        })
    else:
        raise ValueError(f"unknown engine {cfg.engine!r}")
    return env


def log_path(name: str) -> str:
    return f"{ORCH}/pipeline-lane-{name}.log"


def tmux_window_exists(session: str, name: str) -> bool:
    out = subprocess.run(["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
                          capture_output=True, text=True)
    return name in out.stdout.split()


def cmd_list(args):
    workers = load_workers()
    print(f"{'name':<12} {'engine':<18} {'model':<40}")
    for cfg in workers.values():
        print(f"{cfg.name:<12} {cfg.engine:<18} {cfg.model:<40}")


def cmd_start(args):
    workers = load_workers()
    if args.name not in workers:
        sys.exit(f"unknown worker {args.name!r} — see workers.json")
    cfg = apply_overrides(workers[args.name], args.override)
    env = env_for(cfg)
    if tmux_window_exists(args.tmux_session, cfg.name):
        sys.exit(f"tmux window {args.tmux_session}:{cfg.name} already exists — "
                 f"stop it first or it'll collide (this is exactly the zombie-"
                 f"supervisor bug worker_ctl.py exists to prevent)")

    env_prefix = " ".join(f"{k}={_sh_quote(v)}" for k, v in env.items())
    log = log_path(cfg.name)
    loop = (
        f"mkdir -p {ORCH} /tmp/work; "
        f"while true; do "
        f"{env_prefix} bash {OPS}/scripts/pipeline-lane.sh {cfg.name} >> {log} 2>&1; "
        f'echo "[$(date -Is)] {cfg.name} exit, restart 30s" >> {log}; '
        f"sleep 30; done; exec bash"
    )
    subprocess.run(["tmux", "new-window", "-t", args.tmux_session, "-n", cfg.name, loop], check=True)
    print(f"started {cfg.name} in tmux window {args.tmux_session}:{cfg.name}")


def cmd_stop(args):
    if not tmux_window_exists(args.tmux_session, args.name):
        print(f"no tmux window {args.tmux_session}:{args.name} — nothing to stop "
              f"(checking for stray processes anyway)")
    else:
        # Kill the tmux window FIRST — it owns the restart-loop shell. Killing
        # only the leaf pipeline-lane.sh/model-call processes without this
        # leaves the loop alive to immediately respawn a new one (exactly
        # tonight's zombie-supervisor bug: only the child got killed, the
        # parent's `while true` loop silently kept going on stale code).
        subprocess.run(["tmux", "kill-window", "-t", f"{args.tmux_session}:{args.name}"])
    # Belt-and-suspenders: kill any remaining process tree for this worker
    # name, in case it was started outside tmux (e.g. an old-style launcher).
    killed = _kill_process_tree_by_name(args.name)
    print(f"stopped {args.name}" + (f" (also killed {killed} stray process(es))" if killed else ""))


def _kill_process_tree_by_name(name: str) -> int:
    out = subprocess.run(["pgrep", "-f", f"pipeline-lane.sh {name}$"], capture_output=True, text=True)
    roots = [int(p) for p in out.stdout.split()]
    if not roots:
        return 0
    all_pids = set()
    frontier = list(roots)
    while frontier:
        pid = frontier.pop()
        if pid in all_pids:
            continue
        all_pids.add(pid)
        children = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
        frontier.extend(int(p) for p in children.stdout.split())
    for pid in all_pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
    return len(all_pids)


def cmd_restart(args):
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)


def _process_running(name: str) -> bool:
    return subprocess.run(["pgrep", "-f", f"pipeline-lane.sh {name}$"],
                           capture_output=True).returncode == 0


def cmd_status(args):
    workers = load_workers()
    rows = []
    for cfg in workers.values():
        in_tmux = tmux_window_exists(args.tmux_session, cfg.name)
        running = in_tmux or _process_running(cfg.name)
        untracked = running and not in_tmux
        last_line = ""
        lp = log_path(cfg.name)
        if os.path.exists(lp):
            with open(lp, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 300))
                tail = f.read().decode(errors="replace").strip().splitlines()
                last_line = tail[-1] if tail else ""
        rows.append({"name": cfg.name, "engine": cfg.engine, "running": running,
                     "untracked": untracked, "last_log": last_line})
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    for r in rows:
        state = "running" if r["running"] else "stopped"
        if r["untracked"]:
            state += " (untracked!)"
        print(f"{r['name']:<12} {state:<20} {r['last_log'][:100]}")


def _sh_quote(v: str) -> str:
    import shlex
    return shlex.quote(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tmux-session", default="dispatcher")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    p_start = sub.add_parser("start")
    p_start.add_argument("name")
    p_start.add_argument("--override", action="append", default=[], metavar="key=val")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop")
    p_stop.add_argument("name")
    p_stop.set_defaults(func=cmd_stop)

    p_restart = sub.add_parser("restart")
    p_restart.add_argument("name")
    p_restart.add_argument("--override", action="append", default=[], metavar="key=val")
    p_restart.set_defaults(func=cmd_restart)

    p_status = sub.add_parser("status")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
