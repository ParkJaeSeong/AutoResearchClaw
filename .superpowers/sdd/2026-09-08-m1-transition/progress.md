# SDD ledger — plan: docs/superpowers/plans/2026-09-08-m1-transition.md

Base: ea3b62d; worktree: feature/m1-research-graph.

## Rulings
Ruling: User authorized starting the proposed M1 plan; reversible worktree creation and the provisional policy defaults are included. Existing projects remain untouched. Defaults are not approvals for future research.
Ruling: Use Python 3.12.14 and Node 26.8.1 already installed. Baseline runs against original main checkout with explicit PYTHONPATH while implementation is isolated in the worktree.
Ruling: Local-only package UI preserves the approved vanilla stack; Sites registration/hosting is skipped under its local-only rule. Controller owns UI edits; agents may review only.
Ruling: Store command idempotence lookup must precede stale HEAD rejection for the same committed command; otherwise retried success after HEAD advance fails. Reject different payload under the same command ID.
Ruling: Plan code snippets are illustrative contracts; tests must exercise validation/behavior, not tautological identity getters. Correct defects without literal transcription.
Ruling: Task 03 and intermediate C/D live checks use synthetic input clearly marked; only Task 17/20 may establish an actual full M1 research run, with necessary user literature approval.
Ruling: Plan script files are non-executable in this installation. Invoke bash; task briefs are extracted equivalently into this one plan workspace without modifying installed skills.

## Preflight — per task
| Task | Consistency review |
|---|---|
| 01 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 02 | Pure selector sample is insufficient alone; add graph/decision lineage and browser behavior tests. |
| 03 | Actual three independent submissions mandatory; never equate fixture with host proof. |
| 04 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 05 | Apply idempotence-before-stale ruling; initialization atomicity and immutable publish require tests. |
| 06 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 07 | Seeded fixture is test-only until early gates are implemented. |
| 08 | New synthesis schema intentionally differs from legacy; do not feed incompatible schema to old validator. |
| 09 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 10 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 11 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 12 | Readiness alone is not scientific proof; admission/provenance checks belong registration boundary. |
| 13 | Allow same-node corrections with explicit reason and dependency propagation. |
| 14 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 15 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 16 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 17 | Generic readiness must not require selected hypotheses before review node. |
| 18 | Cached flags never authorize handoff; recompute receipts. |
| 19 | Files, consumed/produced interfaces, and boundary agree; no task-local contradiction found. |
| 20 | Local installation validation only; no implicit publication. |

## Preflight — shared files and interfaces
| Tasks | Shared interface / file | Finding |
|---|---|---|
| 01, 04 | policy defaults | Names and responsibility aligned; review each task diff at handoff. |
| 02, 15 | View JSON | Names and responsibility aligned; review each task diff at handoff. |
| 02, 16 | m1_ui | Names and responsibility aligned; review each task diff at handoff. |
| 03, 10 | Assignment provenance | Names and responsibility aligned; review each task diff at handoff. |
| 04, 06 | node/role catalog | Names and responsibility aligned; review each task diff at handoff. |
| 04, 13 | return targets | Names and responsibility aligned; review each task diff at handoff. |
| 04, 17 | review modes | Names and responsibility aligned; review each task diff at handoff. |
| 05, 06 | commit_record/project | Names and responsibility aligned; review each task diff at handoff. |
| 05, 07 | store and approval | Names and responsibility aligned; review each task diff at handoff. |
| 05, 10 | atomic session registration | Names and responsibility aligned; review each task diff at handoff. |
| 05, 14 | idempotence and revision | Names and responsibility aligned; review each task diff at handoff. |
| 05, 15 | read_head | Names and responsibility aligned; review each task diff at handoff. |
| 06, 07 | artifacts/packets | Names and responsibility aligned; review each task diff at handoff. |
| 06, 08 | artifacts/synthesis | Names and responsibility aligned; review each task diff at handoff. |
| 06, 09 | artifacts/hypotheses | Names and responsibility aligned; review each task diff at handoff. |
| 06, 17 | review_pending admission | Names and responsibility aligned; review each task diff at handoff. |
| 07, 08 | evidence refs/helpers | Names and responsibility aligned; review each task diff at handoff. |
| 07, 13 | approval impact | Names and responsibility aligned; review each task diff at handoff. |
| 07, 18 | current corpus binding | Names and responsibility aligned; review each task diff at handoff. |
| 08, 09 | claim and gap IDs | Names and responsibility aligned; review each task diff at handoff. |
| 08, 15 | trace_claim | Names and responsibility aligned; review each task diff at handoff. |
| 09, 10 | authorship and input binding | Names and responsibility aligned; review each task diff at handoff. |
| 10, 11 | council phases | Names and responsibility aligned; review each task diff at handoff. |
| 11, 12 | FinalPosition and Issue | Names and responsibility aligned; review each task diff at handoff. |
| 11, 17 | early council genericity | Names and responsibility aligned; review each task diff at handoff. |
| 12, 13 | Decision/TransitionPlan | Names and responsibility aligned; review each task diff at handoff. |
| 12, 18 | readiness | Names and responsibility aligned; review each task diff at handoff. |
| 13, 14 | plan_hash and input_head | Names and responsibility aligned; review each task diff at handoff. |
| 14, 15 | attempt revisions | Names and responsibility aligned; review each task diff at handoff. |
| 15, 16 | build_view | Names and responsibility aligned; review each task diff at handoff. |
| 16, 20 | bundled UI assets | Names and responsibility aligned; review each task diff at handoff. |
| 17, 18 | completion receipts | Names and responsibility aligned; review each task diff at handoff. |
| 18, 19 | public end-to-end | Names and responsibility aligned; review each task diff at handoff. |
| 19, 20 | verified package baseline | Names and responsibility aligned; review each task diff at handoff. |

