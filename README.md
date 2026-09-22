# magic-ops — Factory NG infrastructure

This repository contains the Factory NG control plane for the Magic
card-engine project: deterministic TicketSpec producers, model-specific worker
adapters, isolated-clone harnesses, immutable receipts, full-gate integration,
the operator dashboard, and supervision.

## Start here

- [`AGENTS.md`](AGENTS.md): mandatory session startup and safety rules.
- [`RUNBOOK.md`](RUNBOOK.md): current NG operations and recovery procedures.
- [`docs/factory-ng/CURRENT.md`](docs/factory-ng/CURRENT.md): canonical durable
  handoff and current implementation status.
- [`config/factory-ng-policy.json`](config/factory-ng-policy.json): queue,
  retry, integration, push, and deployment policy.
- [`config/factory-ng-workers.json`](config/factory-ng-workers.json): enabled
  workers and model profiles.
- [`config/factory-ng-producers.json`](config/factory-ng-producers.json):
  deterministic work producers.

The live dashboard is `http://localhost:9999/dashboard`. Factory NG queue and
execution truth lives in `docs/factory-ng/` and `state/factory-ng-*.json`, not
in historical dispatcher rows.

## Historical material

The evolution from earlier factories is preserved, not deleted, under
[`docs/archive/factory-evolution/`](docs/archive/factory-evolution/README.md).
Archived documents are reflection evidence and must not be used as current
operating instructions.
