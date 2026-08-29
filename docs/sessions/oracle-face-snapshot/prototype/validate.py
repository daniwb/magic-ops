#!/usr/bin/env python3
import argparse, hashlib, json, lzma, os
def load(p):
 b=open(p,"rb").read(); v=json.loads(b); assert b==(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode(); return v
def main():
 a=argparse.ArgumentParser(); a.add_argument("out"); x=a.parse_args(); g=load(os.path.join(x.out,"group-audit.json")); r=load(os.path.join(x.out,"relation-audit.json")); p=load(os.path.join(x.out,"projection-audit.json")); run=load(os.path.join(x.out,"run.json"))
 assert g["occurrenceCount"]==g["mappedOccurrenceCount"]==run["occurrenceCount"]
 assert g["semanticFaceGroupCount"]==g["canonicalFaceIdDistinctCount"]==run["semanticFaceGroupCount"]
 assert g["canonicalCount"]+g["quarantinedCount"]==g["semanticFaceGroupCount"]
 assert not g["missingIdentityRows"] and not g["invalidOracleIds"] and not g["invalidSides"] and not r["danglingTargets"]
 assert p["paperNonpaperPartition"]["sum"]==p["universalCount"] and p["paperNonpaperPartition"]["exact"]
 for v in p["projections"].values(): assert v.get("included",0)+v.get("excluded",0)==p["universalCount"]
 inv=g["inventory"]; assert hashlib.sha256(open(inv["path"],"rb").read()).hexdigest()==inv["sha256"]
 n=0
 with lzma.open(inv["path"],"rt",encoding="utf-8") as f:
  for line in f: json.loads(line); n+=1
 assert n==inv["recordCount"]; print("validation passed")
if __name__=="__main__": main()