## Progress
Task 01: in progress — isolated environment and baseline.

Task 02: complete — 6e72a37 then f9a60f7; Node 8/8, browser360/736/light/dark/keyboard/empty/missing/long verified; independent review approved after three fixes.
Task 03: implemented — 060f46e; three real native assignments + same-task response rounds; synthetic host-only transcript preserved, no engine registration.
Task 04: in progress — pure graph and role contracts via fresh implementer.
Ruling: D1 return does not mark H1-r2 accepted; selected_hypothesis_ids remains empty. Evidence return shown as possible next option, not fabricated executed history.
Ruling: Local preview final QA uses port51633/no-store after browser retained cached JS imports on original origin. Final deliverable points to verified origin.

Task03 review: Approved, host-observed limitation explicitly retained. Task01 policy review correction: selected-hypothesis requirement only review/handoff, not early nodes; future CLI described as planned.

Task01 review: Approved-partial. Policy and targeted166 baseline reviewed; full original suite still pending, so Task01/A not complete. No full-pass claim permitted until final counts and failure classification are recorded.

Task04 implemented291fb96:29named/123legacy tests passing; descriptive contract only, independent review pending. Task01 full baseline interruption requested after 4h unchanged75% wait to obtain failure summary; await agent result/classification.

Task04 review approved: pure contract spec/quality PASS, no Critical/Important. Task01 baseline interruption returned2failed/3639passed/43skipped/1deselected exit2 at75%SSL wait. Environment-corrected focused rerun2passed; full suite remains incomplete. A checkpoint provides implemented02–04 and accurately partial01; no M1 completion claim.

## Task05 execution start
Task03: complete —060f46e, independent review Approved.
Task04: complete —291fb96, independent review PASS,29new+123legacy roles.
Task01: partial baseline recorded f68d263; full suite interrupted in SSL wait; environment-only failures focused rerun passed. No full regression green claim.
Task05: in progress — BASE f68d2637bae1ef02e95a83f35ce42d8c14412684.
Ruling: Current user said start after the proposed Task05 atomic-storage work unit; execute that concrete unit and its review/acceptance. Tasks06 onward remain separately tracked subsequent units, not implied completed by this unit.
Ruling: Existing persistence directory-open failures are silently ignored; M1 durable publication must not suppress real disk/permission failures. Reuse helpers only where their observed error semantics satisfy M1 requirements.

Ruling: Task05 init accepts optional content_origin (research default, synthetic explicit) and matching CLI flag. This preserves existing required call signature while carrying the master origin distinction into persisted metadata; otherwise synthetic acceptance would be mislabeled later. Cost if wrong is a small compatible API adjustment.
Task05 proposed store contract: closed versioned receipts; extensible state; cumulative versioned events and SHA256->size object index; logical-name binding retained in command identity. Root acceptance will use explicit synthetic origin.

Task05 root acceptance passed: separate-process synthetic init/status, readonly bytes/mtime/mode unchanged, actual object/event append, same command with old expected_head returns original receipt, old commit files preserved. Final-code acceptance pending after remaining durability fix.
Ruling: After a publish succeeds but directory fsync fails, a later identical mutation retry must establish publication durability before acknowledging success. It must not rewind current HEAD when returning an earlier receipt. Keep read_head read-only. Cost: extra fsync on mutation retries; benefit: no success acknowledgement that bypasses previously failed durability step.

