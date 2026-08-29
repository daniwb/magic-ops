#!/usr/bin/env python3
"""Top-level reproducible compile -> gates -> evaluate -> validate -> test -> finalize pipeline."""
import pathlib, subprocess, sys
from common import ROOT, tree_digest

NORMATIVE=('schemas','inputs','skills','outputs','fixtures/history')
def norm():
    return tuple((x,tree_digest(ROOT/x)) for x in NORMATIVE)
def run(rel):subprocess.run([sys.executable,str(ROOT/rel)],cwd=ROOT,check=True)

def pass_once():
    run('compiler/schema_gen.py');run('compiler/compile.py');run('compiler/gate_runner.py');run('compiler/readiness.py');run('compiler/validate.py')

def main():
    pass_once();first=norm();pass_once();second=norm()
    if first!=second:raise SystemExit('E_NORMATIVE_RERUN_DRIFT')
    run('compiler/test.py');run('compiler/validate.py');run('compiler/finalize.py');run('compiler/verify_manifest.py')
    print('OK pipeline: two normative-identical runs, unique history, manifest verified')

if __name__=='__main__':main()
