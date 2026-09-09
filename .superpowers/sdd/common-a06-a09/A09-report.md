# A09 implementation report

Base ae15e0c; accepted read-only proposal implemented after A08 approval.
Only budgets.py, test_budgets.py, budget-inputs.md and this report changed.

Pure assess_next_work consumes a complete backed work ledger (including explicit
empty ledger), exact descriptors and historical work versions. Repeats ignore
UUID/event/actor/assignment/HEAD-label changes. Text normalization is NFC plus
whitespace only and preserves scientific case; explicit semantic uncertainty
awaits input. A08 historical reference resolution avoids treating changed input
revisions as either missing history or old work. One-use corrections bind exact
previous work, replacement signature, evidence and current A07 approval/receipt.
Declared return/run/cost budgets are separate; unknown cost under a required cost
limit awaits input. Resume preserves prior failed/inconclusive status and returns
concrete next actions without changing prior status or marking completion.

Validation: initial fixture collection issue (pytest-reserved parameter request)
was corrected before RED. Focused RED: 21 failures for missing budgets module.
Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_budgets.py -q`
→ 21 passed (0.85s). `git diff --check` clean. Cases cover identity-only repeats,
scientific case preservation, semantic uncertainty, unknown cost, each budget,
unused independent limit, exact correction approval/reuse/refusal, failed resume,
missing/omitted ledger, malformed resources/collections, changed historical inputs,
no-I/O purity, snapshot/payload/HEAD and old referenced byte preservation.
No predecessor/broad tests run per root instruction; root owns final integration.

Limits: synthetic structural policy fixtures only. No semantic equivalence claim,
scientific validation, real execution, counter mutation, prerequisite producer,
CLI/UI, approval authority or user acceptance. Ledger/receipt producers remain
future prerequisites, so absence fails closed. A ready result is narrow policy
eligibility and does not grant execution permission.

## Independent review correction wave

Reproduced all three false-ready findings as focused RED: 3 failed, 21 passed.
Envelope versions now require exact types, so schema_version=true is rejected.
Every nonnull historical work correction reference is validated, including exact
prior ledger work and replacement-signature linkage to its recorded attempt.
Correction evidence rejects duplicate project/artifact/digest nodes, preventing
copied used corrections from obtaining a distinct fingerprint via duplicated
references (including alternate HEAD labels). Tests assert refusal and unchanged
HEAD for all three findings.

Final focused GREEN: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_budgets.py -q`
→ 24 passed (1.03s). `git diff --check` clean. No broad or predecessor tests.
