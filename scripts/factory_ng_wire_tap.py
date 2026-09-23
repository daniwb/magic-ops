#!/usr/bin/env python3
"""factory_ng_wire_tap.py — opt-in, self-expiring recorder for the model wire.

Factory NG already keeps the request packet and the raw provider response per
attempt under ``docs/factory-ng/runs/``.  What it never recorded was the exact
provider invocation (argv, system prompt, HTTP body) and the correlated
request/response pair for one round trip.  This module closes that gap without
changing any behaviour when it is off.

Switch file: ``state/factory-ng-wire-tap.json`` (gitignored).  Every
``model_call.py`` invocation is a fresh process, so the switch is honoured by
the next call -- no controller restart, no cache flush.

  {"enabled": true,
   "expires_at": "2026-09-22T22:00:00Z",   # hard stop, so the tap cannot run forever
   "max_record_bytes": 400000,             # per recorded blob, head+tail kept
   "max_total_bytes": 200000000,           # tap dir budget; auto-disables past it
   "ticket": null}                         # optional: only tap one ticket

Records land in ``state/wire-tap/wire-YYYYMMDD.jsonl`` as one JSON object per
line, correlated by ``call_id``:

  request   the prompt bytes that arrived on model_call.py's stdin
  spawn     the argv of each provider subprocess (claude/codex/goose)
  response  the raw provider payload handed to save_raw()
  summary   exit code, wall time, stdout size, stderr tail

Usage:
  python3 scripts/factory_ng_wire_tap.py --on --minutes 90
  python3 scripts/factory_ng_wire_tap.py --status
  python3 scripts/factory_ng_wire_tap.py --follow
  python3 scripts/factory_ng_wire_tap.py --list
  python3 scripts/factory_ng_wire_tap.py --show <call_id>
  python3 scripts/factory_ng_wire_tap.py --off
"""
import argparse
import fcntl
import glob
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
SWITCH = OPS / "state" / "factory-ng-wire-tap.json"
DEFAULT_DIR = OPS / "state" / "wire-tap"

DEFAULT_MINUTES = 90
DEFAULT_MAX_RECORD_BYTES = 400_000
DEFAULT_MAX_TOTAL_BYTES = 200_000_000

_state_cache = {"mtime": None, "config": None}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def config():
    """Current tap configuration, or None when the tap is off.

    Re-read per call but cached on file mtime so a hot loop pays one stat().
    Expired switches report as off and are turned off on disk once.
    """
    try:
        mtime = SWITCH.stat().st_mtime
    except OSError:
        return None
    if _state_cache["mtime"] == mtime:
        cfg = _state_cache["config"]
    else:
        try:
            cfg = json.loads(SWITCH.read_text())
        except (OSError, ValueError):
            return None
        _state_cache["mtime"] = mtime
        _state_cache["config"] = cfg
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        return None
    expires = _parse_iso(cfg.get("expires_at"))
    if expires is not None and expires <= _now():
        disable(reason="expired")
        return None
    return cfg


def enabled():
    return config() is not None


def tap_dir(cfg=None):
    cfg = cfg or config() or {}
    raw = cfg.get("dir") or str(DEFAULT_DIR)
    path = Path(raw)
    if not path.is_absolute():
        path = OPS / path
    return path


def _budget_exceeded(cfg, directory):
    limit = int(cfg.get("max_total_bytes", DEFAULT_MAX_TOTAL_BYTES))
    used = 0
    for name in glob.glob(str(directory / "*.jsonl")):
        try:
            used += os.path.getsize(name)
        except OSError:
            pass
    return used >= limit, used


