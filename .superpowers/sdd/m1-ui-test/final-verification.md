# M1 UI and actual-host acceptance evidence

Production: eabc522 U1, db8e228 U2; independently reviewed without P1/P2 findings.
Final native HEAD: 23e00ee20dc06c1ae2a55268765ccd0b01954270c109b250c147866d1d126fce.

- Fresh affected Python suite:15 passed in85.90s (`test_views.py`, `test_viewer.py`, `test_cli.py`).
- Fresh Node suite with final HTTP snapshot:11 passed in61.48ms, no skips;
  rendered10 revisions,72 statements and11 Issues across all detail panels.
- All8 served UI assets returned200; final GET /api/view contains1 issued handoff.
- `check_live.py` passed:9 nodes,10 revisions,8 councils,72 actual submissions,
  90 distinct actual Codex sessions, no recorded role tool calls, historical
  partial first opinion hidden and selected HEAD preserved. Its initial harness
  invocation used a positional argument for keyword-only head_id; corrected
  that call only and reran successfully. Production API was unchanged.
- Actual r1:7 major hypothesis objections and revise judgments. Actual r2:no
  new objections; prior Issues still blocked until7 fixed-rule logic checks and
  independent resolutions. Two optional questions remain open. Two supplied
  source checks are separately resolved. No automatic closure by revision.
- All M1 nodes reviewed; work ledger ready. Handoff issued_awaiting_acceptance,
  gate false solely handoff_acceptance_required. No M2 receiving actor or
  acceptance was invented, and no M2 experiment ran.
- Original85 files and imported76 files remain byte/mtime-identical to baseline.
- U2 wheel inventory includes all9 package files; no packaging change needed.
- `git diff --check` passed. No unchanged broad438-test baseline was repeated.

Origin is synthetic; corpus receipt is explicitly a development-test declaration,
not real user research approval. Actor/host responsibility remains declared,
model is configured default/unverified, and isolation is instructions_only.
Local raw run artifacts (~51MB before final accounting) remain ignored; scripts
and compact evidence are retained for traceability without indexing all prompts.

Browser limitation: Chrome tab2026905667 at127.0.0.1:8767 shows
ERR_BLOCKED_BY_CLIENT; in-app browser unavailable. Actual360/736px layout,
theme contrast, keyboard and scroll restoration acceptance remain pending.
No DOM test or source review is represented as visual verification.
