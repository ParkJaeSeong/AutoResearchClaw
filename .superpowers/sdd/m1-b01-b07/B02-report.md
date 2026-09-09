# B02 implementation report

Base 78a8e73. B02 adds councils.py, focused tests/input contract, and explicit
council.prepare/council.submit dispatcher entries. No old M1 source was modified.

Implemented usable node-neutral prepare → initial → response → final path.
Prepare creates only closed A04 assignments, A06 frozen session and council record.
Authors can be reused byte-exactly; reviewers are fresh and actor-distinct from
authors/each other. Exact shared evidence graphs exclude unpublished peer
submission, position and proposal identities/hashes, including nested and other
session references. Existing issues are frozen at the prepared ancestor and
projected with their exact body/reference; later replacement fails stale.

Required participants disclose initials together; response and final barriers
behave likewise. A01 structured issue proposals survive disclosure for explicit
node-adapter publication, without creating native issue events or resolution.
New/retained positions use A06 and actor/session/prior-version checks. Final
recommendation is explicit even when review has no registered issues.
Reviewer packets and both first/replay council command receipts are whitelist
projections; no raw state/events/object registry/fingerprint payload leaks. Replay
is projected at its original ancestor. Artifact-ID collisions reject before commit.

Focused RED: 18 failing tests with missing module/unknown council operations.
Additional identity-collision and exact shared-issue regressions were RED before
implementation. Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_councils.py -q`
→ 20 passed (1.42s); `git diff --check` clean. Tests include privacy after first
and second initial, all-three disclosure, stable redacted replay, stale/conflict
HEAD preservation, phase refusals, declared host labels, proposal continuity,
A06 position flow, no-I/O pure interfaces and referenced-byte preservation.
No predecessor/broad suite run; root owns integration/independent review.

Actual host observation (root-owned, not a fixture inference):
`.superpowers/sdd/m1-b01-b07/host-access-observation.json` records another real
Codex subagent reading a 58-byte synthetic peer file. Thus current shared workspace
is instructions_only; no filesystem denial or peer nonaccess is certified. Other
hosts/tools/configurations remain untested. Model/host labels are declarations;
exact observation refs are separate evidence, not identity/isolation proof.
No experiments, runtime prerequisite seeds, CLI/UI, arbitrary state writers,
scientific validation, user approval authority or automatic issue resolution added.

## Independent review correction wave

Confirmed the two review findings with public-command RED: 3 failed, 20 passed.
Freshness exemption now applies only to existing byte-identical author assignments,
so a new author cannot overwrite a shared input artifact alias. The common council
and submission envelope validator now enforces host_observed ⇒ nonempty exact
observation_refs. All regressions assert rejected command HEAD preservation.

Final focused GREEN: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_councils.py -q`
→ 23 passed (1.45s). `git diff --check` clean. No broad/predecessor runs.
