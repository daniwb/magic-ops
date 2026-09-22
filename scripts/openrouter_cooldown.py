#!/usr/bin/env python3
"""Durable provider-wide OpenRouter 429 cooldown state.

Consecutive rate limits use a 60s, 180s, 300s schedule (capped at 300s).
Any successful request that started after the latest 429 resets the sequence.
The state is shared by every OpenRouter adapter and Factory NG worker.
"""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import time


SCHEMA = "factory.openrouter-cooldown/v1"
DELAYS = (60, 180, 300)
DEFAULT_STATE = str(Path(__file__).resolve().parents[1] / "state/openrouter-cooldown.json")


def state_path():
    return Path(os.environ.get("OPENROUTER_COOLDOWN_STATE", DEFAULT_STATE))


def empty_state():
    return {
        "schema": SCHEMA,
        "consecutive_429s": 0,
        "paused_until_epoch": 0,
        "status": "ready",
    }


def _load(path):
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return empty_state()
    if value.get("schema") != SCHEMA:
        return empty_state()
    return value


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def status(now_epoch=None):
    current = time.time() if now_epoch is None else now_epoch
    value = _load(state_path())
    until = float(value.get("paused_until_epoch", 0) or 0)
    value["allowed"] = current >= until
    value["remaining_seconds"] = max(0, int(math.ceil(until - current)))
    value["status"] = "ready" if value["allowed"] else "paused"
    return value


def record_rate_limit(model=None, now_epoch=None):
    current = time.time() if now_epoch is None else now_epoch
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        value = _load(path)
        count = max(0, int(value.get("consecutive_429s", 0))) + 1
        delay = DELAYS[min(count - 1, len(DELAYS) - 1)]
        until = current + delay
        value.update({
            "schema": SCHEMA,
            "status": "paused",
            "consecutive_429s": count,
            "cooldown_seconds": delay,
            "last_429_epoch": current,
            "last_429_at": _iso(current),
            "paused_until_epoch": until,
            "paused_until": _iso(until),
        })
        if model:
            value["last_model"] = model
        _write(path, value)
        return status(current)


def record_success(request_started_epoch=None, model=None, now_epoch=None):
    current = time.time() if now_epoch is None else now_epoch
    started = current if request_started_epoch is None else request_started_epoch
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        value = _load(path)
        # A response from a request that predates a newer 429 must not clear
        # that newer pause in a concurrent worker.
        if started < float(value.get("last_429_epoch", 0) or 0):
            return status(current)
        value = empty_state()
        value.update({"last_success_epoch": current, "last_success_at": _iso(current)})
        if model:
            value["last_model"] = model
        _write(path, value)
        return status(current)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "rate-limit", "success"))
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.action == "rate-limit":
        value = record_rate_limit(args.model)
    elif args.action == "success":
        value = record_success(model=args.model)
    else:
        value = status()
    print(json.dumps(value, sort_keys=True))
    raise SystemExit(0 if value.get("allowed") else 1)


if __name__ == "__main__":
    main()
