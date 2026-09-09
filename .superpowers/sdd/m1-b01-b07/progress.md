# SDD ledger — plan: docs/superpowers/plans/research-governance/tasks/B01.md through B07.md

Status: COMPLETE. User-authorized B01–B07 backend connection, base a4388da → code 519a7f6, existing feature/m1-research-graph worktree. No UI/M2 execution, actual corpus approval, push or merge.

| Task | Final task commit | Independent review |
|---|---|---|
| B01 origins | 78a8e73 | Approved |
| B02 councils | ab07e88; historical-context integration in B07 | Approved |
| B03 scope/questions | 1b06db7 | Approved |
| B04 search/screen | f11b3a1 | Approved |
| B05 source verification | 5c59905 | Approved |
| B06 hypotheses/prior issues | 42251aa | Approved |
| B07 handoff/accounting | 519a7f6 | Approved |

Implementers: rg_a08 / rg_a07; independent reviewer rg_a02_review. Final batch integration review approved, no remaining P1/P2 findings. Native task reports preserve focused RED/GREEN and correction details. Thread limit required reusing existing agents. Review-package helper execute-bit limitation was handled with exact-base git diff via Python; no duplicate old-branch review.

## Final evidence

- `.venv/bin/python -m pytest tests/codex_native/research_graph -q`: 438 passed in 573.82s, exit 0. See final-tests.log.
- Original 85/imported 76 files: hashes, mtimes and file lists unchanged; preservation-after.json.
- Actual imported six issues: all open, unaccounted, unresolved, no owners; input snapshot and HEAD preserved. actual-issues-after.json. Inputs are synthetic; no scientific validation claim.
- Host observation: actual cross-agent synthetic file read succeeded, 58 bytes/hash checked. instructions_only, no filesystem isolation claim; other hosts untested. host-access-observation.json.
- Same accepted synthetic handoff status: 20.39s → 0.49s after eliminating 642 repeated node checks/597 packet builds. Per-call empty internal cache only; new calls recheck current state.
- Root taskboard, B01–B07 checklists and M1 verification report updated. Final documentation/link/diff checks accompany this ledger commit.

## Preserved integration decisions

- B02 private initial opinions and phase barriers; exact shared Issue wrappers are historical context leaves, never automatic current evidence. Embedded private IDs/hashes still reject.
- B03 revisions may repair stale/invalid prior setups, but preserve disclosed nonoptional Issue publication obligations.
- B04 complete screen corpus + explicit user-declared decision then prior-receipt binding; current approval and rejection remain distinct from council votes.
- B05 supplied UTF-8 captures, access limits, Unicode spans, independent actual A05/A04 records. Mismatch stays blocking. Failed old checks can be explicitly rechecked against repaired current inputs without deleting history.
- B06 all prior issues accounted before missing prerequisites. Explicit authenticated import materialization registers exact existing Issue bytes; no silent query mutation, owner/category/status rewrite or resolution.
- B07 immutable issue/accept/owner-transfer stages and narrow native gate. Frozen M1 ownership is reconciled only through exact native M2 acceptance/events; current new blockers still checked. No M2 project initialization/experiments.
- Work records/ledger cover eligible native units; full history counts replacements and checks reaching checking. Unknown cost stays unknown. Authenticated replaced wrong-author setups may be excluded, but current invalid/unbacked sources still reject and all history/replacement counts remain.

Next: E01 M1 read-only projection, then visible conversation/decision/Issue/return UI. E01 overall M2/M3 scope remains unfinished. Do not redispatch completed B tasks or claim actual research/UI completion.
