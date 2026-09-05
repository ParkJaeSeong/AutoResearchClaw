# Stage 13 integrated correction report

Base: `b9ed6fc`. Worktree: `.worktrees/stage13-plugin-orchestration`.

## Design and root causes

GC previously trusted whichever refinement-manifest JSON happened to remain in the directory. It never compared those manifests with ProjectState.artifacts, so deleting an object entry or the entire manifest silently removed a GC root. GC now reads bounded, no-follow project-state JSON, includes its byte hash and filesystem identity in the confirmation token, verifies all registered baseline/refinement manifests by path/size/hash, and fails closed if an anchored manifest is absent. State-anchored intent-authority and registration-intent records are verified before their nested source references protect in-flight objects. Standalone EvidenceStore use remains supported without state, but refinement metadata without state fails closed. Existing nested traversal, identity checks, entry bounds, and quarantine behavior remain.

Both intent-orphan branches previously derived expected IDs, timestamps, and hashes from the orphan being validated. The shared correction creates a deterministic private staging path and authority path from the final intent path's SHA-256. It writes and fsyncs the complete intended intent to a staged single-link inode, writes/fsyncs an authority record containing that exact payload (including the staged inode identity and all timestamps/bindings), and registers the complete authority file through existing ProjectState.artifacts. Only then does native no-replace rename publish the authenticated staged inode at the final intent path. No state reference ever points to an empty or nonexistent target. The original final intent-state publication remains a separately recoverable seam.

Recovery verifies the state-anchored authority, exact canonical payload/hash, and physical inode. It either validates an already published target or renames the still-authenticated staged inode. Changing even valid-looking IDs/timestamps, authority content, staged inode identity, link count, or target content fails closed. Before authority-state commit, only exact reserved private paths may be cleaned after no-follow regular-file/single-link validation, and a new attempt gets new IDs/current time; a published target without state authority is never adopted. No ProjectState schema change or Stage 12 pending-state migration was needed.

Result acceptance no longer treats inventory presence as authorization. A fresh/untrusted registration checks controller time against the approved per-run and session deadlines, samples its registration time after expensive context validation, and checks time again immediately before committing write-ahead authority. Candidate-reported elapsed time grants no authority. Exact already-committed intent/authority recovery may finish after expiry and preserves the original wall-time accounting/run count.

Finalized Stage 13 now reports `result_analysis`, `await_stage_fourteen_support`, `read_only`, and `milestone_complete=false`. The next argv is executable `researchclaw-codex status ROOT --json`. Both handoff and status explain that Stage 13 evidence is retained and Stage 14 analysis awaits future support. Durable Stage 14 state still stores its existing `prepare_stage` action for future compatibility. No Stage 14 analysis was implemented. The public refinement reference has one corresponding boundary clarification.

## RED evidence

All commands below ran from this worktree, using the existing installed Python/pytest/ruff. No install, external LLM/API/key/provider, merge, or push was used.

1. `pytest -q tests/codex_native/test_refinement_execution.py -k 'gc_rejects_changed_state or gc_confirmation_rejects_changed or intent_orphan_cannot'`
   - **6 failed, 113 deselected in 34.31s**, each `DID NOT RAISE ValueError`.
   - Cases: canonical `objects=[]`, manifest deletion, manifest-root move, changed project state after GC planning, recanonicalized self-test orphan ID/timestamps, and recanonicalized result orphan ID/timestamps retried after the approved deadline.
2. `pytest -q tests/codex_native/test_refinement_execution.py -k finalize_select_candidate_retains`
   - **1 failed, 118 deselected in 20.09s**.
   - Exact returned argv invoked `stage prepare`; public CLI returned 2 with `task packets are not defined for stage: 14`.

## Verification

