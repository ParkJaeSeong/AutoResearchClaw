# SDD ledger — plan: docs/superpowers/plans/research-governance/tasks/A06.md through A09.md

User priority: finish common foundation A06–A09 before UI. Base da56c6d, clean existing isolated feature/m1-research-graph. Previous exact base regression207passed4.21s. No dependency/env changes. Execute serial task implementations with independent task reviews; root final impacted suite once after last fixes. No B/UI/experiments/push/merge.

| Tasks | Shared boundary | Preflight |
|---|---|---|
| A06 self | pure validator tuples vs boilerplate mutation | specific interface governs; no arbitrary write operation |
| A06→A07 | positions, acknowledgement, gate requirements | freeze minimal closed registered input contracts, missing input fails closed |
| A07→A08 | gate approvals and impact | exact version refs, no new approval authority |
| A08→A09 | dependency versions and repeat binding | deterministic comparison, uncertain meaning waits, no execution |
| A08 self | list[str] refs vs SnapshotRef | document canonical reference key binding; immutable old objects |
| A09 self | pure assessment vs repeat mutation boilerplate | assess only; no automatic counters/execution claims |

Todo A06 [ ] implement [ ] review; A07 [ ] implement [ ] review; A08 [ ] implement [ ] review; A09 [ ] implement [ ] review; [ ] final regression/preservation/docs.

A06 bindings: public read-only commands.read_policy_snapshot reuses verified context; validators accept Position/Decision directly and return {code,path,message} tuples. Ack must bind exact position, claim, disposition, summary and original assignment actor. Registered session freezes input binding/participants; B02 creates later. Evidence_added uses artifact/content distinction, not HEAD-only relabel. All pure validation and no inferred role approval.

A06 implementation1dbda3b focused7passed0.46s. Reviewer /root/common_review: duplicate claim_ref dispositions overwrite prior unacknowledged conclusion (P1); malformed session participant dict raises TypeError before tuple errors (P2). Same implementer fixing one wave, no further findings.

Task A06: complete at093fe68, independent re-review PASS, focused9passed0.60s. Session checks participant string/backed active assignment; no new UUID-format assertion (A04 existing assignment contract). A07 worker /root/rg_a07 base093fe68 GO.

A07 contract proposal accepted: backed gate_requirements holds milestone/kind/target/input/author assignments/required role mapping/submissions/source refs/approval refs/decision ref. Fixed milestone required reviewers, independent actual actors same frozen input, typed ApprovalBinding exact current receipt/scope, no caller ready authority or omission-based pass. Pure deterministic reasons/actions; revalidate accepted M1 empirical transfer and derive issue trail state.

A08 read-only contract proposed /root/rg_a08; no edits until A07 approval. Canonical full SnapshotRef strings as changed_refs, historical byte validation, DAG logical node identity(project,artifact,sha) ignores HEAD-only relabel, all relations upstream→dependent; direct approval scope impacts considered; no reviving invalid approvals. Outputs affected_refs/approval_checks/reusable_refs/event_plan(uncommitted).
Tool thread limit hit for new A09 worker and resurrecting evicted rg_a05_review. Available agents now root, rg_a07, rg_a08, completed rg_a02_review. Reuse available reviewer rg_a02_review and later completed worker for A09; no repeated spawn attempts.

A07 implementationcf1763e focused19passed4.02s; reviewer rg_a02_review two P2s reproduced: unbound actual oppose can pass when coordinator action handoff; approval_bindings=None raises AttributeError instead failclosed assessment. Same worker rg_a07 fix wave requested. A09 read-only proposal prepared by rg_a07 for later reuse (thread limit): work+resources+correction approval+semantic status+resume ref; NFC/whitespace normalize only, separate resource budgets, backed work ledger/one-use scoped corrections, pure outputs. No A09 code before A08 approval.

Task A07: complete0d1be24. Same reviewer approved fix, targeted16passed19deselected3.65s; focused35passed. A08 GO base0d1be24 sent to rg_a08.

A08 RED24 expected missing module failures0.65s; valid backed synthetic fixtures, implementation underway.

A08 implementation71c6197 focused34passed0.61s. Review oneP2: typed ID collision introduced after ancestor ignored for current reuse; rg_a08 fixing HEAD ambiguity check+regression. Other scope paths no materialfindings.

Task A08: completeae15e0c, independentfixreviewPASS, focused35passed0.64s. A09 GO to rg_a07 (availableagentreuse afterthreadlimit), baseae15e0c.

A09 implementation3fcbb86 focused21passed0.85s, pure policy/completebackedledger/oneusecorrection/separatecostresources. Review rg_a02_review underway A09 and concrete sharedboundaries; finalaffected suite pending.

A09 review3P2s: boolschema_version accepted; malformed historical correction_ref ignored; duplicate correction evidence changes usefingerprint and permits retry. Same worker fixingonewave: strictversiontype, everyhistoricalnonnullcorrection validated, evidenceidentitydedup/reject. No other materialintegrationfindings.

Task A09: complete916c5ce. Scopedfix+commonintegration reviewPASS, no remainingfindings. Final affected suite310passed14.15s. Final original85/imported76files SHA256/mtime/HEAD unchanged. A01–A09 allcomplete; B01–B07/UI/actualresearch stillpending. Root finaldocscommit follows.