def record(event, **fields):
    """Append one record. Never raises into the caller -- a broken tap must not
    take a worker down with it."""
    cfg = config()
    if cfg is None:
        return None
    try:
        only = cfg.get("ticket")
        if only:
            watched = {str(only)}
            seen = {str(fields.get(k)) for k in ("ticket", "ticket_spec", "KB_TICKET")}
            seen |= {str(os.environ.get(k, "")) for k in ("TICKET", "KB_TICKET", "FACTORY_TICKET")}
            if not (watched & {s for s in seen if s}):
                return None
        directory = tap_dir(cfg)
        directory.mkdir(parents=True, exist_ok=True)
        over, used = _budget_exceeded(cfg, directory)
        if over:
            disable(reason="disk budget %d bytes reached" % used)
            return None
        line = json.dumps(_decorate(event, fields, cfg), sort_keys=True, default=str)
        line = _shrink(line, int(cfg.get("max_record_bytes", DEFAULT_MAX_RECORD_BYTES)))
        target = directory / ("wire-%s.jsonl" % _now().strftime("%Y%m%d"))
        with open(target, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.write(line.rstrip("\n") + "\n")
                handle.flush()
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        return target
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the wire
        try:
            sys.stderr.write("wire-tap: disabled after error: %s\n" % exc)
        except Exception:
            pass
        return None


def _decorate(event, fields, cfg):
    out = {
        "ts": _iso(),
        "epoch": time.time(),
        "event": event,
        "pid": os.getpid(),
        "engine": os.environ.get("TAP_ENGINE"),
        "model": os.environ.get("TAP_MODEL"),
        "tier": os.environ.get("TAP_TIER"),
        "phase": os.environ.get("FACTORY_GOOSE_PHASE"),
        "ticket": os.environ.get("KB_TICKET") or os.environ.get("TICKET"),
        "call_id": os.environ.get("TAP_CALL_ID"),
    }
    out.update({k: v for k, v in fields.items() if v is not None})
    out = {k: v for k, v in out.items() if v is not None}
    if not out.get("call_id"):
        out["call_id"] = call_id()
    return out


def call_id():
    return "%s-%d-%s" % (_now().strftime("%Y%m%dT%H%M%SZ"), os.getpid(),
                        hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:6])


def _shrink(line, limit):
    if len(line) <= limit:
        return line
    keep = max(limit // 2 - 64, 256)
    omitted = len(line) - (2 * keep)
    return line[:keep] + ("\n...<<truncated %d bytes>>...\n" % omitted) + line[-keep:]


def clip(text, limit=DEFAULT_MAX_RECORD_BYTES):
    """Head+tail clip for a single blob so the JSON envelope survives."""
    if text is None:
        return None
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    keep = max(limit // 2 - 64, 256)
    return text[:keep] + ("\n...<<clipped %d of %d bytes>>...\n" % (len(text), len(text))) + text[-keep:]


def enable(minutes=DEFAULT_MINUTES, directory=None, max_record_bytes=None,
          max_total_bytes=None, ticket=None):
    cfg = {
        "enabled": True,
        "started_at": _iso(),
        "expires_at": _iso(_now() + timedelta(minutes=int(minutes))),
        "dir": str(directory or DEFAULT_DIR),
        "max_record_bytes": int(max_record_bytes or DEFAULT_MAX_RECORD_BYTES),
        "max_total_bytes": int(max_total_bytes or DEFAULT_MAX_TOTAL_BYTES),
        "ticket": ticket,
    }
    SWITCH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SWITCH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, SWITCH)
    _state_cache.update({"mtime": None, "config": None})
    return cfg


def disable(reason=None):
    if not SWITCH.exists():
        return None
    try:
        cfg = json.loads(SWITCH.read_text())
    except (OSError, ValueError):
        cfg = {}
    cfg["enabled"] = False
    cfg["disabled_at"] = _iso()
    if reason:
        cfg["disabled_reason"] = reason
    tmp = SWITCH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, SWITCH)
    _state_cache.update({"mtime": None, "config": None})
    return cfg


def status():
    cfg = config()
    raw = {}
    if SWITCH.exists():
        try:
            raw = json.loads(SWITCH.read_text())
        except (OSError, ValueError):
            raw = {}
    directory = tap_dir(cfg or raw)
    files = sorted(glob.glob(str(directory / "*.jsonl"))) if directory.exists() else []
    used = sum(os.path.getsize(f) for f in files)
    remaining = None
    if cfg and cfg.get("expires_at"):
        expires = _parse_iso(cfg["expires_at"])
        if expires:
            remaining = max(int((expires - _now()).total_seconds()), 0)
    return {
        "enabled": cfg is not None,
        "switch": str(SWITCH),
        "switch_state": raw.get("enabled"),
        "expires_at": (cfg or {}).get("expires_at"),
        "seconds_remaining": remaining,
        "ticket_filter": (cfg or {}).get("ticket"),
        "dir": str(directory),
        "files": [os.path.basename(f) for f in files],
        "bytes": used,
        "budget_bytes": int((cfg or raw).get("max_total_bytes", DEFAULT_MAX_TOTAL_BYTES)),
        "disabled_at": raw.get("disabled_at"),
        "disabled_reason": raw.get("disabled_reason"),
    }


