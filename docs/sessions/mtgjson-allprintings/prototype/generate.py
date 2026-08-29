#!/usr/bin/env python3
"""Deterministic MTGJSON AllPrintings audit and compact fixture generator."""

import argparse
import collections
import hashlib
import json
import lzma
import os


SCHEMA_PREFIX = "magic.mtgjson-allprintings"
AUDITED_CARD_FIELDS = [
    "uuid", "name", "faceName", "side", "layout", "otherFaceIds",
    "availability", "isOnlineOnly", "isRebalanced", "originalPrintings",
    "rebalancedPrintings", "number", "identifiers", "setCode", "language",
    "text", "types", "subtypes", "supertypes", "finishes", "frameVersion",
]
AUDITED_IDENTIFIER_FIELDS = [
    "scryfallOracleId", "scryfallId", "scryfallCardBackId", "mtgoId",
    "multiverseId", "tcgplayerProductId",
]
AUDITED_SET_FIELDS = [
    "code", "name", "type", "releaseDate", "isOnlineOnly", "isFoilOnly",
    "isNonFoilOnly", "isForeignOnly", "isPartialPreview", "parentCode",
    "baseSetSize", "totalSetSize", "languages", "cards", "tokens",
]


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    data = canonical_bytes(value)
    with open(path, "wb") as handle:
        handle.write(data)
    return sha256_bytes(data)


def load_xz(path):
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def present(obj, field):
    return field in obj and obj[field] is not None


def counter_dict(counter):
    return {str(key): counter[key] for key in sorted(counter, key=str)}


def compact_card(card, set_code=None):
    identifiers = card.get("identifiers") or {}
    return {
        "availability": card.get("availability"),
        "faceName": card.get("faceName"),
        "isOnlineOnly": card.get("isOnlineOnly"),
        "isRebalanced": card.get("isRebalanced"),
        "layout": card.get("layout"),
        "name": card.get("name"),
        "number": card.get("number"),
        "oracleTextSha256": sha256_bytes((card.get("text") or "").encode()),
        "originalPrintings": card.get("originalPrintings"),
        "otherFaceIds": card.get("otherFaceIds"),
        "rebalancedPrintings": card.get("rebalancedPrintings"),
        "scryfallOracleId": identifiers.get("scryfallOracleId"),
        "setCode": set_code or card.get("setCode"),
        "side": card.get("side"),
        "types": card.get("types"),
        "uuid": card.get("uuid"),
    }


