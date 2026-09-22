# Ryzen remote verification

The user asked to add the Ryzen AI 395 at 192.168.1.251 to the queue. Read-only SSH
confirmed Fedora, 32 logical CPUs, 124 GiB RAM (78 GiB available at inspection),
484 GiB free on /data, and existing llama containers. The host had no Go binary.

Installed an isolated Python 3.12 container environment and copied Go 1.25.0 plus
the existing public module cache under /data/factory-ng. No host package install,
model-server restart, provider credentials, source changes or game deployment.
The pinned image ID is in policy. Four remote slots share sixteen CPU threads,
four distinct physical cores per slot, nice 10, 16 GiB memory per job, four-way
Go concurrency and no container network.

Added remote verification beside the existing local verifier/integrator.
Batches preserve pinned sources, scope, all selectors and original proposal identity.
The canonical server validates returned evidence and remains the only integrator.
Unavailable remote jobs retain proposals for local batching with a five-minute
host backoff; semantic failures use the original individual repair mechanism.
The manual switch is mirrored during execution. All jobs use distinct directories
and process-held slot locks; job data is removed after import. Cache cleanup is
bounded and requires the exclusive global cache lock with no running containers.

Validation: the 121-test controller/verification/cache/dashboard suite passed,
followed by six focused remote tests after tightening import-directory creation
and adding manual-policy propagation coverage. A real SSH/container/Go trial
passed and returned an imported immutable receipt. A second real trial with a
deliberately wrong patch failed the required Go test and retained the proposal.
Both trials used disposable fixtures; neither could alter live ticket state.

Trials found and corrected unavailable rootless cpuset delegation, login-shell
Go PATH reset and first-run receipt-directory creation. CPU affinity is set by
the managed Python launcher; memory/pid cgroup limits remain. An initial regression
run hit a pre-existing live-source timing dependency during integration; the
complete repeated suite passed. See the saved test and trial logs.

Remote policy was enabled at 15:06:24 UTC under dispatcher-admin; the controller
was asked to reload gracefully. Existing jobs were not killed. Live activation
evidence is recorded separately after the first queue admission.

The user then asked whether multiple jobs would use the 32-thread / 128-GB machine
better. Enabled two remote slots at 15:14:13 UTC, each with four disjoint physical
cores and a 16 GiB limit, retaining headroom for the existing model servers.
The live backlog had become entirely isolated fallback proposals, so remote slots
also check these individually; a failed check returns to local repair and cannot
be selected remotely again unchanged. Shared cache and mirror access are locked
across slots. Controller tests verify disjoint claims and isolated failure handling.

123 checks passed across the suite and a rerun of one live-source timing-dependent
test (the capability producer observed canonical integration in progress during
the first run). A real remote Engine ticket was accepted and queued for integration:
see `first-live-receipt.json`. Its required checks recorded approximately 37 seconds;
this is one ticket's gate duration, not an end-to-end or cross-machine benchmark.


Four-slot policy was enabled under dispatcher-admin at 15:19:39 UTC and hot-read
by the running controller. Slots use CPUs 0–3, 4–7, 8–11 and 12–15 respectively;
these are distinct physical cores, with SMT siblings 16–31 outside the worker
masks. Memory caps total 64 GiB; the existing model containers remain running.
All four slot identities have executed real tickets and returned results.

Resource samples read container cgroup CPU usage and memory.current every two
seconds for about 31 seconds. With two slots, two simultaneous containers reached
7.72 CPU equivalents and 9.42 GiB combined memory. With four slots configured,
three containers overlapped in the measured intervals, reaching 10.19 CPU
equivalents and 15.84 GiB. Job turnover meant the sample did not capture four
simultaneously running containers. All four CPU allocations appeared during the
sample. These different live workloads are capacity observations, not a controlled
throughput comparison. Raw samples, sampler and resource-summary.json are saved
here. Four slots remain the configured operating limit; eight or 32 jobs have
not been justified. The host has 16 physical cores, not 32 independent cores.

At 15:23:58 UTC, 11 remote-accepted tickets awaited integration and two were in
one canonical integration wave. Acceptance counts do not directly measure queue drain because drafting, local
verification, failures and integration continue.
The snapshot four-slot-live.json records actual states; no queue-drain ETA or
remote-completion count is inferred from it. Canonical integration may become
the next throughput limit.

Live testing also found a missing measurement member-set file in a transported
Map packet. Export now copies the selected ticket's referenced docs/factory-ng
files, hashes every transported input and rechecks these hashes before publishing
receipts. Downpour's failed proposal was retained for local repair. Eight focused
remote tests passed after the fix, including missing measurement export and
changed-input rejection. Existing integration failures remain a separate health
issue; the dashboard returned HTTP 200 and the controller was moving at handoff.
The canonical integration lock was held by an active integration at the final
health check, so no canonical source mutation or cleanup was attempted.