def records(limit=None):
    directory = tap_dir(config() or {})
    out = []
    for name in sorted(glob.glob(str(directory / "*.jsonl"))):
        with open(name, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    if limit:
        out = out[-limit:]
    return out


def by_call(call_id_value):
    return [r for r in records() if r.get("call_id") == call_id_value]


def human(record_row):
    event = record_row.get("event")
    ts = (record_row.get("ts") or "")[11:19]
    head = "[%s] %-9s %s/%s %s" % (
        ts, event,
        record_row.get("engine") or "-",
        record_row.get("model") or "-",
        record_row.get("call_id") or "-")
    if record_row.get("phase"):
        head += " phase=%s" % record_row["phase"]
    if record_row.get("ticket"):
        head += " ticket=%s" % record_row["ticket"]
    detail = ""
    if event == "request":
        detail = "prompt=%s bytes sha=%s" % (record_row.get("prompt_bytes"),
                                           (record_row.get("prompt_sha256") or "")[:12])
    elif event == "spawn":
        detail = " ".join(record_row.get("argv") or [])[:200]
    elif event == "response":
        detail = "raw=%s bytes" % record_row.get("raw_bytes")
    elif event == "summary":
        detail = "exit=%s %sms out=%s bytes" % (record_row.get("exit"),
                                              record_row.get("duration_ms"),
                                              record_row.get("stdout_bytes"))
    return (head + " | " + detail) if detail else head


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--on", action="store_true", help="start tapping (default 90 minutes)")
    ap.add_argument("--off", action="store_true", help="stop tapping")
    ap.add_argument("--status", action="store_true", help="print switch + storage state")
    ap.add_argument("--follow", action="store_true", help="stream records as they land")
    ap.add_argument("--list", action="store_true", help="list recorded call ids")
    ap.add_argument("--show", metavar="CALL_ID", help="print the full round trip for one call")
    ap.add_argument("--part", choices=["request", "response", "argv", "http_request", "summary"],
                    help="with --show: print only this part")
    ap.add_argument("--minutes", type=int, default=DEFAULT_MINUTES)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--max-record-bytes", type=int, default=None)
    ap.add_argument("--max-total-bytes", type=int, default=None)
    ap.add_argument("--ticket", default=None, help="only tap records for this ticket id")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.on:
        cfg = enable(args.minutes, args.dir, args.max_record_bytes,
                    args.max_total_bytes, args.ticket)
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return
    if args.off:
        print(json.dumps(disable("operator") or {"enabled": False}, indent=2, sort_keys=True))
        return
    if args.status:
        print(json.dumps(status(), indent=2, sort_keys=True))
        return
    if args.show:
        rows = by_call(args.show)
        if not rows:
            print("no records for call_id %s" % args.show, file=sys.stderr)
            raise SystemExit(1)
        part_event = {"argv": "spawn"}.get(args.part, args.part)
        for row in rows:
            if args.part:
                if row.get("event") == part_event:
                    payload = (row.get("prompt") or row.get("raw") or row.get("argv")
                             or row.get("body") or row)
                    if isinstance(payload, list):
                        print(" \\\n  ".join(payload))
                    else:
                        print(payload if isinstance(payload, str)
                              else json.dumps(payload, indent=2, sort_keys=True))
            else:
                print("=" * 100)
                print(json.dumps(row, indent=2, sort_keys=True))
        return
    if args.list:
        grouped = {}
        for row in records():
            grouped.setdefault(row.get("call_id"), []).append(row)
        for cid, rows in grouped.items():
            kinds = sorted({r.get("event") for r in rows})
            first = rows[0]
            print("%s  %-22s %-28s %-8s %s" % (
                cid, first.get("engine"), first.get("model"),
                first.get("phase"), ",".join(kinds)))
        return
    if args.follow:
        seen = 0
        while True:
            rows = records()
            for row in rows[seen:]:
                print(json.dumps(row, sort_keys=True) if args.json else human(row), flush=True)
            seen = len(rows)
            if not enabled():
                print("wire tap off (expired or disabled); %d records retained" % seen, flush=True)
                break
            time.sleep(1)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
