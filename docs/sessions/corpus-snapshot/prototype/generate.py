#!/usr/bin/env python3
"""Deterministic, read-only CorpusSnapshot v1 prototype."""

import argparse, collections, gzip, hashlib, json, os, subprocess

SCHEMA = "magic.corpus-snapshot/v1"
MEMBER_SCHEMA = "magic.corpus-snapshot-member/v1"
POLICIES = {
    "classifier-compatible-v1": {
        "description": "Current paragraph classifier-compatible population.",
        "exclude_layouts": ["emblem", "planar", "reversible_card", "scheme", "token", "vanguard"],
        "exclude_types": ["Attraction", "Battle", "Conspiracy", "Contraption", "Dungeon", "Hero", "Phenomenon", "Plane", "Scheme", "Stickers", "Vanguard"],
        "exclude_funny": True, "paper_product": False,
    },
    "schema-non-funny-v1": {
        "description": "All non-funny faces represented by AtomicCards; digital/rebalanced retained as dimensions.",
        "exclude_layouts": [], "exclude_types": [], "exclude_funny": True, "paper_product": False,
    },
    "paper-product-v1": {
        "description": "Paper/product-oriented legality proxy: non-funny and at least one Legal, Restricted, or Banned format status.",
        "exclude_layouts": [], "exclude_types": [], "exclude_funny": True, "paper_product": True,
    },
}

