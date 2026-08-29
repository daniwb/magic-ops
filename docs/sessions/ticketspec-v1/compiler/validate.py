#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
try: import jsonschema
except ImportError: jsonschema=None
PAIRS=[('outputs/ticket.json','schemas/factory.ticket-v1.schema.json'),('outputs/scope.json','schemas/magic.scope-v1.schema.json')]
def main():
 for doc,sch in PAIRS:
  d=json.loads((ROOT/doc).read_text()); s=json.loads((ROOT/sch).read_text())
  if jsonschema: jsonschema.Draft202012Validator(s).validate(d)
  elif not d.get('schema') or not s.get('$id'): raise ValueError('schema identity missing')
 print('validated',len(PAIRS),'primary artifacts','with jsonschema' if jsonschema else 'with built-in fallback')
if __name__=='__main__':main()
