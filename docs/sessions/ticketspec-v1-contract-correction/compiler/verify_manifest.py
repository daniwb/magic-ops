#!/usr/bin/env python3
"""Read-only manifest verifier, with a stale-byte adversarial self-test."""
import pathlib, shutil, tempfile
from common import ROOT, file_digest, load

def verify(root):
    root=pathlib.Path(root);m=load(root/'manifest.json');declared={x['path']:x for x in m['artifacts']}
    try:
        import jsonschema
        jsonschema.Draft202012Validator(load(root/'schemas/session-manifest-v1.schema.json'),format_checker=jsonschema.FormatChecker()).validate(m)
    except jsonschema.ValidationError: raise ValueError('E_SCHEMA_SESSION_MANIFEST')
    actual={p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    if set(actual)!=set(declared):raise ValueError('E_MANIFEST_MEMBER_MISMATCH')
    for rel,path in actual.items():
        if file_digest(path)!=declared[rel]['sha256'] or path.stat().st_size!=declared[rel]['bytes']:raise ValueError('E_STALE_MANIFEST_BYTES')
    return 'OK'

def main():
    print(verify(ROOT))
    with tempfile.TemporaryDirectory() as td:
        dst=pathlib.Path(td)/'bundle';shutil.copytree(ROOT,dst);target=next(x for x in dst.rglob('*') if x.is_file() and x.name not in ('manifest.json',) and '__pycache__' not in x.parts);target.write_bytes(target.read_bytes()+b'x')
        try:verify(dst);got='NO_ERROR'
        except ValueError as ex:got=str(ex)
        if got!='E_STALE_MANIFEST_BYTES':raise AssertionError(got)
    print('OK stale-manifest-bytes E_STALE_MANIFEST_BYTES')

if __name__=='__main__':main()
