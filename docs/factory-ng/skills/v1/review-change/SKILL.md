---
name: review-change
description: Fresh-context review of one proposed product diff against its TicketSpec.
---

Read the TicketSpec, proposed changed paths, and raw gate evidence. Confirm
scope, positive behavior, adjacent negatives, and that the proposed diff is
the tested diff. Return `ACCEPT`, `REJECT`, or `SPLIT_REQUIRED` with concise
findings. Ordinary Map/Engine changes are judged by their TicketSpec gates;
this Skill does not introduce a separate audit process.