Task05 implemented fe23532:65final targetedpass,155legacy pass in earlier215combined run. Finalcode external acceptance PASS including both-direction legacy isolation. Independent review dispatched, pending. No physical-power-cut/full-suite/ruff success claim.

Task05 review round1: Needs fixes. Important fresh commit after init postpublish metadata fsync failure does not sync m1 parent before success; independent focused reproduction confirmed. Implementer resumed for regression and publication durability fix. All other scope inspected approved provisionally. FixBASE fe23532.

Task05 fixround1 complete:0486946 source/test,45afdf9 report;66targetedpass. Final separateprocess acceptance PASS. Scoped rereview Approved(spec+quality), no remaining finding. Task05: complete —fe23532..45afdf9. Current user-authorized work unit done; Task06 next per user-facing plan. FulllegacySSL baseline limit retained for integration gate.

## Task06 execution
Task06: in progress BASE1ba7678fef588360c61af63c3a438b3e106b63d7; user selected this unit after Task05.
Ruling: Draft correction budget means initial submission plus up to2 correction submissions; third content-validation failure waits for user. Replaying one failed command must not consume budget again. Reject unsafe manifests before filesystem reads. This clarifies master additional-correction semantics; cost if wrong is adjusting counts before later budget integration.
Ruling: New node packets reference project-relative m1/work/<attempt>/ drafts; metadata immutable objects remain .researchclaw/m1. Persisted packet is authoritative; caller cannot change its allowlist/inputbinding. Declared hashes may bind submission to support retry after consumed draft files disappear. Implementation will document exact public schema.

Task06 schema agreement: submission {schema_version:1,files:{logical_path:{path,sha256,size}}}; prepare returns receipt/packet/attempt; register returns receipt/packet_id/attempt_id/status/issues/artifacts; resume returns version/head/current node/status/action/wait reasons/inputs/current attempt. Unsafe/malformed preflight consumes no correction budget; safe snapshotted content-format failures consume budget. Failed registration CLI remains stderr/exit2 even if a failure history event is persisted.
Task06 root acceptance driver prepared: separateprocess synthetic scope prepare/register/replay with drafts removed, readonly resume, no skipping review into questions. Execution pending implementation.

Task06 root initial acceptance PASS on available implementation: real separate CLI processes,prepare replay, valid registration->review_pending, replay after draft removal, readonly resume, questions preparation denied while scope review pending. Re-run after final reviewed source if modified. Initial resume output scope/review_pending/await_review correctly explains independent review still needed.

Task06: complete - implementation 3fcb610. Final targeted run: 163 passed, including 32 new Task06 tests, 2.72s. Root separate-process CLI acceptance rerun on final commit passed: prepare replay, registration replay after draft removal, read-only resume, review gate retained. Independent reviewer: spec Pass, quality Approved; no required changes. Review inspected diff and targeted integration dependencies; did not rerun broad tests. Task07 remains next, not started. Full legacy baseline remains incomplete.

## Task07 execution
Task 07: in progress - BASE 386cdd77b0575397331547eed367f15a3c4f37a2. User accepted proposed Task07 unit. Existing isolated worktree clean; prior 163-test baseline retained.
Ruling: Task07 includes necessary packet preparation/registration and readonly resume approval integration even though file list only names artifacts/CLI; without these the documented approval gate cannot operate. Preserve review gates and defer general node advancement to Task17. Cost: additional scoped integration changes and tests.

Ruling: Task07 corpus binding includes current scope/questions plus search/collection/screen artifacts sorted by ID/hash, project and workflow version. New context or artifact revision requires new approval; unrelated HEAD churn does not. This conservatively binds informed selection; cost is occasional extra approval for identical bytes registered as new artifacts. CLI actor user is declared authority, not independent identity authentication; synthetic fixtures remain declared_only.
Task07 schema: record_corpus_approval returns receipt/approval; current_corpus(root) readonly returns corpus_binding/corpus_refs; resume includes corpus summary. Approval records never replace screen council or advance nodes. Latest same-binding rejection revokes approval; historical replay cannot undo later decision.

Task07 implementer RED:31new tests failed expected missing implementation. Root acceptance driver prepared with separate CLI calls from explicit synthetic checkpoint: screen approval retains review gate; reject blocks preparation; old approve command replay preserves later reject; revoked approval blocks prepared extraction registration; new approval enables registration; changed context rejects old binding; readonly resume. Driver AST parsed; execution pending implementation.