def canon(x): return (json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()
def git_state(path):
    def g(*args): return subprocess.run(["git","-C",path,*args],text=True,capture_output=True,check=True).stdout.rstrip("\n")
    return {"path":path,"sha":g("rev-parse","HEAD"),"dirty":bool(g("status","--porcelain")),"status_porcelain":g("status","--porcelain").splitlines()}
def dim(v): return "<missing>" if v is None or v=="" else str(v)
def legality_class(ls):
    vals=set((ls or {}).values())
    if "Legal" in vals: return "any_legal"
    if "Restricted" in vals: return "restricted_only"
    if "Banned" in vals: return "banned_or_not_legal"
    return "no_legal_format"
def parent_id(parent_key, faces):
    payload={"face_fingerprints":[sha(canon({
      "side":f.get("side"),"oracle":(f.get("identifiers") or {}).get("scryfallOracleId"),"text":f.get("text"),
      "layout":f.get("layout"),"types":f.get("types"),"mana_cost":f.get("manaCost")
    })) for f in faces]}
    return "parent-fallback-v1:"+sha(canon(payload))
def fallback_id(parent_stable, f):
    # Never uses name or array position. Content changes intentionally create a new fallback identity.
    payload={"parent_id":parent_stable,"side":f.get("side") or "none","layout":f.get("layout") or "",
      "mana_cost":f.get("manaCost") or "","text":f.get("text") or "","types":f.get("types") or [],
      "subtypes":f.get("subtypes") or [],"supertypes":f.get("supertypes") or []}
    return "fallback-v1:"+sha(canon(payload))
def exclusion(policy, f):
    reasons=[]
    if policy["exclude_funny"] and f.get("isFunny"): reasons.append("funny")
    if f.get("layout") in policy["exclude_layouts"]: reasons.append("layout:"+f.get("layout"))
    for t in sorted(set(f.get("types") or []) & set(policy["exclude_types"])): reasons.append("type:"+t)
    if policy["paper_product"]:
        if not any(v in ("Legal","Restricted","Banned") for v in (f.get("legalities") or {}).values()): reasons.append("no_paper_format_status")
    return reasons
def bump(c,k): c[dim(k)]+=1
def breakdown(members):
    out={k:collections.Counter() for k in ["layout","type","legality","digital","rebalanced","side"]}
    parents={}
    for m in members:
        bump(out["layout"],m["layout"])
        for t in m["types"] or ["<none>"]: bump(out["type"],t)
        bump(out["legality"],m["legality_class"]); bump(out["digital"],str(m["digital"]).lower())
        bump(out["rebalanced"],str(m["rebalanced"]).lower()); bump(out["side"],m["side"])
        parents[m["parent_id"]]=1
    return {"face_count":len(members),"parent_count":len(parents),**{k:dict(sorted(v.items())) for k,v in out.items()}}
def examples(rows, key, n=3):
    groups=collections.defaultdict(list)
    for r in rows:
        vals=r[key] if isinstance(r[key],list) else [r[key]]
        for v in vals or ["<none>"]:
            if len(groups[dim(v)])<n: groups[dim(v)].append({"source_unit_id":r["source_unit_id"],"parent_key":r["parent_key"],"face_name":r["face_name"]})
    return dict(sorted(groups.items()))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--corpus",required=True); ap.add_argument("--out",required=True); ap.add_argument("--project",required=True); ap.add_argument("--ops",required=True); a=ap.parse_args()
    os.makedirs(os.path.join(a.out,"manifests"),exist_ok=True)
    raw_hash=file_sha(a.corpus)
    with gzip.open(a.corpus,"rt",encoding="utf-8") as f: root=json.load(f)
    data=root["data"]; all_rows=[]; parent_groups={}
    for parent_key in sorted(data):
        faces=data[parent_key]; pid=parent_id(parent_key,faces); parent_groups[pid]=[]
        for f in faces:
            oid=(f.get("identifiers") or {}).get("scryfallOracleId"); side=f.get("side") or "none"
            sid=("oracle:"+oid+":"+side) if oid else fallback_id(pid,f)
            digital="unknown_not_exposed"; rebalanced="unknown_not_exposed"
            row={"schema":MEMBER_SCHEMA,"source_unit_id":sid,"identity_kind":"oracle_side" if oid else "fallback_v1",
              "scryfall_oracle_id":oid,"parent_id":pid,"parent_key":parent_key,"face_name":f.get("name") or "",
              "side":side,"layout":f.get("layout") or "","oracle_text":f.get("text") or "",
              "source_text_sha256":sha((f.get("text") or "").encode()),"types":f.get("types") or [],
              "subtypes":f.get("subtypes") or [],"legalities":f.get("legalities") or {},
              "legality_class":legality_class(f.get("legalities")),"printings":f.get("printings") or [],"funny":bool(f.get("isFunny")),
              "digital":digital,"rebalanced":rebalanced}
            all_rows.append(row); parent_groups[pid].append(row)
    all_rows.sort(key=lambda x:(x["source_unit_id"],x["parent_id"],x["source_text_sha256"]))
    # Identity audit across every schema-supported face, not merely an included policy.
    ids=collections.defaultdict(list); oracle_parents=collections.defaultdict(set)
    for r in all_rows: ids[r["source_unit_id"]].append(r); oracle_parents[r["scryfall_oracle_id"]].add(r["parent_id"]) if r["scryfall_oracle_id"] else None
    collisions=[]
    for sid,rs in sorted(ids.items()):
        if len(rs)>1: collisions.append({"source_unit_id":sid,"count":len(rs),"members":[{"parent_key":x["parent_key"],"face_name":x["face_name"],"side":x["side"],"text_sha256":x["source_text_sha256"]} for x in rs]})
    unexpected=[{"scryfall_oracle_id":oid,"parent_count":len(ps),"parent_ids":sorted(ps),"examples":[{"parent_key":r["parent_key"],"face_name":r["face_name"],"side":r["side"]} for r in all_rows if r["scryfall_oracle_id"]==oid][:8]} for oid,ps in sorted(oracle_parents.items()) if len(ps)>1]
    multif=[]
    for pid,rs in sorted(parent_groups.items()):
        if len(rs)>1:
            multif.append({"parent_id":pid,"parent_key":rs[0]["parent_key"],"face_count":len(rs),"sides":[r["side"] for r in rs],"unique_source_ids":len(set(r["source_unit_id"] for r in rs)),"layout":rs[0]["layout"]})
    ident={"schema":"magic.corpus-snapshot-identity-audit/v1","audited_face_count":len(all_rows),
      "missing_oracle_id_count":sum(not r["scryfall_oracle_id"] for r in all_rows),
      "missing_oracle_id_cases":[{k:r[k] for k in ["source_unit_id","parent_key","face_name","side","layout"]} for r in all_rows if not r["scryfall_oracle_id"]],
      "duplicate_source_identity_count":len(collisions),"duplicate_source_identities":collisions,
      "oracle_ids_in_multiple_parent_groups_count":len(unexpected),"oracle_ids_in_multiple_parent_groups":unexpected,
      "multi_face_parent_count":len(multif),"multi_face_findings":multif,
      "multi_face_nonunique_identity_count":sum(x["unique_source_ids"]!=x["face_count"] for x in multif),
      "fallback_rule":{"id":"fallback-v1","inputs":["content-derived parent_id","side","layout","mana_cost","oracle_text","types","subtypes","supertypes"],"prohibited_inputs":["card name","array position"],"stability":"Deterministic for identical input; changes when identity-relevant source content changes and therefore requires migration evidence."},
      "stability_implications":["Oracle ID + side survives printed-name changes when upstream retains the Oracle object.","Oracle object revisions that retain the Oracle ID keep identity even if text changes; text hash exposes revision.","Oracle object splits/merges or side reassignment require an explicit cross-snapshot alias/supersession manifest.","Fallback identities are deterministic but content-sensitive and must not be treated as durable cross-snapshot identity."]}
    open(os.path.join(a.out,"identity-audit.json"),"wb").write(canon(ident))
    comparisons={"schema":"magic.corpus-snapshot-policy-comparison/v1","raw_face_count":len(all_rows),"raw_parent_count":len(parent_groups),"policies":{}}
    descriptors=[]
    for policy_id,p in POLICIES.items():
        ph=sha(canon({"policy_id":policy_id,**p})); inc=[]; exc=[]
        for r in all_rows:
            # reconstruct filter-relevant fields from normalized row
            pseudo={"isFunny":r["funny"],"layout":r["layout"],"types":r["types"],"legalities":r["legalities"]}
            reasons=exclusion(p,pseudo)
            m={**r,"included_by_policy":not reasons,"exclusion_reason_codes":reasons}
            (inc if not reasons else exc).append(m)
        inc.sort(key=lambda x:x["source_unit_id"]); exc.sort(key=lambda x:(x["source_unit_id"],x["parent_id"]))
        member_bytes=b"".join(canon(x) for x in inc); mp=os.path.join(a.out,"manifests",policy_id+".members.jsonl"); open(mp,"wb").write(member_bytes)
        excluded_counts=collections.Counter(q for x in exc for q in x["exclusion_reason_codes"])
        desc={"schema":SCHEMA,"snapshot_id":"sha256:"+sha(canon({"raw_corpus_sha256":raw_hash,"policy_hash":ph,"normalizer_hash":sha(canon({"id":"corpus-snapshot-normalizer-v1"})),"member_manifest_sha256":sha(member_bytes)})),
          "policy_id":policy_id,"policy_sha256":ph,"normalizer_id":"corpus-snapshot-normalizer-v1","normalizer_sha256":sha(canon({"id":"corpus-snapshot-normalizer-v1"})),
          "raw_corpus_sha256":raw_hash,"member_count":len(inc),"parent_count":len(set(x["parent_id"] for x in inc)),"sorted_member_manifest_sha256":sha(member_bytes),"member_manifest":"manifests/"+policy_id+".members.jsonl"}
        db=canon(desc); open(os.path.join(a.out,"manifests",policy_id+".descriptor.json"),"wb").write(db); descriptors.append(desc)
        comparisons["policies"][policy_id]={"policy":p,"policy_sha256":ph,"included":breakdown(inc),"excluded_face_count":len(exc),"excluded_parent_count":len(set(x["parent_id"] for x in exc)),"exclusion_reason_counts":dict(sorted(excluded_counts.items())),
          "examples":{"layout":examples(inc,"layout"),"type":examples(inc,"types"),"legality":examples(inc,"legality_class"),"digital":examples(inc,"digital"),"rebalanced":examples(inc,"rebalanced"),"exclusion_reason":examples(exc,"exclusion_reason_codes")},"descriptor":desc}
    open(os.path.join(a.out,"policy-comparison.json"),"wb").write(canon(comparisons))
    # Stable machine summary consumed by finalize.py; excludes timestamps by design.
    run={"schema":"magic.corpus-snapshot-run/v1","corpus_metadata":root.get("meta") or {},"raw_corpus_path":os.path.abspath(a.corpus),"raw_corpus_sha256":raw_hash,"repositories":{"magic":git_state(a.project),"magic_ops":git_state(a.ops)},"descriptors":descriptors}
    open(os.path.join(a.out,"manifests","run.json"),"wb").write(canon(run))
if __name__=="__main__": main()
