#!/usr/bin/env python3
import argparse,hashlib,json,os,sys

def canon(x): return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(); p.add_argument("out"); a=p.parse_args()
 comp=json.load(open(os.path.join(a.out,"policy-comparison.json")))
 audit=json.load(open(os.path.join(a.out,"identity-audit.json")))
 assert audit["audited_face_count"]==comp["raw_face_count"]
 for pid,v in sorted(comp["policies"].items()):
  d=v["descriptor"]; path=os.path.join(a.out,d["member_manifest"]); b=open(path,"rb").read()
  lines=b.splitlines(keepends=True); assert all(x.endswith(b"\n") for x in lines)
  rows=[json.loads(x) for x in lines]; assert len(rows)==d["member_count"]==v["included"]["face_count"]
  assert len({x["parent_id"] for x in rows})==d["parent_count"]==v["included"]["parent_count"]
  assert sha(b)==d["sorted_member_manifest_sha256"]
  assert rows==sorted(rows,key=lambda x:(x["source_unit_id"],x["parent_id"],x["source_text_sha256"]))
  assert all(canon(x)==line for x,line in zip(rows,lines))
  snap={"raw_corpus_sha256":d["raw_corpus_sha256"],"policy_hash":d["policy_sha256"],"normalizer_hash":d["normalizer_sha256"],"member_manifest_sha256":d["sorted_member_manifest_sha256"]}
  assert d["snapshot_id"]=="sha256:"+sha(canon(snap))
 print("VALID: 3 policies; canonical manifests and conservation checks passed")
if __name__=="__main__": main()
