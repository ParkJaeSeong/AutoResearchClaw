# Pilot runtime audit — 2026-09-18

Scope: static inspection of `/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph`, HEAD `c89f086c41a6f384450942bece887f96e9acf77b`, including current working files. No research models, external requests, runtime state changes, or implementation changes were made. This file is the only audit artifact written by this reviewer. Tests below were read, not executed; no passing-test claim is made. Line references are relative to this worktree.

## Main finding

Pilot has substantial durable transport, evidence validation, immutable graph, independent-round disclosure, and selected resume protections. It does **not** yet have one compulsory research execution lifecycle tying task contracts, current inputs, scientific adoption, completion, feedback, return plans, all workers, and cancellation together. Existing lower-level checks must not be represented as an end-to-end enforced research protocol.

## Prioritized omissions and exact evidence

### P0 — Completion representations do not share the formal gate

- `researchclaw/core/research_graph/gates.py:105` implements the formal assessment: bound source/approval refs (`:161`), distinct author/reviewer actors (`:133`), submissions and rationale (`:175`), blocking issues and revision conditions (`:200`). A search of `researchclaw/core` and `researchclaw/codex` for `assess_gate` finds only this definition. It is not called by the dispatcher or episode completion.
- `researchclaw/core/research_graph/work_episodes.py:96` concludes work using only an existing open episode, `finished|failed`, and nonempty judgment/remaining/next-action strings. It does not require a task packet, evidence refs, review results, input freshness, artifact checks, or a gate receipt. `:53` lets callers choose `review_required` and empty dependencies. Dependency review checks (`:68`) only apply to dependencies that a caller actually declares.
- `researchclaw/core/research_graph/work_execution.py:16` accepts `status='completed'` for M1 with a nonempty reason; no gate or completion artifact is required. Its assignment uses arbitrary nonempty `input_revision` (`:23`), not a resolved versioned task contract.
- These are real dispatched commands: `researchclaw/core/research_graph/commands.py:39` and `:45`. CAS/idempotency in `:74` protects storage integrity, not scientific sufficiency.
- Important qualification: this does not show a forged **formal native handoff**. Native handoff validation remains implemented in `researchclaw/core/research_graph/handoffs.py:363` and is surfaced via `researchclaw/core/research_graph/views.py:271`; `assess_native_handoff` delegates to it (`handoffs.py:397`). The defect is that “episode finished”, “execution policy completed”, and formal handoff readiness are disconnected, and consumers can treat the former as completion without the latter.
- Requirement to map: name and distinguish execution-ended, result-reviewed, judgment-adopted, milestone-complete, and handoff-accepted; define one obligatory transition receipt for each claimed meaning and every path that can publish it.

### P0 — Import-review freshness is checked before the long-running model, not before return

- `researchclaw/codex/import_review_worker.py:72` hashes and compares the current question file once at tick start (`:80`). It optionally checks active work, then executes all queued model work (`:92`).
- `publish_review` (`:54`) checks original `work_ref` and current episode/policy active (`:45`), but does not compare the current question bytes, policy revision, assignment, task input revision, or originating graph head. Each note uses a newly read HEAD (`:67`), allowing an old-context result to attach to an episode that is still open after its premises changed. Multiple note commits can interleave; there is no final immutable batch receipt.
- Queue identity includes question/policy revision (`researchclaw/codex/import_review.py:54`), and completion binds to a packet hash (`:85`). Those checks prove the result matches its **old frozen packet**, not that that packet remains applicable now.
- Contrast: `researchclaw/codex/service_review_worker.py:80` re-reads context after the model and preserves late output without acknowledging it if changed; `service_work_binding.py:35` publishes with the original graph HEAD CAS. Thus the stronger freshness rule exists but is not shared by all review paths.
- Requirement to map: current applicability check and quarantine/explicit rebase for every late result, including changed question, persona, policy, user feedback, assignment, closed work, and stop→restart.

### P1 — Revalidation/rollback graph exists as a planner but is not a connected lifecycle hook

- `researchclaw/core/research_graph/dependencies.py:104` computes affected/reusable refs, verifies dependency DAG cycles (`:145`), and checks approvals (`:167`). It returns an `event_plan` (`:187`), rather than committing it or pausing/rescheduling affected workers.
- A search of runtime `researchclaw/core` and `researchclaw/codex` for `plan_revalidation` finds only the definition. `commands.py:30` exposes no revalidation operation or automatic mutation hook.
- Episode `return_to` only checks that a prior episode exists (`work_episodes.py:77`). This does not invalidate dependent adopted conclusions, schedule targeted re-review, or preserve a machine-checked completion criterion for the return.
- Evidence-driven return requirements exist (`return_policy.py:38`; callers in `budgets.py:185` and `:190`), while old snapshots default to `count_limited` (`return_policy.py:17`). The episode/service execution routes do not call this policy. A documented evidence-driven return policy therefore is not a global guarantee.
- Requirement to map: feedback/change reception → exact affected references → quarantine only affected adoption/execution → concrete return task → revalidation → revised judgment; retain immutable earlier conclusions and unaffected work.

