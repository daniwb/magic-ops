#!/usr/bin/env python3
"""Validate canonical audit outputs and required conservation properties."""

import argparse
import hashlib
import json
import os


def load(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    value = json.loads(raw)
    canonical = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n").encode()
    assert raw == canonical, "non-canonical JSON: " + path
    return value


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    args = parser.parse_args()
    field = load(os.path.join(args.out, "field-audit.json"))
    identity = load(os.path.join(args.out, "identity-audit.json"))
    fixture = load(os.path.join(args.out, "fixture-comparison.json"))
    run = load(os.path.join(args.out, "run.json"))
    count = field["occurrenceCount"]
    assert count == run["occurrenceCount"] == identity["occurrenceCount"]
    assert count == identity["uuid"]["presentCount"]
    assert identity["uuid"]["distinctCount"] == count
    assert identity["uuid"]["duplicateValueCount"] == 0
    assert identity["candidateIdentityVerdict"]["sourceOccurrenceIdAccepted"]
    assert fixture["releaseEquality"]["sameRelease"]
    assert fixture["priorAtomicCollisionFixture"]["observedOracleIdCount"] == 3
    assert fixture["priorAtomicCrossParentFixture"]["observedOracleIdCount"] == 70
    relation = identity["otherFaceRelations"]
    assert relation["directedEdgeCount"] == relation["reciprocalDirectedEdgeCount"] + relation["nonReciprocalDirectedEdgeCount"]
    for relpath in run["outputs"]:
        assert os.path.isfile(os.path.join(args.out, relpath)), relpath
    manifest_path = os.path.join(args.out, "manifest.json")
    if os.path.isfile(manifest_path):
        manifest = load(manifest_path)
        assert manifest["status"] == "complete"
        assert manifest["reproducibility"]["byteIdentical"] is True
        assert manifest["temporaryPayloads"][0]["cleanupStatus"] == "deleted"
        for artifact in manifest["artifacts"]:
            path = os.path.join(args.out, artifact["path"])
            assert os.path.getsize(path) == artifact["bytes"], artifact["path"]
            assert file_hash(path) == artifact["sha256"], artifact["path"]
    print("validation passed")


if __name__ == "__main__":
    main()