- `pytest -q tests/codex_native/test_refinement_execution.py -k 'gc_rejects_changed_state or gc_confirmation_rejects_changed or intent_orphan_cannot or finalize_select_candidate_retains'`: **7 passed, 112 deselected in 52.46s** after the initial integrated fix.
- `pytest -q tests/codex_native/test_refinement_execution.py -k 'write_ahead_intent_crash or result_registration_expiry_requires or adopts_only_exact_intent_orphan or recovers_intent_write_before_state_publication or recovers_exact_partial_publication'`: initial seam/regression run **12 passed, 4 failed in 101.08s**. Two failures were old assertions expecting no authority artifact; those now verify the single extra complete authority artifact and otherwise identical state. Two failures exposed the existing pending-result handoff limitation described below; recovery itself works, and the test now requires unchanged state when that handoff rejects.
- `pytest -q tests/codex_native/test_refinement_execution.py -k 'write_ahead_authority_rejects or gc_requires_state or write_ahead_intent_crash or result_registration_expiry_requires or adopts_only_exact_intent_orphan'`: **17 passed, 117 deselected in 80.15s**.
- `pytest -q tests/codex_native/test_evidence_store.py tests/codex_native/test_handoff.py tests/codex_native/test_resume.py`: **92 passed in 15.40s**.
- `pytest -q tests/codex_native/test_stage13_multi_agent_e2e.py`: **2 passed in 22.02s**. The synthetic candidate's contract still permits one second, subprocesses have a bounded timeout, network/provider guard probes remain blocked, and the exact returned Stage 14 status argv executes in a real subprocess. The independent negative provider probe now occurs after authenticated result registration, preserving its no-result-write assertion without consuming the approved one-second candidate budget.
- `pytest -q tests/codex_native/test_refinement_execution.py -k 'existing_registered_intents_work or fresh_result_checks_deadline or late_authoritative_boundary or wall_time_uses_trusted or report_cannot_replay_across_intents or intent_orphan_cannot_authenticate'`: **9 passed, 1 failed, 128 deselected in 61.48s**. All new/legacy deadline checks passed. The older cross-intent replay test manually reset preparation/intent state to create a new identity but left the new write-ahead authority behind; its fixture now explicitly revokes that authority too, preserving the original cross-intent rejection assertion.
- `pytest -q tests/codex_native/test_refinement_execution.py -k 'report_cannot_replay_across_intents or gc_rejects_changed_state or gc_requires_state' tests/codex_native/test_public_docs.py`: **5 passed, 167 deselected in 27.19s**. The selector intentionally exercised the final cross-intent and GC fixes; it selected no public-doc tests.
- `pytest -q tests/codex_native/test_public_docs.py`: **34 passed in 0.05s**.
- `ruff check researchclaw/core/refinement_execution.py researchclaw/core/evidence_store.py researchclaw/core/handoff.py researchclaw/core/project.py tests/codex_native/test_refinement_execution.py tests/codex_native/test_stage13_multi_agent_e2e.py`: exit 0.
- `python3 -m compileall -q researchclaw/core tests/codex_native/test_refinement_execution.py tests/codex_native/test_stage13_multi_agent_e2e.py`: exit 0.
- `git diff --check`: exit 0.

## Installed-release follow-up: noncanonical project roots

Starting from `bf05e730cb4ffcdc4184483e2899526d760f3f53`, the controller reproduced an installed CLI failure with a `/tmp/...` project root on macOS. `_publish_authorized_intent` constructed an `EvidenceStore` whose root was canonicalized to `/private/tmp/...`, then passed the original lexical project root to that store's `_open_directory`. Its deliberate lexical containment check consequently rejected the otherwise valid metadata directory. Relative project roots had the same mismatch.

The minimal repair retains the store instance and opens `.researchclaw` under that instance's canonical `project_root`. The helper's remaining operations use APIs that already handle the supplied project root; there was no second mismatched store-directory call in this helper. CLI arguments and `ResearchProject.root` remain untouched. The evidence-store containment check, no-follow directory traversal, held descriptors, exact byte/inode authority, and no-replace target publication are unchanged.

