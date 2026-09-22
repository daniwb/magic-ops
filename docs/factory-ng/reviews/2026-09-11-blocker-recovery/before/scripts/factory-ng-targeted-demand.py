#!/usr/bin/env python3
"""Read-only exact member inventory for one current parser miss shape."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "test" / "openmagic"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def revision(source):
    return subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()


def pinned_members(path):
    measurement = json.loads(path.read_text())
    if measurement.get("schema") != "factory.targeted-demand/v1":
        raise ValueError("--members-from must be a factory.targeted-demand/v1 measurement")
    members = measurement.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("--members-from must contain one or more members")
    expected = {}
    for member in members:
        name, text_hash = member.get("name"), member.get("text_sha256")
        if not isinstance(name, str) or not isinstance(text_hash, str):
            raise ValueError("--members-from has an invalid member")
        if name in expected:
            raise ValueError("--members-from repeats member %s" % name)
        expected[name] = text_hash
    shape = measurement.get("shape")
    if not isinstance(shape, str) or not shape:
        raise ValueError("--members-from has no exact shape")
    return shape, expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shape", nargs="?", help="exact miss shape, e.g. loyalty_body:choose")
    parser.add_argument("--repo", type=Path, default=DEFAULT_SOURCE,
                        help="source checkout to measure (default: canonical openmagic checkout)")
    parser.add_argument("--members-from", type=Path,
                        help="pinned targeted-demand JSON; remeasure only its named, text-hashed members")
    parser.add_argument("--summary", action="store_true",
                        help="summarize every current miss shape without emitting card members")
    args = parser.parse_args()
    if args.summary and (args.shape or args.members_from):
        parser.error("--summary cannot be combined with a shape or --members-from")
    if not args.summary and not args.shape and not args.members_from:
        parser.error("provide a shape, --summary, or --members-from")
    if args.shape and args.members_from:
        parser.error("shape is read from --members-from; do not provide both")
    source = args.repo.resolve()
    parser_root = source / "scripts" / "paragraph"
    if not (parser_root / "reparse.py").is_file():
        parser.error("--repo must contain scripts/paragraph/reparse.py")
    sys.path.insert(0, str(parser_root))
    import reparse  # noqa: E402
    try:
        shape, expected_members = (pinned_members(args.members_from)
                                   if args.members_from else (args.shape, None))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    members, scanned, summary, unresolved = [], 0, {}, []
    for path in sorted(Path(reparse.CARDDB).glob("*.json")):
        if path.name.startswith("_"):
            continue
        cards = json.loads(path.read_text())
        for name, card in cards.items():
            if expected_members is not None and name not in expected_members:
                continue
            if expected_members is None and card.get("status") != "review":
                continue
            if expected_members is not None and card.get('status') not in ('review', 'auto'):
                parser.error('pinned member has unsupported status: %s' % name)
            scanned += 1
            text_hash = "sha256:" + hashlib.sha256((card.get("text") or "").encode()).hexdigest()
            if expected_members is not None and text_hash != expected_members[name]:
                parser.error("pinned member text changed: %s" % name)
            result = reparse.reparse_card(card)
            if expected_members is not None and not result.get('eligible'):
                unresolved.append({'name': name, 'misses': result.get('misses', [])})
            all_shapes = sorted({kind for kind, _ in result["misses"]})
            if args.summary:
                for shape in all_shapes:
                    matching = [detail for kind, detail in result["misses"] if kind == shape]
                    item = summary.setdefault(shape, {"member_count": 0, "sole_shape_members": 0,
                                                       "detail_counts": {}})
                    item["member_count"] += 1
                    item["sole_shape_members"] += (all_shapes == [shape])
                    for detail in matching:
                        item["detail_counts"][detail] = item["detail_counts"].get(detail, 0) + 1
            else:
                matching = [detail for kind, detail in result["misses"] if kind == shape]
                if matching:
                    members.append({"name": name, "details": matching,
                                    "all_miss_shapes": all_shapes,
                                    "text_sha256": text_hash})
    if expected_members is not None and scanned != len(expected_members):
        parser.error("pinned members missing: expected %d, found %d" %
                     (len(expected_members), scanned))
    source_info = {"repository": str(source), "revision": revision(source),
                   "parser_sha256": digest(parser_root / "reparse.py")}
    if args.summary:
        shapes = []
        for shape, item in summary.items():
            details = item["detail_counts"]
            shapes.append({"shape": shape, "member_count": item["member_count"],
                           "sole_shape_members": item["sole_shape_members"],
                           "multi_shape_members": item["member_count"] - item["sole_shape_members"],
                           "distinct_details": len(details),
                           "largest_exact_detail_cluster": max(details.values())})
        print(json.dumps({"schema": "factory.miss-summary/v1", "source": source_info,
                          "review_cards_scanned": scanned,
                          "shapes": sorted(shapes, key=lambda item: (-item["sole_shape_members"], -item["member_count"], item["shape"]))},
                         indent=2, sort_keys=True))
        return
    output = {"schema": "factory.targeted-demand/v1", "shape": shape,
                      "source": source_info, "review_cards_scanned": scanned,
                      "member_count": len(members), "members": members}
    if args.members_from:
        output["pinned_members_from"] = str(args.members_from.resolve())
        output["pinned_member_count"] = len(expected_members)
        output['pinned_unresolved_count'] = len(unresolved)
        output['pinned_unresolved_members'] = unresolved
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
