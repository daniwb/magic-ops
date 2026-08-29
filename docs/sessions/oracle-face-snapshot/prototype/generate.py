#!/usr/bin/env python3
"""Derive the deterministic Factory NG Oracle-face snapshot from AllPrintings."""
import argparse, collections, hashlib, json, lzma, os, re

SEMANTIC_FIELDS = ["text", "type", "types", "subtypes", "supertypes", "layout",
                   "manaCost", "colorIdentity", "keywords", "power", "toughness", "loyalty"]
PLATFORMS = ["arena", "mtgo", "dreamcast", "shandalar"]
OID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

def cb(v): return (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def write(path, v):
    b=cb(v); os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path,"wb") as f: f.write(b)
    return {"path":os.path.basename(path),"bytes":len(b),"sha256":sha(b)}
def key_obj(k): return {"scryfallOracleId":k[0],"side":k[1]}
def key_id(k): return "oracle:"+k[0]+":"+(k[1] if k[1] is not None else "none")
def norm(v):
    if isinstance(v,list): return sorted(v)
    return v
def semantic(c): return {f:norm(c.get(f)) for f in SEMANTIC_FIELDS}
def small_occ(r):
    c=r["card"]
    return {"sourceOccurrenceId":"mtgjson:"+c["uuid"],"setCode":r["setCode"],
            "sourceCollection":r["collection"],"name":c.get("faceName") or c.get("name"),
            "availability":sorted(c.get("availability") or []),"semantic":semantic(c)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--all-printings",required=True); ap.add_argument("--out",required=True); ap.add_argument("--inventory",required=True)
    a=ap.parse_args(); os.makedirs(a.out,exist_ok=True); os.makedirs(os.path.join(a.out,"fixtures"),exist_ok=True); os.makedirs(a.inventory,exist_ok=True)
    with lzma.open(a.all_printings,"rt",encoding="utf-8") as f: root=json.load(f)
    rows=[]; uuid_row={}; missing=[]; invalid_oid=[]; invalid_side=[]
    for sk in sorted(root["data"]):
        s=root["data"][sk]; sc=s.get("code") or sk
        for coll in ("cards","tokens"):
            for c in s.get(coll) or []:
                r={"card":c,"set":s,"setCode":sc,"collection":coll}; rows.append(r)
                u=c.get("uuid"); oid=(c.get("identifiers") or {}).get("scryfallOracleId"); side=c.get("side")
                if not u or not oid: missing.append({"uuid":u,"scryfallOracleId":oid,"setCode":sc,"number":c.get("number")})
                if oid and not OID_RE.match(oid): invalid_oid.append({"uuid":u,"value":oid})
                if side is not None and side not in "abcde": invalid_side.append({"uuid":u,"value":side})
                if u: uuid_row[u]=r
    groups=collections.defaultdict(list)
    for r in rows:
        c=r["card"]; oid=(c.get("identifiers") or {}).get("scryfallOracleId")
        if oid: groups[(oid,c.get("side"))].append(r)
    conflict_counts=collections.Counter(); conflict_examples=collections.defaultdict(list); group_records=[]
    size_dist=collections.Counter(); projections=collections.defaultdict(lambda:collections.Counter())
    relation_targets=collections.defaultdict(lambda:collections.defaultdict(set)); rel_edges=set(); reb_edges=set(); dangling=[]
    for k, rs in sorted(groups.items(),key=lambda x:(x[0][0],x[0][1] or "")):
        size_dist[len(rs)]+=1; variants={f:{json.dumps(norm(r["card"].get(f)),sort_keys=True,separators=(",",":")) for r in rs} for f in SEMANTIC_FIELDS}
        reasons=["semantic_conflict:"+f for f in SEMANTIC_FIELDS if len(variants[f])>1]
        for reason in reasons:
            conflict_counts[reason]+=1
            if len(conflict_examples[reason])<5: conflict_examples[reason].append({"oracleFaceKey":key_obj(k),"occurrences":[small_occ(r) for r in rs[:8]]})
        av=sorted({x for r in rs for x in (r["card"].get("availability") or [])})
        collections_=sorted({r["collection"] for r in rs}); set_types=sorted({r["set"].get("type") for r in rs})
        layouts=sorted({r["card"].get("layout") for r in rs}); types=sorted({x for r in rs for x in (r["card"].get("types") or [])})
        is_funny=any(r["card"].get("isFunny") is True or r["set"].get("type") in {"funny","memorabilia"} for r in rs)
        token=any(r["collection"]=="tokens" for r in rs)
        normal_ex=[]
        if token: normal_ex.append("exclude:token_template")
        if is_funny: normal_ex.append("exclude:funny_or_memorabilia")
        for layout in layouts:
            if layout in {"art_series","planar","scheme","vanguard","token","double_faced_token"}: normal_ex.append("exclude:layout:"+layout)
        memberships={"universal-oracle-faces-v1":(True,["include:oracle_id_present"]),
          "paper-oracle-faces-v1":("paper" in av,["include:paper_available"] if "paper" in av else ["exclude:no_paper_availability"]),
          "nonpaper-oracle-faces-v1":("paper" not in av,["include:no_paper_availability"] if "paper" not in av else ["exclude:paper_available"]),
          "digital-oracle-faces-v1":(bool(set(av)&set(PLATFORMS)),["include:digital_available"] if set(av)&set(PLATFORMS) else ["exclude:no_digital_availability"]),
          "normal-game-oracle-faces-candidate-v1":(not normal_ex, ["include:no_candidate_exclusion"] if not normal_ex else sorted(set(normal_ex))),
          "token-templates-v1":(token,["include:token_collection_provenance"] if token else ["exclude:not_token_collection"])}
        for p in PLATFORMS: memberships[p+"-oracle-faces-v1"]=(p in av,["include:"+p+"_available"] if p in av else ["exclude:no_"+p+"_availability"])
        for p,(inc,_) in memberships.items(): projections[p]["included" if inc else "excluded"]+=1
        rec={"schema":"magic.oracle-face/v1","oracleFaceId":key_id(k),"oracleFaceKey":key_obj(k),"status":"canonical" if not reasons else "quarantined",
             "quarantineReasons":reasons,"canonicalSemanticRevision":semantic(rs[0]["card"]) if not reasons else None,
             "occurrenceIds":sorted("mtgjson:"+r["card"]["uuid"] for r in rs),"occurrenceCount":len(rs),"availabilityUnion":av,
             "dimensions":{"sourceCollections":collections_,"setTypes":set_types,"layouts":layouts,"types":types,"funnyOrMemorabilia":is_funny},
             "memberships":{p:{"included":v[0],"reasonCodes":v[1]} for p,v in sorted(memberships.items())}}
        group_records.append(rec)
    uuid_key={u:((r["card"].get("identifiers") or {}).get("scryfallOracleId"),r["card"].get("side")) for u,r in uuid_row.items()}
    valid_keys=set(groups)
    for u,r in sorted(uuid_row.items()):
        sk=uuid_key[u]
        for field,typ in (("otherFaceIds","other_face"),("originalPrintings","derived_from_original"),("rebalancedPrintings","has_rebalanced_printing")):
            for target in r["card"].get(field) or []:
                tk=uuid_key.get(target)
                if not tk or tk not in valid_keys: dangling.append({"type":typ,"sourceUuid":u,"targetUuid":target})
                else:
                    edge=(typ,key_id(sk),key_id(tk)); (rel_edges if typ=="other_face" else reb_edges).add(edge)
                    relation_targets[typ][sk].add(tk)
    inconsistent=[]
    for typ, sources in relation_targets.items():
        for sk, targets in sources.items():
            per=[]
            for r in groups[sk]:
                raw=r["card"].get({"other_face":"otherFaceIds","derived_from_original":"originalPrintings","has_rebalanced_printing":"rebalancedPrintings"}[typ]) or []
                per.append(sorted(key_id(uuid_key[x]) for x in raw if x in uuid_key))
            if len({tuple(x) for x in per})>1: inconsistent.append({"type":typ,"source":key_obj(sk),"targetSets":sorted({tuple(x) for x in per})})
    inventory_name="oracle-face-snapshot.jsonl.xz"; inv_path=os.path.join(a.inventory,inventory_name)
    with lzma.open(inv_path,"wb",preset=9) as f:
        for rec in group_records: f.write(cb(rec))
    inv_hash=hashlib.sha256(open(inv_path,"rb").read()).hexdigest(); final=os.path.join(a.inventory,inv_hash+".jsonl.xz"); os.replace(inv_path,final)
    audit={"schema":"magic.oracle-face-group-audit/v1","metadata":root.get("meta"),"occurrenceCount":len(rows),"mappedOccurrenceCount":sum(len(x) for x in groups.values()),
      "semanticFaceGroupCount":len(groups),"canonicalCount":sum(not x["quarantineReasons"] for x in group_records),"quarantinedCount":sum(bool(x["quarantineReasons"]) for x in group_records),
      "groupSizeDistribution":{str(k):v for k,v in sorted(size_dist.items())},"maximumGroupSize":max(size_dist),"maximumGroupOccurrenceCount":max(map(len,groups.values())),
      "conflictReasonCounts":dict(sorted(conflict_counts.items())),"conflictExamples":dict(sorted(conflict_examples.items())),"missingIdentityRows":missing,"invalidOracleIds":invalid_oid,"invalidSides":invalid_side,
      "canonicalFaceIdDistinctCount":len({x["oracleFaceId"] for x in group_records}),"inventory":{"path":final,"bytes":os.path.getsize(final),"sha256":inv_hash,"recordCount":len(group_records)}}
    rel={"schema":"magic.oracle-face-relation-audit/v1","otherFace":{"edgeCount":len(rel_edges),"edges":[{"type":x[0],"sourceOracleFaceId":x[1],"targetOracleFaceId":x[2]} for x in sorted(rel_edges)],"inconsistentSourceGroups":inconsistent},
         "rebalanced":{"edgeCount":len(reb_edges),"edges":[{"type":x[0],"sourceOracleFaceId":x[1],"targetOracleFaceId":x[2]} for x in sorted(reb_edges)]},"danglingTargets":dangling,
         "sideCounts":dict(sorted(collections.Counter(k[1] if k[1] is not None else "<null>" for k in groups).items()))}
    proj={"schema":"magic.oracle-face-projection-audit/v1","universalCount":len(groups),"projections":{p:dict(c) for p,c in sorted(projections.items())},
          "paperNonpaperPartition":{"paper":projections["paper-oracle-faces-v1"]["included"],"nonpaper":projections["nonpaper-oracle-faces-v1"]["included"],"sum":projections["paper-oracle-faces-v1"]["included"]+projections["nonpaper-oracle-faces-v1"]["included"],"exact":True},
          "membershipDecisionsPerProjection":len(groups),"reprintWorkProof":{"occurrences":len(rows),"semanticMembers":len(groups),"maximumReprintsStillOneMember":max(map(len,groups.values()))}}
    write(os.path.join(a.out,"group-audit.json"),audit); write(os.path.join(a.out,"relation-audit.json"),rel); write(os.path.join(a.out,"projection-audit.json"),proj)
    cats={"conflict":[],"high-reprint":[],"multi-side":[],"rebalanced":[],"token":[],"funny":[],"battle":[],"split-adventure-dfc-meld":[]}
    maximum_group_occurrences=max(map(len,groups.values()))
    for rec in group_records:
        d=rec["dimensions"]; layouts=set(d["layouts"]); typ=set(d["types"])
        checks={"conflict":rec["status"]=="quarantined","high-reprint":rec["occurrenceCount"]==maximum_group_occurrences,"multi-side":any(x in {"c","d","e"} for x in [rec["oracleFaceKey"]["side"]]),"rebalanced":any(rec["oracleFaceId"] in (e[1],e[2]) for e in reb_edges),"token":"tokens" in d["sourceCollections"],"funny":d["funnyOrMemorabilia"],"battle":"Battle" in typ,"split-adventure-dfc-meld":bool(layouts&{"split","adventure","transform","modal_dfc","meld"})}
        for c,ok in checks.items():
            if ok and len(cats[c])<6: cats[c].append(rec)
    for c,v in cats.items(): write(os.path.join(a.out,"fixtures",c+".json"),{"schema":"magic.oracle-face-fixture/v1","category":c,"groups":v})
    write(os.path.join(a.out,"run.json"),{"schema":"magic.oracle-face-run/v1","metadata":root.get("meta"),"occurrenceCount":len(rows),"semanticFaceGroupCount":len(groups),"inventory":audit["inventory"]})

if __name__=="__main__": main()
