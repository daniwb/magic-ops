"""Export the observed queue and distinct flow outcomes for the active goal."""
import json
from datetime import datetime, timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root=Path(__file__).resolve().parents[4]
review=Path(__file__).resolve().parent
latest=json.loads((root/'state/factory-ng-queue-trend.json').read_text())
rows=[]
for line in (root/'state/factory-ng-queue-trend.jsonl').read_text().splitlines():
 row=json.loads(line)
 if row['baseline_at']==latest['baseline_at']:rows.append(row)
(review/'queue-history.json').write_text(json.dumps(rows,indent=2)+'\n')
x=[datetime.fromtimestamp(r['epoch'],timezone.utc) for r in rows]
fig, axes=plt.subplots(2,1,figsize=(10,6.5),sharex=True,layout='constrained')
axes[0].plot(x,[r['waiting'] for r in rows],label='Waiting',color='#e39d22',linewidth=2)
axes[0].plot(x,[r['total_unfinished'] for r in rows],label='Waiting + running',color='#334155',linewidth=2)
axes[0].fill_between(x,[r['waiting'] for r in rows],[r['total_unfinished'] for r in rows],color='#94a3b8',alpha=.2,label='Running')
arrivals=[];unsuccessful=[];a=f=0
for row in rows:
 a+=len(row.get('arrivals',[])); f+=len(row.get('departed_without_completion',{}));arrivals.append(a);unsuccessful.append(f)
axes[1].step(x,[r['completed_since_baseline'] for r in rows],where='post',label='Completed',color='#16814c',linewidth=2)
axes[1].step(x,arrivals,where='post',label='Entries / reentries',color='#2563eb',linewidth=2)
axes[1].step(x,unsuccessful,where='post',label='Failed / other unsuccessful exits',color='#c23b45',linewidth=2)
for ax in axes:
 ax.grid(alpha=.2); ax.legend(loc='upper left',fontsize=9);ax.set_ylim(bottom=0);ax.set_ylabel('Tickets')
axes[0].set_title('Factory queue — observed backlog and outcomes',loc='left')
axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M',tz=timezone.utc))
axes[1].set_xlabel('15 September 2026 · UTC')
fig.savefig(review/'queue-trend.png',dpi=160)
print(review/'queue-trend.png')