### P1 — Follow-up planning is not an autonomous research loop

- Episode reviews atomically create hashed follow-up plans (`work_episodes.py:119`, `work_followups.py:17`), explicitly without starting them (`work_followups.py:1`).
- Service follow-up planning accepts `ask_atlas`, `collect_sources`, `review`, and `revise_design` (`work_execution.py:36`), but execution supports **only** `ask_atlas` (`:64`). It starts a new episode with empty dependencies and `review_required=False` (`:70`).
- `researchclaw/codex/service_followup_runner.py:6` handles one designated follow-up. Once an answer is captured, it returns `result_stored` (`:35`); it does not queue the next reviewer, adopt any judgment, conclude the episode, update the service follow-up to terminal state, or schedule the next research task. The stored service row remains `started` (`work_execution.py:72`).
- `AtlasSession.queue_answer` is separate (`atlas_session.py:164`) and needs an explicitly chosen recipient. `service_review_worker.py:22` runs a single role/round, not a council or milestone. `import_review_worker.py:109` watches import observations, stops on any errors (`:114`), and is not a research coordinator.
- Requirement to map: actionable follow-up kinds, eligibility and ordering, dispatch ownership, deduplication, successor selection, terminal states, duplicate-discussion detection, evidence-driven return, budget/authority boundaries, and continuation of unaffected work.

### P1 — Stop, retry, and resume contracts differ by entry point

- Positive: graph mutations have transaction/CAS and fingerprinted command replay (`commands.py:84`); inbox deliveries are durable and deduplicated (`service_inbox.py:44`), recipient-bound on acknowledgment (`:69`). Service review serializes delivery with a lock and preserves intent/raw/result (`service_review_worker.py:33`), refuses to blindly re-execute an interrupted attempt (`:64`), and reuses saved results (`:38`).
- Positive: Atlas persists outbound intent before submission (`atlas_session.py:109`), reuses request keys (`:90`), validates instance/request receipt and immutable identity (`:117`), and atomically saves hashed response bytes (`:189`). Document adapter saves owned events before stream cursor (`document_handoff_adapter.py:142`) and acknowledges only after processing (`:165`). Observer still polls independent received work if new submission fails (`document_handoff_runner.py:30`).
- Gaps: stopping `work_execution_policy` blocks the service follow-up runner and WorkBinding, but `AtlasSession.ask/poll` (`atlas_session.py:84`, `:117`) has no such check; UI dispatch calls it directly (`atlas_service_http.py:28`). `atlas_council.run_council` (`atlas_council.py:26`) likewise does not check this execution policy. Thus policy stop is not universal remote cancellation or even universal dispatch inhibition.
- `host_reviewer` reuses a successful exited attempt but otherwise returns `reviewer_attempt_requires_inspection` (`atlas_reviewer.py:45`). `wait_for_host` records heartbeat/PID but waits indefinitely (`literature_loop.py:100`); no cancellation/termination/finally cleanup is defined there. A stopped work can leave already launched model work running. This preserves artifacts but does not supply reconnect-to-process, structured retry authorization, orphan-process reconciliation, or cancellation confirmation.
- Service review's saved-result fast path (`service_review_worker.py:38`) republishes with the original context. With production WorkBinding, CAS rejects a changed head; unrelated graph changes can strand an otherwise reusable result until explicitly reconciled. This is fail-closed, not transparent resume. No rebase/rebind recovery command is provided in these worker modules.
- Requirement to map: separate pause-dispatch, stop-project, cancel-remote, cancel-model, preserve-result, retry-failed-attempt, reuse-completed-result, and resume-same-attempt semantics and receipts.

### P1 — Scientific adoption and task contract checking remain partly coordinator obligations

- `host_reviewer` instructs scope, persona, provenance, earlier context, question/impact/completion conditions, and non-adoption (`atlas_reviewer.py:53`). Its validated output only has `rationale` and `recommendation` (`:20`, `:32`). It does not mechanically require structured evidence locations, unresolved issue ownership, artifact checks, counterarguments, or successor completion criteria.
- Service follow-up registration only requires a JSON output note with matching delivery ID and any dict-shaped `review` (`work_execution.py:43`). It does not verify that the note was authored by the actual worker, that the result has a valid scientific contract, or that a review is applicable to current inputs.
- `service_review_worker.py:70` checks dict-shaped materials/packet and prevents obvious `disclosed_*` initial inputs. Caller-provided text/material fields may still contain prior peer content; strong isolation cannot be claimed.
- Import council explicitly ends with `research_adoption=False` (`import_council.py:39`); import queue completion enforces this (`import_review.py:91`). Import worker publishes dialogue and coordinator text only (`import_review_worker.py:60`). No automatic adoption/issue-materialization hook is demonstrated by these paths.
- Requirement to map: which work types require structured task packets and acceptance evidence; how source review, hypothesis judgment, design review, issue adoption, and task completion connect without inventing review or authority.

### P2 — Persona/model selection and research-purpose routing remain incomplete

