# Factory NG Skills v1

These project Skills are compact, model-neutral “how to work here” contracts.
The profile adapter supplies model-specific prompting/execution; a TicketSpec
selects a Skill and the harness enforces its named gates. They are deliberately
not Codex-global skills and do not create a second workflow engine.