Task07 root initial CLI acceptance PASS on in-progress source. Implementer reports336M1+knowledge/approval/task_packets passed22.64s before self-review read-integrity regression. New RED validates object bytes at content-read against digest; final test count/acceptance pending fix.

Task07 implemented dfeb152:343passed23.30s including39newTask07; relevant legacy adapters/approval/task_packets unchanged and regression-tested. Root CLI acceptance rerun on final commit PASS, including rejection-after-preparation and stale corpus binding. Independent task review dispatched to m1_task07_review; pending verdict. No whole-graph/full-legacy success claim.

Task07 review: spec compliant, quality Approved, no Critical/Important/Minor. Cannot-verify store atomicity/replay dependency resolved by unchanged Task05 engine and prior approved review (0486946 fix), current343-pass suite includes store/approval interruption tests, and final root CLI replay acceptance. No store source change in Task07.
Task 07: complete (commits386cdd7..dfeb152, review clean). Final root CLI acceptance PASS on dfeb152. Task08 next; not started. Full legacy baseline remains incomplete.

## Task08 through Task16 execution
User explicitly requests proceeding through UI connection. Authorized scope now Tasks08-16 including real host council validation and local read-only viewer, no pause between units. Tasks17-20 remain later integration. BASE43bd23d0032f35db1035e655121c2cf086116a0f. Existing worktree clean.
Task 08: in progress. Existing plan preflight table applies; per-task reviews retained.

Task08-16 execution checklist: 08 synthesis/lineage;09 hypothesis versions;10 independent initials;11 responses/finals;12 decisions;13 return impact;14 apply/budgets;15 readonly view;16 local viewer/UI. Each implementation reviewed before dependent work. Controller owns live host acceptance and UI source per existing Sites ownership ruling. Local-only authorized plan includes browser QA; no external hosting or Site registration.

Ruling: Task08 adds readonly read_trace_head hydration adapter and m1 trace --claim [--synthesis] CLI, keeping store.read_head schema unchanged. trace_claim consumes exact digest-bound registered bytes, pinned synthesis/extraction provenance and historical approval at extraction commit; missing bytes fail explicitly. Cost: small extra adapter/CLI surface, required to make stated trace_claim(head) contract useful without mutable filesystem paths.
Ruling: Synthesis claims are registered claim ID strings; agreements have id/claim_refs/summary; conflicts have id/claim_refs/interpretations/open_questions; gaps with empty refs require status unverified_question and nonblank reason. No verified gaps is a reported limitation, not invented evidence or blanket structural rejection.

Task08 implemented d13684c:292passed final8.76s,26new. Root final CLI acceptancePASS. Independent review pending. Task09 context prepared, not dispatched until review gate.

Task 08: complete (43bd23d..d13684c, review clean spec+quality). Task 09: in progress BASEd13684c; implementer m1_task09. User authorization through16 remains active.

Task09 BASE updated bf65d7c (Task08 docs). Ruling: cumulative hypothesis envelope preserves earlier records, author_assignment_id and explicit change_reason for revision>1; exact synthesis producer extraction refs bind authoring. No-candidate envelope requires an explicit reason per master spec; no invented candidates.
Live acceptance project created at SDD/live-ui-project by live-case-setup.py. Synthetic C1 aggregate improvement and C2 differing composition, G1 identification question. Public corpus declaration/extract/synthesis registrations, earlier transitions injected declared_only; root author and nonvoting coordinator. No real research approval or full pipeline completion claimed. Pending H1 creation with Task09 API and fresh real role workers Task10.

Task 09: complete (bf65d7c..93a5f03, review clean).245passed final12.50s; root fresh public H1 register/replayPASS. Reviewer future authenticated independence/advancement boundary belongs10+ notmissing09. Task10 next under current user authorization.

Task 10: in progress BASEdfa63a0; implementer m1_task10. Root owns fresh host roles and exact submissions; no opinion generation by implementation worker. Review lifecycle/schema agreement pending.

Ruling: Task10 prepare_council starts actual review NodeAttempt from latest current hypothesis authoring review_pending, atomically sets currentnode review, retains source history without scientific approval, binds session source_attempt_id/review_attempt_id/exacthypothesis+evidence. Necessary resume integration handles session phase without normal authoring packet. Required for Task13 review return topology and truthful UI phase. Cost: extra narrow lifecycle integration now instead of inconsistent synthetic review later.
Ruling: Initial issues are structured with stable IDs/raiser/target/evidence/question/impact/severity/resolution_condition, not just strings; avoids coordinator inventing severity/identity in Task11. No forced recommendation or issue count. Pre-disclosure replacement preserves failed assignment and original history; actual execution attestation remains separate from declared CLI fields.