- Three specialist roles plus coordinator and polymer/CNT defaults are hardcoded (`atlas_reviewer.py:7`, `:13`, `:56`). Import context may override persona/milestone purpose (`import_council.py:16`) but none is required or validated as a versioned role contract. Service assignments restrict role and round values (`work_execution.py:30`).
- Model launch has no explicit model argument (`atlas_reviewer.py:82`); evidence truthfully reports `codex-cli-default-unverified` (`:38`). Model diversity/selected runtime configuration therefore is not verified. Role separation is explicitly `instructions_only` in council packets (`councils.py:213`) and reviewer prompt (`atlas_reviewer.py:71`).
- Generic handoff gate mapping supports M1→M2 and M2→M3 (`gates.py:127`); native handoff gate requires M1→M2 (`handoffs.py:400`). The newer M1→M4 report/business-plan route is not represented here as an executable formal gate.
- Requirement to map: purpose-specific persona, review criteria and outputs for M1-1/M1-2/M1-3 and M2/M3/M4; explicit actual model provenance; no unsupported claims about independent models or strong isolation.

### P2 — User-visible progress and feedback are narrower than the required interaction

- Native councils enforce an all-participant disclosure barrier (`councils.py:178`) and snapshot all packets before publishing a phase (`atlas_council.py:93`). Import council has the same phase barrier (`import_council.py:26`). This is implemented, not merely aspirational.
- Atlas council publishes episode dialogue only after all phase submissions (`atlas_council.py:115`, `atlas_episode.py:34`); import review publishes dialogue only after the **entire** council and coordinator return (`import_review_worker.py:33`, `:63`). Keeping initial statements private is correct, but users do not get a corresponding per-role progress event from this path.
- Heartbeats go to `activity.json` (`literature_loop.py:104`); runtime search finds the discovery viewer reading these (`discovery_view.py:133`), but no import-review activity reader in the inspected viewer path. Generic live feed renders only when graph HEAD changes (`research_ui/live.js:13`). A connected UI thus is not evidence of active research or fresh per-role progress.
- User feedback endpoint supports one post-conclusion `continue|revise` review (`episode_http.py:9`, `work_episodes.py:108`). Review is immutable after one submission (`work_episodes.py:115`). There is no general evolving feedback thread, repeated feedback-version binding, affected-input assessment, accepted/rejected rationale, and revised-conclusion chain in this API.
- `CouncilEpisode.start` forces review-required (`atlas_episode.py:24`), and `finish` says development review determines the next work (`:50`). Successors that declare this dependency wait for a `continue` review (`work_episodes.py:72`). This is a local review gate, not the fully autonomous default described in AGENTS.md.

## Read test coverage and limits

- `tests/codex_native/research_graph/test_gates.py:108` onwards exercises accepted transfers, missing prerequisites, author/reviewer separation, stale approvals, unresolved opposition and malformed data **by calling the assessor**. This does not test that all completion entry points invoke it.
- `tests/codex_native/research_graph/test_work_episodes.py:87` tests declared dependency checks; `:171` explicitly tests that episode conclusion/review does not approve science. This is evidence of intended separation, not completion enforcement.
- `tests/codex_native/test_service_work_binding.py:14`, `:25`, `:38`, `:57` cover real-store publication/replay, closed work, and stopped/changed assignments.
- `tests/codex_native/test_service_review_worker.py:16`, `:36`, `:46`, `:55` cover saved review reuse, late result preservation, failed attempt no automatic replay, initial peer disclosure guard.
- `tests/codex_native/test_service_followup_runner.py:9` uses a fake Atlas service to test lost response/idempotent request recovery; `:22` checks pre-dispatch stop only. It does not cover full capture→review→adoption→successor or actual remote/model cancellation.
- `tests/codex_native/test_import_review_worker.py:27` tests question changes **before** tick. `:62` tests idempotent note publication; `:82` tests stopped work. Missing regression scenarios include question/policy/assignment change during the model, stop→restart with same work ID, publication interrupted halfway, global stop through alternate Atlas entry points, and source-hash changes after frozen packet creation.
- `tests/codex_native/test_import_council.py:12`, `:31` cover independent initial phase/resume and optional persona propagation, not semantic persona adequacy or verified model selection.
- These tests are valuable component tests with temporary stores/mocks; inspected coverage does not establish an end-to-end deployed autonomous research run.

## Examined files

Full or relevant portions read: `AGENTS.md`; `researchclaw/core/research_graph/{commands,gates,work_execution,work_episodes,work_followups,councils,dependencies,return_policy,handoffs}.py`; `researchclaw/codex/{service_inbox,service_work_binding,service_review_worker,service_followup_runner,import_review,import_review_worker,import_council,atlas_session,atlas_reviewer,atlas_council,atlas_episode,atlas_service_http,document_handoff_adapter,document_handoff_runner,episode_http,literature_loop}.py`; `researchclaw/codex/research_ui/live.js`; tests identified above. Targeted symbol/call-site searches additionally covered `views.py`, `budgets.py`, `work_accounting.py`, `research_viewer.py`, `discovery_view.py`, all runtime `.py` files under core/codex, and test names in the corresponding suites. This inventory does not assert a full audit of every module in those directories.
