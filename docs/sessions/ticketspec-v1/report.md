# TicketSpec v1 implementation result

Status: `complete`

The session implements nine executable Draft 2020-12 schemas, a deterministic
read-only compiler, contract/hash/DAG/dedup/idempotence tests, negative
fixtures, and exactly one ready Map ticket. No production code or state was
changed.

The first adapter scans all 41,979 canonical Oracle-face records and admits only
canonical members of `normal-game-oracle-faces-candidate-v1`. Its bounded root
cause is the exact standalone assertion `Target player draws two cards.`.
Exact line equality recovers the complete positive class; nearby conjunctions
and sequencing variants are retained as negative evidence. Each member carries
structured Oracle identity, canonical semantic-revision hash, exact locator,
quarantine clearance, and relation status. The behavior is homogeneous:
`draw_cards(target_player, 2, resolve)`.

The compiled artifact keeps predicted unlock separate from original scope,
records the current complete gap set, pins implemented Engine behavior as a
dependency receipt, prohibits Engine paths, and requires discriminating,
honesty, regression, and full-scope remeasurement gates. Stages 4–7 remain
pending as required.

Architecture finding: projection policy and relation policy must be separately
hashed. This class is relation-independent, so unresolved multi-face semantic
relations do not leak into readiness. The existing `normal-game` projection is
still marked candidate upstream; its exact content hash is therefore pinned
and any change makes the premise stale rather than silently rebasing scope.
