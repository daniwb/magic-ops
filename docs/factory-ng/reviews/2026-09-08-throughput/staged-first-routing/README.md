# Claude staged first; agentic investigates evidence only

The user authorized this policy on September 8 after the two latest completed
agentic runs used 2.09M and 1.89M raw processed tokens. This supersedes the earlier
decision to wait for the five-card trial before changing the ordinary Claude
route. The 200k–500k target remains unproven.

Ordinary Claude Map and Engine tickets now use `claude-staged@1.0.0`. The primary
worker's profile changed from agentic to staged. Other worker enablement and
usage settings were preserved. The controller no longer adds either Claude
agentic profile to implementation routes, and the ticket runner rejects direct
agentic implementation, including attempts to invoke an old immutable ticket.
Existing running jobs retain their process; subsequent dispatches follow the
new rule.

The staged worker first gets its prepared evidence and the existing one-round
deterministic NEED lookup. That lookup now also works for staged Map tickets.
If it still lacks essential source/API evidence, an explicit `EVIDENCE_GAP`
(question plus specific sources already examined), or an unresolved NEED,
can start one read-only agentic investigation. A vague AMBIGUOUS verdict,
provider error, coding/test failure, framework verdict, or valid new-primitive
request does not qualify. Compile/test mistakes retain the single existing
staged correction. Infrastructure and integration recovery keep their existing
factory paths.

The investigator uses the same physical worker lease, at most 12 turns and
300 seconds, with Read/Grep/Glob and the knowledge service. Shell, editing,
writing, web access and subagents are disabled. It returns source references,
never an implementation. The harness validates repository paths, line bounds,
source hashes and checkout cleanliness, then rereads up to six ranges (480
lines / 32k characters total) for staged. Investigator prose and patches are
not forwarded as implementation. Staged still owns both patch attempts, and
all original scope, named-test, package and integration gates remain intact.

If the investigation supplies no valid evidence, or staged still cannot
proceed, the observation parks visibly. There is no second investigation or
unbounded repair loop within an observation. Normal bounded infrastructure
retries remain separate. Historical terminal tickets are not silently reopened.

Receipts retain the staged evidence failure, investigator prompt/raw output,
validated source, staged continuation, and investigator telemetry. Total token
counters include helper spending; `investigation.telemetry` also exposes it
separately. An assisted staged observation is not a pure staged cost sample.
Exact-profile tickets, including the five-card cohort, remain unassisted; their
comparison cannot silently acquire another model.

Validation: 22 staged runner tests (including real Git clones, strict patch
application and real gates with mocked provider replies), four investigation
policy/adapter/reference tests, 65 controller tests, 19 reliability tests,
eight recovery tests and seven cohort tests passed: 125 total. The Claude
profiles and baseline validate. The full enabled-worker validation still fails
on the pre-existing MiniMax adapter registration/schema mismatch, which was
already present at startup and was not changed by this routing work.

The five-card trial currently has no complete cards: Siegfried failed its worker
gates after 149,836 raw tokens; Sigil parked after 128,201; the other cards are
pending. These are incomplete-card costs, not evidence that the target is met.
See the live cohort report for newer states.

No live game deployment was performed. `activation.json`, test logs and
`live-handoff.json` record the rollout. This checkout includes other ongoing
work; do not restore the entire worker configuration from `workers-before.json`.
