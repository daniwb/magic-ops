#!/usr/bin/env python3
"""factory-ng-debug-session.py — look inside the Factory while it runs.

Three questions this answers, in order of cost:

  what Python produces   -> `pack`  (free: TicketSpec -> prompt packet, no model)
  what goes out / back   -> `watch` (free: live correlated round trips from the
                                    retained artifacts + the wire tap)
  one controlled round   -> `call`  (spends quota: pack + ONE model call in a
  trip                                   throwaway clone; no apply, no gates,
                                         no receipt, no queue interference)

Everything here is read-only against the live queue except `call`, which never
applies a patch, never runs a gate, never writes a receipt and never touches
the canonical checkout.  It clones with hardlinks, so it is cheap.

Examples
  python3 scripts/factory-ng-debug-session.py status
  python3 scripts/factory-ng-debug-session.py watch --follow
  python3 scripts/factory-ng-debug-session.py show                 # latest trip
  python3 scripts/factory-ng-debug-session.py show --stem <stem> --full
  python3 scripts/factory-ng-debug-session.py pack --ticket docs/factory-ng/tickets/x.json
  python3 scripts/factory-ng-debug-session.py call --ticket ... --engine claude \
      --model claude-sonnet-5 --yes
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
RUNS = OPS / "docs" / "factory-ng" / "runs"
TICKETS = OPS / "docs" / "factory-ng" / "tickets"
STATE = OPS / "state"
SOURCE = Path(os.environ.get("FACTORY_NG_SOURCE", str(OPS.parent / "test" / "openmagic")))

sys.path.insert(0, str(OPS / "scripts"))
try:
    import factory_ng_wire_tap as wire_tap
except Exception:  # noqa: BLE001
    wire_tap = None

ARTIFACT_SUFFIXES = (
    ".investigation.packet.txt", ".investigation.raw.json",
    ".continuation.packet.txt", ".continuation.raw.json",
    ".gate-repair.packet.txt", ".gate-repair.raw.json",
    ".repair.packet.txt", ".repair.raw.json",
    ".packet.txt", ".raw.json", ".context.txt", ".lookup.jsonl", ".json",
)
PHASE_ORDER = {"initial": 0, "continuation": 1, "investigation": 1,
              "repair": 2, "correction": 2}


def now_utc():
    return datetime.now(timezone.utc)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def run(cmd, cwd=None, stdin=None, timeout=600, env=None):
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, input=stdin,
                         capture_output=True, text=True, timeout=timeout, env=env)
    return proc


def nbytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return "%.1f%s" % (n, unit) if unit != "B" else "%dB" % n
        n /= 1024.0


def stem_of(name):
    for suffix in ARTIFACT_SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)], suffix
    return name, ""


def artifact_index():
    """Map stem -> {suffix: Path} for every retained run artifact."""
    index = {}
    for path in sorted(RUNS.glob("*")):
        if not path.is_file():
            continue
        stem, suffix = stem_of(path.name)
        index.setdefault(stem, {})[suffix] = path
    return index


def parse_raw(path):
    """Pull the interesting fields out of a retained provider response."""
    out = {"kind": "unknown", "text": "", "tokens": {}, "stop": None, "cost": None,
           "error": None}
    try:
        body = path.read_text(errors="replace")
    except OSError as exc:
        out["error"] = str(exc)
        return out
    try:
        data = json.loads(body)
    except ValueError:
        out["kind"] = "text"
        out["text"] = body
        return out
    if isinstance(data, dict) and "provider_error" in data:
        out["kind"] = "provider_error"
        out["error"] = json.dumps(data["provider_error"], sort_keys=True)[:2000]
        return out
    if "choices" in data:  # OpenRouter / OpenAI-shaped
        out["kind"] = "openrouter"
        choice = (data.get("choices") or [{}])[0]
        out["text"] = ((choice.get("message") or {}).get("content")) or ""
        out["stop"] = choice.get("finish_reason")
        usage = data.get("usage") or {}
        out["tokens"] = {"in": usage.get("prompt_tokens", 0),
                        "out": usage.get("completion_tokens", 0),
                        "cache_r": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}
        out["cost"] = data.get("usage", {}).get("cost")
        return out
    if "result" in data or "usage" in data:  # claude CLI json envelope
        out["kind"] = "claude-cli"
        out["text"] = data.get("result") or ""
        out["stop"] = data.get("stop_reason")
        usage = data.get("usage") or {}
        out["tokens"] = {"in": usage.get("input_tokens", 0),
                        "out": usage.get("output_tokens", 0),
                        "cache_r": usage.get("cache_read_input_tokens", 0),
                        "cache_w": usage.get("cache_creation_input_tokens", 0)}
        details = usage.get("output_tokens_details") or {}
        if details.get("thinking_tokens"):
            out["tokens"]["thinking"] = details["thinking_tokens"]
        out["cost"] = data.get("total_cost_usd")
        out["session_id"] = data.get("session_id")
        out["turns"] = data.get("num_turns")
        out["is_error"] = data.get("is_error")
        return out
    out["kind"] = "json"
    out["text"] = json.dumps(data, indent=2, sort_keys=True)[:4000]
    return out


def first_line(text, limit=110):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:limit]
    return "(empty)"


# ---------------------------------------------------------------- status
def cmd_status(args):
    print("== HOW THE FACTORY IS RUNNING RIGHT NOW")
    procs = subprocess.run(["ps", "-eo", "pid,etime,args"], capture_output=True,
                          text=True).stdout.splitlines()
    patterns = ("factory-ng-controller.py", "dispatcher-v4", "factory-ng-watchdog.py",
                "factory-ng-run-engine-ticket.py", "factory-ng-run-map-ticket.py",
                "model_call.py", "coverage-snapshot")
    for pattern in patterns:
        hits = [p for p in procs[1:] if pattern in p and "grep" not in p]
        if hits:
            for hit in hits[:4]:
                print("  %-34s %s" % (pattern, hit.strip()[:150]))
        else:
            print("  %-34s (not running)" % pattern)

    print("\n== WIRE TAP (exact provider argv + request/response bytes)")
    if wire_tap is None:
        print("  module unavailable")
    else:
        st = wire_tap.status()
        print("  enabled=%s  expires=%s  filter=%s  stored=%s in %s" % (
            st["enabled"], st["expires_at"], st["ticket_filter"] or "none",
            nbytes(st["bytes"]), st["dir"]))
        if st["enabled"]:
            print("  -> every model_call.py from here on records itself; "
                  "`watch` will show argv lines too")
        else:
            print("  -> turn on: python3 scripts/factory_ng_wire_tap.py --on --minutes 120")

    print("\n== LIVE STATE FILES")
    for name, keys in (("factory-ng-runtime.json", ("state", "phase", "updated_at", "message")),
                      ("factory-ng-watchdog.json", ("checked_at", "healthy", "moving", "problems"))):
        path = STATE / name
        if not path.exists():
            print("  %s: missing" % name)
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            print("  %s: unreadable (%s)" % (name, exc))
            continue
        picked = {k: data.get(k) for k in keys if k in data}
        print("  %s: %s" % (name, json.dumps(picked)[:400]))

    print("\n== MOST RECENT ROUND TRIPS (%s)" % RUNS)
    index = artifact_index()
    stems = sorted(index.keys(),
                  key=lambda s: max(p.stat().st_mtime for p in index[s].values()))[-8:]
    for stem in stems:
        parts = index[stem]
        packet = parts.get(".packet.txt")
        raw = parts.get(".raw.json")
        receipt = parts.get(".json")
        line = "  %s" % stem[:72]
        if packet:
            line += "  req=%s" % nbytes(packet.stat().st_size)
        if raw:
            parsed = parse_raw(raw)
            tok = parsed["tokens"]
            line += "  resp=%s stop=%s out=%s" % (nbytes(raw.stat().st_size),
                                                parsed["stop"], tok.get("out", "?"))
        if receipt:
            try:
                r = json.loads(receipt.read_text())
                line += "  outcome=%s" % r.get("outcome")
            except (OSError, ValueError):
                pass
        print(line)
    print("\n  drill in: show --stem <stem>   |   live: watch --follow")


# ---------------------------------------------------------------- watch
def watch_events(seen):
    """Yield printable correlated events for artifacts that appeared since last poll."""
    out = []
    index = artifact_index()
    for stem, parts in sorted(index.items()):
        for suffix, path in sorted(parts.items()):
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            mtime = path.stat().st_mtime
            if time.time() - mtime > 3600 and not getattr(watch_events, "_replay", False):
                continue  # don't dump history on attach
            if suffix.endswith(".packet.txt"):
                phase = suffix.replace(".packet.txt", "").lstrip(".") or "initial"
                size = path.stat().st_size
                head = first_line(path.read_text(errors="replace"), 90)
                out.append((mtime, "REQUEST  %-12s %8s  %s\n           %s" % (
                    phase, nbytes(size), stem[:70], head)))
            elif suffix.endswith(".raw.json"):
                phase = suffix.replace(".raw.json", "").lstrip(".") or "initial"
                parsed = parse_raw(path)
                tok = parsed["tokens"]
                out.append((mtime, "RESPONSE %-12s %8s  %s\n           %s%s" % (
                    phase, nbytes(path.stat().st_size), stem[:70],
                    "%s in=%s out=%s cache_r=%s stop=%s%s" % (
                        parsed["kind"], tok.get("in", 0), tok.get("out", 0),
                        tok.get("cache_r", 0), parsed["stop"],
                        " cost=$%.4f" % parsed["cost"] if isinstance(parsed.get("cost"), (int, float)) else ""),
                    " ERROR: " + parsed["error"][:120] if parsed["error"] else "")))
            elif suffix == ".json":
                try:
                    receipt = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                model = (receipt.get("model") or {})
                out.append((mtime, "RECEIPT  %-12s %8s  %s\n           outcome=%s calls=%s next=%s" % (
                    "", nbytes(path.stat().st_size), stem[:70],
                    receipt.get("outcome"),
                    model.get("telemetry", {}).get("model_calls", "?"),
                    (receipt.get("next_action") or receipt.get("failure_category") or "-"))))
            elif suffix == ".lookup.jsonl":
                try:
                    count = sum(1 for _ in open(path, errors="replace"))
                except OSError:
                    count = 0
                out.append((mtime, "KNOWLEDGE lookup=%d lines  %s" % (count, stem[:70])))
    out.sort(key=lambda item: item[0])
    return out


def cmd_watch(args):
    watch_events._replay = args.replay
    seen = set()
    if not args.follow:
        args.replay = True
    if args.follow:
        # mark everything already on disk as seen so we only show new activity
        for stem, parts in artifact_index().items():
            for path in parts.values():
                seen.add(str(path))
        print("watching %s (Ctrl-C to stop)" % RUNS, flush=True)
        while True:
            for _, line in watch_events(seen):
                print(iso(_)[11:] + " " + line, flush=True)
            if wire_tap is not None and wire_tap.enabled():
                for row in wire_tap.records()[-40:]:
                    key = ("tap", row.get("call_id"), row.get("event"), row.get("epoch"))
                    if key in seen:
                        continue
                    seen.add(key)
                    if row.get("event") == "spawn":
                        print(iso(row["epoch"])[11:] + " TAP      " + wire_tap.human(row), flush=True)
            time.sleep(1)
    for _, line in watch_events(seen):
        print(iso(_)[11:] + " " + line)


# ---------------------------------------------------------------- show
def resolve_stem(args):
    index = artifact_index()

    def newest(candidates):
        return max(candidates, key=lambda s: max(p.stat().st_mtime for p in index[s].values()))

    if args.stem:
        matches = [s for s in index if args.stem in s]
        if not matches:
            raise SystemExit("no run artifacts match %r" % args.stem)
        return newest(matches), index
    receipts = [s for s in index if ".json" in index[s]]
    pool = receipts or list(index)
    if not pool:
        raise SystemExit("no run artifacts under %s" % RUNS)
    return newest(pool), index


def cmd_show(args):
    stem, index = resolve_stem(args)
    parts = index[stem]
    print("STEM   %s" % stem)
    for suffix in sorted(parts):
        print("  %-28s %8s  %s" % (suffix, nbytes(parts[suffix].stat().st_size), parts[suffix]))

    packet = parts.get(".packet.txt")
    if packet:
        text = packet.read_text(errors="replace")
        print("\n" + "=" * 100)
        print("SENT TO THE MODEL  (%s, %d bytes, sha=%s)" % (
            packet.name, len(text),
            __import__("hashlib").sha256(text.encode()).hexdigest()[:16]))
        print("=" * 100)
        print(text if args.full else text[:args.heads])
        if not args.full and len(text) > args.heads:
            print("\n... %d more bytes; --full prints everything, or: less %s" % (
                len(text) - args.heads, packet))

    raw = parts.get(".raw.json")
    if raw:
        parsed = parse_raw(raw)
        print("\n" + "=" * 100)
        print("CAME BACK  (%s, kind=%s, stop=%s, tokens=%s)" % (
            raw.name, parsed["kind"], parsed["stop"], parsed["tokens"]))
        print("=" * 100)
        if parsed["error"]:
            print("ERROR: " + parsed["error"])
        print(parsed["text"] if args.full else parsed["text"][:args.heads])

    lookup = parts.get(".lookup.jsonl")
    if lookup and args.lookups:
        print("\n" + "=" * 100)
        print("CARD-KNOWLEDGE LOOKUPS  (%s)" % lookup.name)
        print("=" * 100)
        for line in open(lookup, errors="replace"):
            print(line.rstrip()[:300])

    receipt = parts.get(".json")
    if receipt:
        try:
            data = json.loads(receipt.read_text())
        except (OSError, ValueError):
            return
        print("\n" + "=" * 100)
        print("RECEIPT  (%s)" % receipt.name)
        print("=" * 100)
        print(json.dumps({"outcome": data.get("outcome"),
                         "failure_category": data.get("failure_category"),
                         "next_action": data.get("next_action"),
                         "model": data.get("model"),
                         "gates": data.get("gates")}, indent=2, sort_keys=True)[:3000])


# ---------------------------------------------------------------- pack
def build_packet(ticket_path, repo, no_tools=True, profile=None):
    ticket = json.loads(Path(ticket_path).read_text())
    packer = OPS / "scripts" / ("engine-pipeline-pack.py"
                                if ticket.get("work_type") == "engine"
                                else "map-ticket-spec-pack.py")
    cmd = [sys.executable, str(packer), "--ticket-spec", str(ticket_path), "--repo", str(repo)]
    if ticket.get("work_type") == "engine" and no_tools:
        cmd.append("--no-tools")
    proc = run(cmd, cwd=OPS, timeout=300)
    if proc.returncode != 0:
        raise SystemExit("packer failed (%d): %s" % (proc.returncode, proc.stderr[-500:]))
    packet = proc.stdout
    packet += ("\n\n## TICKET CONTRACT (enforced verbatim by the harness)\n"
               "scope.allowed_paths (edit nothing else):\n%s\n\ngates:\n%s\n" % (
                   "\n".join("- " + p for p in ticket.get("scope", {}).get("allowed_paths", [])),
                   "\n".join("- " + g for g in ticket.get("gates", []))))
    packet += ("\nrequired behavior:\n" +
               "\n".join("- " + rule for rule in ticket.get("required_behavior", [])))
    if profile == "claude-staged@1.0.0":
        from factory_ng_investigation import EVIDENCE_INSTRUCTIONS
        packet += "\n" + EVIDENCE_INSTRUCTIONS
    packet += ("\n## Vocabulary handoff\n"
              "Every new public ExecuteAbilityEffect case must be registered with regEffect in an "
              "allowed registry_*.go file, with executor and runtime test metadata. The registry "
              "literal is frozen. Parser-emitted effects must already be registered. "
              "The harness checks this before acceptance, in addition to every original gate.\n")
    packet += ("\nCompilation and testing are controlled separately by the dashboard. "
              "Do not run compilers, tests, benchmarks or generated test executables. "
              "Use source reads and return your proposed edit blocks; the harness owns validation.\n")
    return ticket, packet


def cmd_pack(args):
    repo = Path(args.repo or SOURCE)
    ticket, packet = build_packet(args.ticket, repo,
                                no_tools=not args.with_tools, profile=args.profile)
    print("TICKET %s" % ticket.get("id"))
    print("TITLE  %s" % ticket.get("title"))
    print("TYPE   %s   revision %s" % (ticket.get("work_type"),
                                      (ticket.get("source") or {}).get("revision")))
    print("PACKET %s bytes (%d lines)  produced by %s against %s" % (
        len(packet), packet.count("\n"),
        "engine-pipeline-pack.py" if ticket.get("work_type") == "engine"
        else "map-ticket-spec-pack.py", repo))
    print("\n--- sections ---")
    for line in packet.splitlines():
        if line.startswith("#"):
            print("  " + line[:120])
    print("\n--- packet ---")
    print(packet if args.full else packet[:args.heads])
    if args.out:
        Path(args.out).write_text(packet)
        print("\nwritten: %s" % args.out)


# ---------------------------------------------------------------- call
def cmd_call(args):
    if not args.yes:
        raise SystemExit("`call` spends real provider quota. Re-run with --yes to confirm.\n"
                        "(Nothing is applied, gated, receipted or pushed either way.)")
    ticket_path = Path(args.ticket)
    workdir = Path(tempfile.mkdtemp(prefix="factory-ng-debug-"))
    clone = workdir / "clone"
    try:
        print("cloning %s -> %s (hardlinked)" % (SOURCE, clone))
        proc = run(["git", "clone", "--quiet", "--local", str(SOURCE), str(clone)],
                  cwd=OPS, timeout=600)
        if proc.returncode != 0:
            raise SystemExit("clone failed: " + proc.stderr[-400:])
        ticket = json.loads(ticket_path.read_text())
        revision = (ticket.get("source") or {}).get("revision")
        if revision:
            proc = run(["git", "checkout", "--detach", revision], cwd=clone, timeout=120)
            if proc.returncode != 0:
                raise SystemExit("checkout %s failed: %s" % (revision, proc.stderr[-300:]))
        _, packet = build_packet(ticket_path, clone,
                               no_tools=not args.with_tools, profile=args.profile)
        print("\nREQUEST  %s bytes\n%s\n" % (len(packet),
                                            packet if args.full else packet[:args.heads]))
        env = os.environ.copy()
        env["KB_TICKET"] = str(ticket.get("id"))
        env["TICKET"] = str(ticket.get("id"))
        if wire_tap is not None and not wire_tap.enabled():
            wire_tap.enable(minutes=30, ticket=None)
            print("(wire tap enabled for this session)")
        print("calling %s / %s ..." % (args.engine, args.model))
        started = time.time()
        model = run([sys.executable, str(OPS / "scripts" / "model_call.py"),
                     "--engine", args.engine, "--model", args.model,
                     "--tier", ticket.get("work_type", "map")],
                    cwd=clone, stdin=packet, timeout=args.timeout, env=env)
        elapsed = time.time() - started
        print("\n" + "=" * 100)
        print("RESPONSE  exit=%d  %.1fs  stdout=%s bytes" % (
            model.returncode, elapsed, nbytes(len(model.stdout))))
        print("=" * 100)
        print(model.stdout if args.full else model.stdout[:args.heads])
        print("\n--- adapter stderr (tokens line, provider notes) ---")
        print(model.stderr[-2000:])
        if wire_tap is not None:
            print("\nfull wire record: python3 scripts/factory_ng_wire_tap.py --list")
    finally:
        if args.keep:
            print("\nclone kept at %s" % clone)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def add_heads(parser, default=4000):
    parser.add_argument("--heads", type=int, default=default,
                      help="bytes to print per section (default %d)" % default)
    parser.add_argument("--full", action="store_true", help="print everything")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="what is running, tap state, recent round trips").set_defaults(
        func=cmd_status)

    w = sub.add_parser("watch", help="correlated live round trips")
    w.add_argument("--follow", action="store_true", help="keep streaming")
    w.add_argument("--replay", action="store_true", help="include the last hour of artifacts")
    w.set_defaults(func=cmd_watch)

    s = sub.add_parser("show", help="dump one round trip in full")
    s.add_argument("--stem", help="run stem substring (default: most recent)")
    s.add_argument("--lookups", action="store_true", help="also print card-knowledge lookups")
    add_heads(s)
    s.set_defaults(func=cmd_show)

    p = sub.add_parser("pack", help="produce the prompt packet only (no model, free)")
    p.add_argument("--ticket", required=True)
    p.add_argument("--repo", help="checkout to read source from (default: canonical openmagic)")
    p.add_argument("--profile", default=None)
    p.add_argument("--with-tools", action="store_true", help="omit --no-tools like agentic profiles")
    p.add_argument("--out", help="also write the packet to this file")
    add_heads(p, 6000)
    p.set_defaults(func=cmd_pack)

    c = sub.add_parser("call", help="one live round trip in a throwaway clone (spends quota)")
    c.add_argument("--ticket", required=True)
    c.add_argument("--engine", default="claude")
    c.add_argument("--model", default="claude-sonnet-5")
    c.add_argument("--profile", default=None)
    c.add_argument("--with-tools", action="store_true")
    c.add_argument("--timeout", type=int, default=1900)
    c.add_argument("--keep", action="store_true", help="keep the throwaway clone")
    add_heads(c, 6000)
    c.set_defaults(func=cmd_call)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