Added four public CLI regressions, using existing real candidate/self-test fixtures: symlink-parent and relative project roots for both `refinement prepare-self-test` and `refinement register-result`. They assert success, correct durable artifact references, identical physical artifact targets through both roots, unchanged Stage 12 evidence, and one-run accounting for result registration. The symlink-parent case reproduces macOS `/tmp` alias behavior without depending on a platform-specific alias. The tests explicitly preserve the root spelling accepted by `ResearchProject.open_readonly`.

- RED before the production edit: `pytest -q tests/codex_native/test_refinement_execution.py -k refinement_intent_cli_accepts_noncanonical_project_roots`: **4 failed, 149 deselected in 19.16s**. All four commands returned 2 with `refinement_project_invalid` instead of succeeding.
- GREEN after the minimal edit: `pytest -q tests/codex_native/test_refinement_execution.py -k 'refinement_intent_cli_accepts_noncanonical_project_roots or write_ahead_authority_rejects_replacement_or_linked_publication or anchored_record_rejects_unsafe_components_before_filesystem_access'`: **11 passed, 142 deselected in 30.06s**. Includes authority edits, replaced staged inode, extra hard link, no-clobber target collision, and unsafe path-component rejection.
- `ruff check researchclaw/core/refinement_execution.py tests/codex_native/test_refinement_execution.py`: exit 0.
- `python3 -m compileall -q researchclaw/core/refinement_execution.py tests/codex_native/test_refinement_execution.py`: exit 0.
- `git diff --check`: exit 0.

No full-module repeat, main-worktree edit, plugin metadata change, merge, push, or install was performed by the implementer for this follow-up. Existing documented compatibility limitations are unchanged; the controller independently handles installed smoke verification and integration.

## Controller completion verification

Implementation commits: `5d41d7d` and `6c91d35`. Independent initial review approved the four corrected requirements; the controller's complete module then found the two ordering failures documented in the follow-up section. Following their correction, independent scoped review approved `5d41d7d..6c91d35` with no Critical or Important findings. It checked precommit placement, complete held-evidence equivalence, closed inventories, original deadline enforcement, and authenticated replay.

The controller independently ran `pytest -q tests/codex_native/test_refinement_execution.py -k self_test_session_component_race_cannot_escape_or_publish_state` on `6c91d35`: **4 passed, 145 deselected in 13.99s**. `git diff --check b9ed6fc HEAD` passed and the implementation worktree was clean. Combined with the implementer's final 36-case boundary/recovery batch and 2 real E2E tests, this closes the four original findings and the ordering regression found by the complete module. The entire 149-case module was not rerun after the follow-up; the complete earlier run and scoped subsequent runs are distinguished in this report.

Correction is complete and reviewed. Merge, GitHub push, installed-tool update, and the post-merge `uv tool` gate remain separate integration steps and were not performed. The documented incomplete-result public handoff limitation remains; exact direct registration retry is supported and verified.

Additional fixture-only mistakes during test construction were corrected: a low-level authority test initially used nonexistent profile `default` instead of `materials_ai`; the first isolated formatter invocation could not parse an indented method until its input was dedented. These were not production regressions or substantive RED evidence.

## Crash seams and compatibility

- Before authority exists: completed staged file can be discarded safely; retry starts a new identity and current-time acceptance.
- Authority file written/fsynced but state not committed: authority remains untrusted; retry with no published target starts fresh. Expired fresh acceptance is rejected even if old staged timestamps looked timely.
- State authority committed but final target absent: exact staged inode is authenticated and published on retry. Result acceptance can resume after expiry without another run or altered accounting.
- Target renamed/fsynced but final target-state reference absent: exact target bytes/inode recover; recanonicalized ID/timestamp changes reject.
- Existing final intent-state, manifest, and result-state crash seams retain their previous recovery behavior; focused existing recovery regressions pass.
- Committed authority rejects canonical authority edits, a replaced staged inode with rewritten physical-identity fields, extra hard links, and target collisions without overwriting the colliding target.
- Existing properly registered intent records continue without new authority records; unanchored legacy target orphans fail closed. Recovery does not invent authority for them.
- No new scientific-merit evaluation, automatic candidate selection, external provider, or runtime-budget policy was added. One second remains the synthetic E2E contract budget only.
- The native no-replace rename primitive already supports the project's Darwin/Linux environments. Platforms lacking that primitive fail closed; this is the existing evidence-store portability boundary.

