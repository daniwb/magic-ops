#!/usr/bin/env python3
"""Snapshot the ticket dependency galaxy for the live dashboard view.

Builds the same node/edge graph as the one-off galaxy artifact (capability
shapes as nebula hubs via each ticket's declared "plan:<shape>" parent, plus
real Map<->Engine dependency edges from "parents"/"supersedes"), runs a
Fruchterman-Reingold force layout, and writes a compact JSON snapshot to
state/factory-ng-galaxy.json for the Go dispatcher to serve at
/factory-ng/galaxy.json.

Warm-starts from the previous snapshot's positions when present, so a
periodic re-run refines the existing layout instead of reshuffling it --
the picture should stay recognizable across refreshes, not jump around.
Costs ~10-30s at the current ticket count; intended to be re-run every few
minutes by factory-ng-viz-snapshot.py, not on every page load.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
JOBS = OPS / "state/factory-ng-jobs.json"
OUT = OPS / "state/factory-ng-galaxy.json"
PLAN = Path(os.environ.get("OPENMAGIC_BUILD_PLAN", "/opt/development/test/openmagic/corpus/build-plan.jsonl"))

GOLDEN = 137.508


def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def atomic_write(path, payload, compact=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-" + path.name)
    try:
        with os.fdopen(fd, "w") as handle:
            if compact:
                json.dump(payload, handle, separators=(",", ":"))
            else:
                json.dump(payload, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def extract_graph():
    plan_rows = [json.loads(line) for line in PLAN.read_text().splitlines() if line.strip()] if PLAN.is_file() else []
    plan_by_item = {row["item"]: row for row in plan_rows}
    jobs = (load_json(JOBS, {}) or {}).get("jobs", {})

    tickets = {}
    for path in TICKETS.glob("*.json"):
        ticket = load_json(path)
        if not ticket or not ticket.get("id"):
            continue
        tickets[ticket["id"]] = {
            "work_type": ticket.get("work_type"),
            "parents": ticket.get("parents") or [],
            "supersedes": ticket.get("supersedes"),
        }

    hub_ids = set()
    for t in tickets.values():
        for p in t["parents"]:
            if isinstance(p, str) and p.startswith("plan:"):
                hub_ids.add(p)

    nodes = {}
    for hub in hub_ids:
        item = hub[len("plan:"):]
        row = plan_by_item.get(item, {})
        nodes[hub] = {"id": hub, "kind": "hub", "label": item,
                      "rank": row.get("rank"), "unlock": row.get("marginal_unlock", 0) or 0}
    for tid, t in tickets.items():
        job = jobs.get(tid, {})
        nodes[tid] = {"id": tid, "kind": "ticket", "work_type": t["work_type"],
                      "state": job.get("state"), "outcome": job.get("outcome"),
                      "label": tid.replace("ticket:", "")}

    edges = []
    for tid, t in tickets.items():
        for p in t["parents"]:
            if not isinstance(p, str):
                continue
            if p.startswith("plan:"):
                if p in nodes:
                    edges.append({"a": tid, "b": p, "kind": "cluster"})
            elif p in tickets:
                edges.append({"a": tid, "b": p, "kind": "dependency"})
        if t["supersedes"] and t["supersedes"] in tickets:
            edges.append({"a": tid, "b": t["supersedes"], "kind": "revision"})

    return nodes, edges


def layout(nodes, edges, prior_positions, iterations):
    ids = list(nodes.keys())
    idx = {nid: i for i, nid in enumerate(ids)}
    n = len(ids)
    hub_idx = [i for i, nid in enumerate(ids) if nodes[nid]["kind"] == "hub"]

    W = 3400.0
    pos = None
    if np is not None:
        pos = np.zeros((n, 2))

    hub_pos = {}
    nhub = max(1, len(hub_idx))
    for k, i in enumerate(hub_idx):
        prior = prior_positions.get(ids[i])
        if prior:
            hub_pos[ids[i]] = (prior[0], prior[1])
        else:
            angle = 2 * math.pi * k / nhub
            r = W * 0.34
            hub_pos[ids[i]] = (r * math.cos(angle), r * math.sin(angle))
        pos[i] = hub_pos[ids[i]]

    ticket_hub = {}
    for e in edges:
        if e["kind"] == "cluster":
            ticket_hub.setdefault(e["a"], e["b"])

    rng = np.random.default_rng(7)
    for i, nid in enumerate(ids):
        if nodes[nid]["kind"] == "hub":
            continue
        prior = prior_positions.get(nid)
        if prior:
            pos[i] = (prior[0], prior[1])
            continue
        hub = ticket_hub.get(nid)
        if hub in hub_pos:
            hx, hy = hub_pos[hub]
            pos[i] = (hx + rng.normal(0, 160), hy + rng.normal(0, 160))
        else:
            pos[i] = (rng.uniform(-W * 0.55, W * 0.55), rng.uniform(-W * 0.55, W * 0.55))

    mass = np.ones(n)
    for i in hub_idx:
        mass[i] = 26.0

    degree = np.zeros(n)
    pairs, kinds = [], []
    for e in edges:
        a, b = idx.get(e["a"]), idx.get(e["b"])
        if a is None or b is None or a == b:
            continue
        pairs.append((a, b))
        kinds.append(e["kind"])
        degree[a] += 1
        degree[b] += 1
    mass += np.minimum(degree, 12) * 0.5

    pairs = np.array(pairs, dtype=np.int64)
    ea, eb = pairs[:, 0], pairs[:, 1]
    kind_arr = np.array(kinds)
    ideal_len = np.where(kind_arr == "cluster", 260.0, np.where(kind_arr == "revision", 70.0, 110.0))
    strength = np.where(kind_arr == "cluster", 0.55, np.where(kind_arr == "revision", 1.3, 1.15))

    k_repulse = 5200.0
    temperature = W * 0.03 if prior_positions else W * 0.045
    for _ in range(iterations):
        diff = pos[:, None, :] - pos[None, :, :]
        dist2 = np.sum(diff * diff, axis=2) + 0.01
        dist = np.sqrt(dist2)
        force = (k_repulse * k_repulse) / dist2
        force = force * (mass[:, None] * mass[None, :]) ** 0.5 / 8.0
        contrib = (diff / dist[:, :, None]) * force[:, :, None]
        disp = np.sum(contrib, axis=1)

        d = pos[ea] - pos[eb]
        dist = np.sqrt(np.sum(d * d, axis=1)) + 0.01
        f = strength * (dist - ideal_len)
        fx = (d / dist[:, None]) * f[:, None]
        np.add.at(disp, ea, -fx)
        np.add.at(disp, eb, fx)

        disp[hub_idx] *= 0.12

        dlen = np.sqrt(np.sum(disp * disp, axis=1)) + 1e-9
        capped = np.minimum(dlen, temperature)
        pos += (disp / dlen[:, None]) * capped[:, None]
        pos -= pos.mean(axis=0) * 0.002
        temperature *= 0.97

    return ids, pos, degree


def build(iterations):
    nodes, edges = extract_graph()
    prior = load_json(OUT, {}) or {}
    # Job state changes do not change geometry. Avoid the quadratic force
    # calculation for the same graph; gently settle additions on warm starts.
    topology = hashlib.sha256(json.dumps(
        [sorted(nodes), sorted((e['a'], e['b'], e['kind']) for e in edges)],
        separators=(',', ':')).encode()).hexdigest()
    prior_positions = {}
    if isinstance(prior, dict):
        for n in prior.get("nodes", []):
            if "x" in n and "y" in n and n.get("id"):
                prior_positions[n["id"]] = (n["x"], n["y"])

    if np is None or not nodes:
        return {"generated_at": None, "error": "numpy unavailable or empty graph", "nodes": [], "edges": []}

    if prior.get('topology') == topology and len(prior_positions) == len(nodes):
        iterations = 0
    elif prior_positions:
        iterations = min(iterations, 3)
    ids, pos, degree = layout(nodes, edges, prior_positions, iterations)

    hubs = sorted([n for n in nodes.values() if n["kind"] == "hub"], key=lambda h: -(h.get("unlock") or 0))
    hub_hue = {h["id"]: (208 + i * GOLDEN) % 360 for i, h in enumerate(hubs)}

    compact_nodes = []
    for i, nid in enumerate(ids):
        n = nodes[nid]
        x, y = round(float(pos[i][0]), 1), round(float(pos[i][1]), 1)
        if n["kind"] == "hub":
            compact_nodes.append({"id": nid, "k": "h", "l": n["label"], "x": x, "y": y,
                                  "u": n.get("unlock", 0), "r": n.get("rank"), "hue": round(hub_hue[nid], 1)})
        else:
            c = {"id": nid, "k": "t", "l": n["label"], "x": x, "y": y, "d": int(degree[i])}
            if n.get("work_type"):
                c["w"] = n["work_type"][0]
            if n.get("state"):
                c["s"] = n["state"]
            if n.get("outcome"):
                c["o"] = n["outcome"]
            compact_nodes.append(c)

    idx = {nid: i for i, nid in enumerate(ids)}
    kind_code = {"cluster": "c", "dependency": "d", "revision": "r"}
    compact_edges = [[idx[e["a"]], idx[e["b"]], kind_code[e["kind"]]] for e in edges
                     if e["a"] in idx and e["b"] in idx]

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "topology": topology,
        "nodes": compact_nodes,
        "edges": compact_edges,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--iterations", type=int, default=70,
                        help="fewer than a cold-start layout needs, since warm-starting only refines")
    args = parser.parse_args()
    t0 = time.time()
    payload = build(args.iterations)
    atomic_write(args.out, payload)
    print("galaxy snapshot: %d nodes in %.1fs" % (len(payload.get("nodes", [])), time.time() - t0))


if __name__ == "__main__":
    main()
