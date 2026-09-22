# Factory NG benchmark ticket

Implement support for the exact Oracle assertion:

`Target player draws two cards.`

Work from the current repository. Repair the complete production path from the
paragraph parser through `CardDefinition.ToGameCard`, cast-time targeting, and
Engine resolution. Do not special-case card names or this exact amount.

Requirements:

- `target player` emits a chosen-player target;
- existing `target opponent` and `each opponent` behavior is unchanged;
- unsupported `each player` and referential `that player` remain honest misses;
- the converted draw spell requires a player target and the chosen player—not
  automatically the controller—draws the cards;
- populate libraries in behavior tests;
- do not modify `backend/game`, `backend/cardfns`, generated corpus files, or
  unrelated code;
- add focused tests and run relevant regressions;
- keep the change generic and minimal.

You may inspect and edit the repository. Finish with a concise summary of files
changed and tests run. Do not commit, push, deploy, or touch external ticket
state.