def classify_edge(card, set_obj):
    layout = (card.get("layout") or "").lower()
    types = set(card.get("types") or [])
    name = card.get("name") or ""
    categories = set()
    if "Token" in types or layout == "token": categories.add("token")
    if card.get("isFunny") or set_obj.get("type") in {"funny", "memorabilia"}: categories.add("funny")
    if "Battle" in types: categories.add("battle")
    if layout == "reversible_card": categories.add("reversible_card")
    if layout == "split": categories.add("split")
    if layout == "adventure": categories.add("adventure")
    if layout in {"transform", "modal_dfc", "double_faced_token"}: categories.add(layout)
    if layout == "meld": categories.add("meld")
    if len(card.get("otherFaceIds") or []) > 1: categories.add("unusual_multi_side")
    if " // " in name and card.get("side") not in {"a", "b"}: categories.add("unusual_multi_side")
    return categories


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-printings", required=True)
    parser.add_argument("--atomic", required=True)
    parser.add_argument("--prior-identity-audit", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    fixtures_dir = os.path.join(args.out, "fixtures")
    os.makedirs(fixtures_dir, exist_ok=True)

    root = load_xz(args.all_printings)
    atomic_root = load_xz(args.atomic)
    with open(args.prior_identity_audit, encoding="utf-8") as handle:
        prior = json.load(handle)

    sets = root["data"]
    cards = []
    card_set = {}
    card_collection = {}
    set_by_code = {}
    token_count = 0
    for set_key in sorted(sets):
        set_obj = sets[set_key]
        set_code = set_obj.get("code") or set_key
        set_by_code[set_code] = set_obj
        for collection_name in ("cards", "tokens"):
            for card in set_obj.get(collection_name) or []:
                cards.append(card)
                card_set[id(card)] = set_code
                card_collection[id(card)] = collection_name
                if collection_name == "tokens": token_count += 1

    card_field_presence = {field: 0 for field in AUDITED_CARD_FIELDS}
    identifier_presence = {field: 0 for field in AUDITED_IDENTIFIER_FIELDS}
    set_field_presence = {field: 0 for field in AUDITED_SET_FIELDS}
    layouts = collections.Counter()
    sides = collections.Counter()
    availability = collections.Counter()
    set_types = collections.Counter()
    set_online = collections.Counter()
    card_online = collections.Counter()
    languages = collections.Counter()
    missing_uuid = []
    missing_oracle = []
    uuid_rows = collections.defaultdict(list)
    oracle_rows = collections.defaultdict(list)
    number_key_rows = collections.defaultdict(list)
    other_face_edges = []
    edge_examples = collections.defaultdict(list)
    edge_counts = collections.Counter()
    rebalanced_rows = []
    projection_counts = collections.Counter()

    for set_key in sorted(sets):
        set_obj = sets[set_key]
        set_code = set_obj.get("code") or set_key
        for field in AUDITED_SET_FIELDS:
            set_field_presence[field] += int(present(set_obj, field))
        set_types[set_obj.get("type", "<missing>")] += 1
        set_online[str(set_obj.get("isOnlineOnly", "<missing>")).lower()] += 1
        for card in (set_obj.get("cards") or []) + (set_obj.get("tokens") or []):
            for field in AUDITED_CARD_FIELDS:
                card_field_presence[field] += int(present(card, field))
            identifiers = card.get("identifiers") or {}
            for field in AUDITED_IDENTIFIER_FIELDS:
                identifier_presence[field] += int(present(identifiers, field))
            layouts[card.get("layout", "<missing>")] += 1
            sides[card.get("side", "<missing>")] += 1
            card_online[str(card.get("isOnlineOnly", "<missing>")).lower()] += 1
            for item in card.get("availability") or ["<missing>"]:
                availability[item] += 1
            available = set(card.get("availability") or [])
            projection_counts["universal-occurrences-v1"] += 1
            if "paper" in available:
                projection_counts["paper-occurrences-v1"] += 1
            if available & {"arena", "mtgo", "dreamcast", "shandalar"}:
                projection_counts["digital-occurrences-v1"] += 1
            if "paper" not in available:
                projection_counts["nonpaper-occurrences-v1"] += 1
            languages[card.get("language", "<missing>")] += 1
            uuid = card.get("uuid")
            if not uuid:
                if len(missing_uuid) < 25: missing_uuid.append(compact_card(card, set_code))
            else:
                uuid_rows[uuid].append(card)
            oid = identifiers.get("scryfallOracleId")
            if not oid:
                if len(missing_oracle) < 100: missing_oracle.append(compact_card(card, set_code))
            else:
                oracle_rows[oid].append(card)
            product_key = (set_code, card.get("number"), card.get("language"))
            number_key_rows[product_key].append(card)
            for target in card.get("otherFaceIds") or []:
                other_face_edges.append((uuid, target))
            if card.get("isRebalanced") or card.get("originalPrintings") or card.get("rebalancedPrintings"):
                rebalanced_rows.append(compact_card(card, set_code))
            for category in classify_edge(card, set_obj):
                edge_counts[category] += 1
                if len(edge_examples[category]) < 12:
                    edge_examples[category].append(compact_card(card, set_code))
            if card_collection[id(card)] == "tokens":
                edge_counts["token_collection"] += 1
                if len(edge_examples["token_collection"]) < 12:
                    edge_examples["token_collection"].append(compact_card(card, set_code))

    uuid_set = set(uuid_rows)
    dangling_edges = [(source, target) for source, target in other_face_edges if target not in uuid_set]
    reciprocal_edges = sum((target, source) in set(other_face_edges) for source, target in other_face_edges)
    duplicate_uuids = {key: value for key, value in uuid_rows.items() if len(value) > 1}
    original_edges = [(c.get("uuid"), target) for c in cards for target in c.get("originalPrintings") or []]
    rebalanced_edges = [(c.get("uuid"), target) for c in cards for target in c.get("rebalancedPrintings") or []]
    reverse_rebalanced = {(target, source) for source, target in rebalanced_edges}
    duplicate_product_keys = [
        {"setCode": key[0], "number": key[1], "language": key[2], "count": len(value),
         "uuids": sorted(card.get("uuid") for card in value if card.get("uuid"))}
        for key, value in sorted(number_key_rows.items(), key=lambda item: str(item[0])) if len(value) > 1
    ]

    atomic_rows = []
    for parent_key in sorted(atomic_root["data"]):
        for card in atomic_root["data"][parent_key]:
            atomic_rows.append((parent_key, card))
    atomic_by_oracle = collections.defaultdict(list)
    for parent_key, card in atomic_rows:
        oid = (card.get("identifiers") or {}).get("scryfallOracleId")
        if oid:
            atomic_by_oracle[oid].append((parent_key, card))

    collision_ids = sorted({entry["source_unit_id"].split(":")[1]
                            for entry in prior["duplicate_source_identities"]})
    cross_parent_ids = sorted(entry["scryfall_oracle_id"]
                              for entry in prior["oracle_ids_in_multiple_parent_groups"])

    def compare_oracle_ids(ids):
        result = []
        for oid in ids:
            atomic_matches = atomic_by_oracle.get(oid, [])
            printing_matches = oracle_rows.get(oid, [])
            result.append({
                "scryfallOracleId": oid,
                "atomicRows": [
                    {"parentKey": parent, "faceName": card.get("name"), "side": card.get("side"),
                     "oracleTextSha256": sha256_bytes((card.get("text") or "").encode())}
                    for parent, card in atomic_matches
                ],
                "allPrintingsOccurrenceCount": len(printing_matches),
                "allPrintingsDistinctUuids": len({c.get("uuid") for c in printing_matches}),
                "allPrintingsSides": counter_dict(collections.Counter(c.get("side", "<missing>") for c in printing_matches)),
                "allPrintingsSetCodes": sorted({card_set[id(c)] for c in printing_matches}),
                "allPrintingsTextHashes": sorted({sha256_bytes((c.get("text") or "").encode()) for c in printing_matches}),
            })
        return result

    collision_comparison = compare_oracle_ids(collision_ids)
    cross_parent_comparison = compare_oracle_ids(cross_parent_ids)

    field_audit = {
        "schema": SCHEMA_PREFIX + "-field-audit/v1",
        "metadata": root.get("meta"),
        "setCount": len(sets),
        "occurrenceCount": len(cards),
        "cardCollectionCount": len(cards) - token_count,
        "tokenCollectionCount": token_count,
        "cardFieldPresence": card_field_presence,
        "identifierFieldPresence": identifier_presence,
        "setFieldPresence": set_field_presence,
        "breakdowns": {
            "availabilityMembership": counter_dict(availability),
            "cardIsOnlineOnly": counter_dict(card_online),
            "language": counter_dict(languages),
            "layout": counter_dict(layouts),
            "setIsOnlineOnly": counter_dict(set_online),
            "setType": counter_dict(set_types),
            "side": counter_dict(sides),
        },
        "namedProjectionCounts": counter_dict(projection_counts),
        "anomalies": {
            "missingUuidCount": len(cards) - sum(len(v) for v in uuid_rows.values()),
            "missingUuidExamples": missing_uuid,
            "missingScryfallOracleIdCount": len(cards) - sum(len(v) for v in oracle_rows.values()),
            "missingScryfallOracleIdExamples": missing_oracle,
            "duplicateSetNumberLanguageKeyCount": len(duplicate_product_keys),
            "duplicateSetNumberLanguageKeyExamples": duplicate_product_keys[:50],
        },
    }
    identity_audit = {
        "schema": SCHEMA_PREFIX + "-identity-audit/v1",
        "occurrenceCount": len(cards),
        "uuid": {
            "presentCount": sum(len(v) for v in uuid_rows.values()),
            "distinctCount": len(uuid_rows),
            "duplicateValueCount": len(duplicate_uuids),
            "duplicateRows": [compact_card(card, card_set[id(card)]) for values in duplicate_uuids.values() for card in values],
            "role": "unique MTGJSON printing/face occurrence identifier within the pinned snapshot",
            "crossSnapshotStability": "upstream contract; not longitudinally measured from one release",
        },
        "oracle": {
            "presentCount": sum(len(v) for v in oracle_rows.values()),
            "missingCount": len(cards) - sum(len(v) for v in oracle_rows.values()),
            "distinctCount": len(oracle_rows),
            "maxOccurrencesPerOracleId": max(map(len, oracle_rows.values())),
            "oracleIdsWithMultipleSides": sum(len({c.get("side") for c in values}) > 1 for values in oracle_rows.values()),
        },
        "otherFaceRelations": {
            "directedEdgeCount": len(other_face_edges),
            "selfEdgeCount": sum(source == target for source, target in other_face_edges),
            "danglingTargetCount": len(dangling_edges),
            "danglingExamples": dangling_edges[:50],
            "reciprocalDirectedEdgeCount": reciprocal_edges,
            "nonReciprocalDirectedEdgeCount": len(other_face_edges) - reciprocal_edges,
            "maxTargetsPerOccurrence": max((len(c.get("otherFaceIds") or []) for c in cards), default=0),
        },
        "candidateIdentityVerdict": {
            "sourceOccurrenceId": "mtgjson:<uuid>",
            "sourceOccurrenceIdAccepted": not duplicate_uuids and not missing_uuid,
            "oracleFaceId": "oracle:<scryfallOracleId>:<semantic-face>",
            "oracleFaceIdAcceptedWithRevision": True,
            "semanticFaceRule": "Use explicit side when present; otherwise 'none'. Treat the pair as semantic grouping, never occurrence uniqueness. Preserve missing Oracle IDs as null and do not invent identity from names or positions.",
            "revisionReason": "The pair is a semantic grouping shared by many printing occurrences, not an occurrence key. UUID remains occurrence authority; semantic-face value must be explicit and nullable-safe.",
        },
    }
    fixture_comparison = {
        "schema": SCHEMA_PREFIX + "-fixture-comparison/v1",
        "releaseEquality": {
            "allPrintings": root.get("meta"), "atomicCards": atomic_root.get("meta"),
            "sameRelease": root.get("meta") == atomic_root.get("meta"),
        },
        "priorAtomicCollisionFixture": {
            "priorDuplicateSourceIdentityCount": prior["duplicate_source_identity_count"],
            "expectedOracleIdCount": 3,
            "observedOracleIdCount": len(collision_ids),
            "cases": collision_comparison,
        },
        "priorAtomicCrossParentFixture": {
            "expectedOracleIdCount": 70,
            "observedOracleIdCount": len(cross_parent_ids),
            "cases": cross_parent_comparison,
        },
        "edgeCases": {
            key: {"occurrenceCount": edge_counts[key], "examples": edge_examples[key]}
            for key in sorted(set(edge_counts) | {"token", "funny", "battle", "reversible_card", "split", "adventure", "transform", "modal_dfc", "meld", "unusual_multi_side"})
        },
        "rebalancedRelations": {
            "rowCount": len(rebalanced_rows),
            "isRebalancedTrueCount": sum(c.get("isRebalanced") is True for c in cards),
            "originalPrintingsEdgeCount": len(original_edges),
            "rebalancedPrintingsEdgeCount": len(rebalanced_edges),
            "originalPrintingsDanglingTargetCount": sum(target not in uuid_set for _, target in original_edges),
            "rebalancedPrintingsDanglingTargetCount": sum(target not in uuid_set for _, target in rebalanced_edges),
            "originalEdgesWithReverseRebalancedEdgeCount": sum(edge in reverse_rebalanced for edge in original_edges),
            "examples": sorted(rebalanced_rows, key=lambda row: (row["uuid"] or ""))[:100],
        },
    }

    write_json(os.path.join(args.out, "field-audit.json"), field_audit)
    write_json(os.path.join(args.out, "identity-audit.json"), identity_audit)
    write_json(os.path.join(args.out, "fixture-comparison.json"), fixture_comparison)
    write_json(os.path.join(fixtures_dir, "edge-cases.json"), fixture_comparison["edgeCases"])
    write_json(os.path.join(fixtures_dir, "atomic-collisions.json"), fixture_comparison["priorAtomicCollisionFixture"])
    write_json(os.path.join(fixtures_dir, "atomic-cross-parent.json"), fixture_comparison["priorAtomicCrossParentFixture"])
    write_json(os.path.join(fixtures_dir, "rebalanced.json"), fixture_comparison["rebalancedRelations"])
    summary = {
        "schema": SCHEMA_PREFIX + "-run/v1",
        "metadata": root.get("meta"),
        "occurrenceCount": len(cards),
        "setCount": len(sets),
        "outputs": ["field-audit.json", "identity-audit.json", "fixture-comparison.json",
                    "fixtures/edge-cases.json", "fixtures/atomic-collisions.json",
                    "fixtures/atomic-cross-parent.json", "fixtures/rebalanced.json"],
    }
    write_json(os.path.join(args.out, "run.json"), summary)


if __name__ == "__main__":
    main()
