#!/usr/bin/env python3
"""Leitet aus primitive-catalog.md eine knappe Karten-Worker-Version ab:
pro Primitiv 1 Zeile (Signatur + [dur] + ~12-Wort-Kurzbeschreibung),
Warnungs-/Muster-Absätze bleiben erhalten. Kein Modell-Token."""
import re, sys, os
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'primitive-catalog.md')
lines = open(src).read().split('\n'); out=[]; i=0
while i < len(lines):
    l = lines[i]
    if l.startswith('- `'):
        entry=[l]; j=i+1
        while j < len(lines) and not lines[j].startswith('- ') and not lines[j].startswith('#') and lines[j].strip()!='':
            entry.append(lines[j]); j+=1
        full=' '.join(x.strip() for x in entry)
        sig=re.match(r'(- `[^`]+`)', full); sig=sig.group(1) if sig else full[:90]
        dur=''; m=re.search(r'\[dur:[^\]]*\]', full)
        if m: dur=' ['+m.group(0)[5:].strip(' ]')+']'
        rest=re.sub(r'\([a-zA-Z0-9/._-]+\.go\)','', full[len(sig):])
        rest=re.sub(r'\*\*\[dur:[^\]]*\]\*\*','', rest).strip(' —*`')
        desc=' '.join(re.sub(r'\s+',' ',rest).split(' ')[:12])
        out.append(f"{sig} — {desc}{dur}".rstrip()); i=j
    else:
        out.append(l); i+=1
sys.stdout.write('\n'.join(out))