## Known limitation retained with controller approval

While a candidate result exists but its registration is incomplete, the existing public handoff may reject `refinement_candidate_manifest_open` because the result is not yet in the closed candidate inventory. This predates the correction, does not mutate or rewind project state, and is explicitly tested at the committed authority/target seams. Recover directly with:

`researchclaw-codex refinement register-result ROOT --candidate-id candidate-001 --result refinement/candidates/candidate-001/results.json --confirm-refinement-result --json`

Use the actual `result_path` returned by that candidate's prepare-run command in place of the example path. Self-test recovery uses `researchclaw-codex refinement prepare-self-test ROOT --candidate-id candidate-001 --json`. Completed Stage 13 public handoff/resume and their exact next argv succeed.

The local trust boundary remains the trusted project state and its registered immutable references. Coordinated rewrites of trusted state and every referenced artifact are outside the existing tamper-detection model.

The controller will independently review the committed diff and run the complete refinement-execution regression module once; the implementer does not duplicate that long run.

## Follow-up: validate held inputs before committing authority

The controller's complete module run at `5d41d7d` reported **136 passed, 2 failed in 779.00s**. Both failures were the `prepare` variants of `test_self_test_session_component_race_cannot_escape_or_publish_state`. The write-ahead change correctly detected a changed-and-restored session and prevented path escape, but detection happened after registering the authority artifact. This was a real ordering regression; the original unchanged-state assertions remain intact.

The first authority commit now has a shared preaccept gate for both self-test preparation and result registration. It revalidates the closed candidate inventory, held context/file identities, current environment/launcher, baseline registration and direct baseline result, and the held state-file identity before publication. Only `.researchclaw` directory ctime changes from our own staging entries are allowed; no file-identity changes are exempted. Result registration additionally rechecks its held reservation, contract, result, registered self-test evidence, approved input snapshots, and run inventory, then checks the trusted deadline after this validation. Existing postpublication gates and authenticated recovery behavior remain.

The gate reuses already-validated package/candidate/self-test semantics only after proving their complete underlying evidence is unchanged: candidate manifest and every candidate file (including package contract/manifest/config/code), session, council decision, evidence packet, baseline manifest, immutable baseline objects and direct result, state file, reservation and run contract, all four registered self-test intent/preparation/report/receipt files, approved inputs, and submitted result. Self-test/input snapshots are also compared with the physical identities committed in the reserved run contract. The closed tree allows only the previously declared candidate paths, already registered report/result paths, and that exact pending result path. It does not accept new files or a changed identity merely because bytes were restored.

Focused RED evidence at `5d41d7d`:

- `pytest -q tests/codex_native/test_refinement_execution.py -k self_test_session_component_race_cannot_escape_or_publish_state`: **2 failed, 2 passed, 134 deselected in 13.39s**. Both prepare variants violated the unchanged-state assertion by adding an authority artifact.
- `pytest -q tests/codex_native/test_refinement_execution.py -k intent_authority_commit_revalidates_inputs_before_publishing_state`: **8 failed, 138 deselected in 38.87s**. The new tests inject session/baseline/state ABA or a late candidate file immediately after writing the authority file but before its first state commit, for both entry points. Session/baseline/late-file changes were rejected only after state publication; restored state-file bytes could pass completely.

Follow-up GREEN:

