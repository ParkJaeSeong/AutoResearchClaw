# SDD ledger — plan: docs/superpowers/plans/2026-09-09-research-governance-core.md

Authorized first implementation batch A01–A03 following user '구현을 시작해도 될끼?'. Base df36f08, existing isolated worktree feature/m1-research-graph. No merge/push/hosting, no experiments. Remaining A04–E08 not part of this batch completion claim.

Skills: subagent-driven-development for task implementers/reviewers; existing worktree reused under using-git-worktrees; TDD and verification-before-completion. Root owns ledger/acceptance/docs; workers own bounded code/tests.

Preflight: git dir differs common dir, no superproject; clean baseline. `.venv/bin/python -m pytest tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py -q`:60passed0.67s. Whole repository historical baseline remains incomplete; don't claim green.

A01 running /root/rg_a01. Root prepares actual M1 source integrity snapshot and A02/A03 integration boundaries independently.

Ruling: A01 is pure schema validation; generic plan mutation assertions apply only A02+. No imaginary HEAD writes in contract tests. A02 will preserve M1 path/version/error APIs and monkeypatch-based durability test seams. A03 imports into a separate empty root, never inplace conversion or takeover of active source council.


## Preflight interface/task matrix
| Tasks | Producer / consumer or internal consistency | Finding / ruling |
|---|---|---|
| A01 | pure validate_record; generic plan says assert HEAD | Ruling: pure errors and input immutability tests only; no store dependency |
| A02 | low-level shared store, commands registry and init | Ruling: explicit initialize_record interface needed for A03 atomic genesis; preserve m1 error/wrapper seams |
| A03 | import_m1 into empty target; source frozen head | Ruling: complete archive+projection staged before single publication, not init-empty then second commit |
| A01/A02 | UUID project/version contracts → genesis state | Strict new IDs; legacy origin refs kept opaque |
| A01/A03 | new closed Issue schema → imported issues | Stable new UUID mapping + preserved raw source archive; no fabricated resolver evidence |
| A02/A03 | initialize_record/commit_record and CLI parser shared | Sequential ownership; document init API for worker before dispatch |

Later A04–A09 execution is outside current authorized first batch; their planned shared interfaces remain specification only. Preflight skills script lacked executable bit; used bash without changing plugin permissions.

A01 implementation d82bce2:10 record kinds+10synthetic examples; implementer107contracts regressionpassed; root90newpassed0.04s; source85files/HEAD preserved. Independent review /root/rg_a01_review pending. Ruling: issue owner nullable for truthful unassigned imports; exact attempt references UUIDs; embedded foreign archived SnapshotRef allowed. Full lifecycle/reference existence is A04+, not shape validator.
Review packaging helper failed because nested bundled sdd-workspace is not executable. Used explicit git diff df36f08..d82bce2 and named spec/plan/report paths; did not change plugin permissions.

Task A01: complete d82bce2, independent Approved;90tests+4864malformed mutation observations. Task A02: running /root/rg_a02.

A02 implementation599dcd3;299passed86.95s; reviewer /root/rg_a02_review running exactd82bce2..599dcd3. Root separateCLI init/replay/inspect equal (headf355...); originalsource85files/HEADpreserved. initialize_record API recorded ina03-context. No finalapprovalclaimyet.

Task A02: complete599dcd3 independentApproved. Optional P3 regressiongaps addressed byroot2tests, store18passed0.46s, uncommitted untilA03workercommit finishes. Task A03 running /root/rg_a03.

A03 rootreview steering before taskcommit: issue origin must mapped review_attempt_id, not reviewed hypothesis attempt; legacy content_origin research→real explicitmapping preserves original metadata; malformed extensible legacy state rejects ValueError; publicimportCLI returns safe summary, Pythoninternalreceipt mayfullarchive. Native exact target refs must resolve when existing pinned M1 view provides target_version_ids/sourceartifact/pointer; unresolved-only may emptywithlimitation. Root actualcase H1r1 resolvable, so blanketemptytargetrefs notaccepted.

A03 implementation86c3ffa,206impactedpassed9.67s; prior320broad87.55s,21focusedaftertargetfix. RootactualimportPASS33commits40objects6open/6targetrefs, old85files/HEADunchanged, CLIreplay1196...same. ReviewP2 malformed disclosedresponse/finalcollections silently treatedempty; implementerfixround1 running. Finalintegration freshspawn failedthreadlimit and archived rg_a01 reviewer unavailable; reused available independent rg_a02_review pertoolinventory. No independenceclaim for implementer's selfcheck.

Task A03: complete663fd12 scopedP2rereviewApproved/no new findings. Final integration rg_a02_review no new findings/conditionP2 satisfied byrg_a03_review. Root152tests1.12s, actualimportreplay1196... andsource85filesHEAD unchanged. A01–A03 batch complete; A04+ notstarted. Keep actual acceptance project for user review (no workspace deletion).