Task10 root livehost acceptance: domain/methodology/critical independently returned own initials, exactpayload registration succeeded;2initials still concealed fromthird, all3 reveal identical frozen snapshot. Session911e9f.. reviewattempt180a77.. contains6issues(3blocking/3major) fromrealworkers. Domain own raised_by schema correction only, no root authored opinions. Engine provenance declared_only; external nativehost observations stored separately. Task10 finaltests/review pending.

Task 10: complete (dfa63a0..e513bfc, review clean).325passed36.53s. Root actualhost acceptance observed3distinctcanonicaltasks and ownpayloads; independent reviewer cannot authenticate host externally, resolved by preserved nativehost observations with bounded declared-vs-observed scope. No scientific independence signature claimed. Task11 next.

Task 11: in progress BASEda71d3d implementer m1_task11. Root actual roles preserved for followup. User task remainsUI through16, notpause after11.

Task11 agreed schema: perassignment response bundle with rationale/responses/new_issues; allroles response then final positions accountall knownissues. Root prepared same frozen allinitials + evidence packets with explicit agreed Task11 outputcontract while enginecode pending; actualdomain/method followups dispatched. Sourcecontent and binding unchanged; no new evidence or coordinator-written responses.

Task16 independent UI polling slice started by controller while Task11 worker implements distinct Python files. Ruling: existing Sites ownership requires controller UI edits; frozen View head_id contract makes standalone live.js polling independent of backend decisions. Keep uncommitted until Task16 integration/review, no UI-connected claim now. Cost: small added module/file beyond original map. TDD4failed missing implementation ->12UItests passed(4new+8existing); polling serializes, avoids sameHEAD rerender, retains data/update time onerror, ignores late result afterstop. Actual selection/scroll/browser checks still Task16. Task15 build_view must expose top-level head_id.

Task11 rootactualhost acceptancePASS:3responsebundles then3finalpositions registeredverbatim; phase final_positions_complete. Allrolesrevise; actual dialogue distinguishes M1 clarification from M2 detailed design, retains openissues (no data/revision supplied). Rawresponses/finals+hashes+exactnativeIDs preserved. Roothelper final print assumed list rather than dict, fixeddisplay only; engine succeeded.
Task16 standalone HTTP slice (controllerowner) added m1_viewer.py, scratch SDD/task16_viewer_test.py. Expected missingmodule5setupfailures ->5passed2.83s. Tests realHTTP loopback/Host/Origin/write405/routeallowlist/visibleactualartifact+inerttext/readonlyfiles with injected viewadapter. build_view notyetimplemented, CLI notconnected, staticUI notyetlive; no completionclaim. Keep source uncommitted for16review; doesnotaffect11ownedfiles.

Task11 implemented fee0fcb:348scopedpass63.41s,60focusedpass50.56s. Root3actualresponse/finalregistrationPASS plus finalcode separateCLI replay retainslaterHEAD andexactreceipt. Independentreviewpending. Task16 controlleruncommitted newviewer/live polling untouchedbyworker.

Task11 review round1 Needsfixes: Important new_issues:[null] reaches issue.get before dict validation, uncaughtAttributeError instead ofCLIexit2. Purevalidator reproduction byreviewer. Implementerresumed scopedfix round1 BASEfee0fcb withRED/GREEN+CLIstatepreservation; no nexttask untilrereview. Livevalidpayloads unaffected.

Task11 complete at 82fd0ca: independent scoped re-review Approved, no findings. Actual host responses/finals registered; all three revise, six issues open. Task12 fresh implementer started, root continues UI preparatory work.
Task16 root preparatory UI slice: replaced demo fetch with /api/view, serial 3s feed, selected node/decision retention, disclosure and scroll preservation. RED selection tests 2 failed missing function; GREEN existing8+poll4+selection2=14 pass. Added text-only council rendering and raw/source link rendering; dependent view schema alignment and actual browser acceptance remain pending. No Task16 completion claim.

Task12 complete30413b3: independentreviewApproved aftercanonicalreplayfix. Regression469passed; fixsubset13passed149deselected. FinalCLIactualdecisionexactreceipt/HEADpreserved. Task13freshworkerstarted.

Task13 completed d5d7a78 after2scopedreviewfixes; independentApproved. Mainfocused31 and relevant59passed; finalfix11passed28deselected. Actualplan2affected7reusable, exactCLIandread-onlysnapshotverified. Task14freshworkerstarted; rootwillapplyactualreturnthenauthorr2.