- `pytest -q tests/codex_native/test_refinement_execution.py -k 'self_test_session_component_race_cannot_escape_or_publish_state or intent_authority_commit_revalidates_inputs_before_publishing_state'`: **12 passed, 134 deselected in 54.93s**.
- The first `pytest -q tests/codex_native/test_stage13_multi_agent_e2e.py` run with repeated full semantic validation at the new gate produced **1 passed, 1 failed in 7.89s**, with `refinement_run_wall_time_exhausted`. The duplicate full validation traversals consumed the unchanged one-second contract budget. Replacing only the duplicate semantic work with the complete evidence/identity rechecks described above restored **2 passed in 20.63s**. No deadline, candidate budget, reported timestamp, or subprocess timeout was increased or faked.
- Final verification below used the follow-up implementation. No complete-module repeat was performed.
- `pytest -q tests/codex_native/test_refinement_execution.py -k 'self_test_session_component_race_cannot_escape_or_publish_state or intent_authority_commit_revalidates_inputs_before_publishing_state or result_authority_commit_rejects_restored_run_input_identity or write_ahead_intent_crash_recovery or result_registration_expiry_requires_preexisting_authority or fresh_result_checks_deadline_immediately_before_authority_commit or final_gate_rejects_late_tree_change or recovers_exact_partial_publication or intent_orphan_cannot_authenticate or existing_registered_intents_work_without_write_ahead_records'`: **36 passed, 113 deselected in 207.30s**. This includes all original four session-race parameters, eight new precommit mutations, three restored run-input identities, every write-ahead crash seam, existing partial-publication recovery, deadline/legacy/canonical-orphan checks, and late candidate-tree cases.
- `pytest -q tests/codex_native/test_stage13_multi_agent_e2e.py`: **2 passed in 20.59s** on the final code, including the unchanged one-second contract and exact executable Stage 14 status argv.
- `ruff check researchclaw/core/refinement_execution.py tests/codex_native/test_refinement_execution.py`: exit 0.
- `python3 -m compileall -q researchclaw/core/refinement_execution.py tests/codex_native/test_refinement_execution.py tests/codex_native/test_stage13_multi_agent_e2e.py`: exit 0.
- `git diff --check`: exit 0.

## Main merge and installed release verification — 2026-09-05

- Fast-forward merged the reviewed corrections through `6d2a617` into local main. Independent review approved the final noncanonical-root fix without blockers; containment and no-follow protections remain unchanged.
- After the initial merge at `bf05e73`, the Stage 13 multi-agent E2E, public documentation, and plugin packaging modules passed: **42 passed in 20.89s**. The subsequent root fix passed **11 scoped regressions** as recorded above; no broad suite was duplicated.
- Reinstalled `researchclaw-codex` from main with `uv tool install --reinstall --refresh`, retaining the managed Python 3.13 runtime. Verified imports from installed site-packages outside the repository and byte equality of five production modules with main.
- Refreshed the personal plugin to `0.1.0+codex.20260905125102` with the plugin-creator cachebuster helper and `codex plugin add autoresearchclaw-codex@personal`. Plugin validation passed and cached refinement instructions match main.
- Ran the installed CLI synthetic workflow through **20 commands**, using the uncanonicalized `/tmp` alias path: session preparation, three-role assessments and deliberation, refinement decision, candidate registration, exact returned self-test/run argv, result registration, new assessments, 2–1 candidate selection, finalization, resume, and the exact returned read-only status command. **Passed**.
- Launcher: `/Users/jspark/.local/share/uv/tools/researchclaw-codex/bin/python3`. Preparation, actual self-test report, and run environment fingerprints matched (`ff17c648fc8af06b26b243e0d8ffc1cb46ee092a24d3e7737d3e84d864ede6a7`). Baseline evidence remained unchanged and the network guard observed **0 attempts**.
- Final durable stage is 14; public handoff correctly reports `await_stage_fourteen_support`, `read_only`, and an incomplete milestone. This verifies the boundary, not implementation of Stage 14 analysis or scientific validity of synthetic data.
- Local diagnostic driver and detailed command results: `/tmp/researchclaw-stage13-installed.713y9C/verify_installed.py` and `verification.json` (temporary, not committed). No live research projects were used.
- GitHub push was not performed in this merge/install/verification task. Start a new Codex task to load the refreshed plugin instructions.
