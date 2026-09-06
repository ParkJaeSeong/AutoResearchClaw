# Task 3 report: handoff, skill and acceptance integration

## Source behavior

Implemented the Stage 14/15 integration boundary without changing the canonical
analysis evidence-packet schema or bytes.

- Stage 14 handoff now derives its live phase from `analysis_status()` and routes
  to `analysis prepare`, `register-review`, `register-rebuttals`, or
  `register-result` as appropriate.
- Generic `stage prepare` / `stage validate` remain limited by
  `SUPPORTED_STAGE_IDS == 1..11` and now fail explicitly at Stage 14 and Stage
  15, so they cannot bypass analysis registration.
- A completed analysis returns a read-only Stage 15 `research_decision`
  boundary with `unsupported_stage_15`; its verification command is
  `analysis status`, and no `analysis/decision.json` is created.
- The Stage 14 contract declares both `analysis/results.json` and
  `analysis/report.md`.
- Report metric rows identify `Baseline result` and `Selected candidate`, so
  same-named metrics remain readable without interpreting object hashes.
- The skill documents complete review, response, and synthesis schemas; exact
  CLI commands; evidence reading; three-role isolation before disclosure; one
  response round; non-voting synthesis; missing-evidence treatment; and the
  no-provider/no-execution/no-code-ranking boundary. It explicitly permits the
  five caller-owned `analysis/submissions/*.json` staging inputs while reserving
  durable publication paths for registration.
- Historical Stage 13 limitations remain preserved as source context. The
  registered final selection and completed Stage 13 are documented as current
  state authority.

## TDD evidence

Initial contract, Stage 14 route, generic-bypass, and Stage 15 boundary RED:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_contracts.py::test_stage_fourteen_contract_declares_structured_and_readable_analysis_outputs tests/codex_native/test_handoff.py::test_stage_fourteen_handoff_routes_to_phase_specific_analysis_commands tests/codex_native/test_handoff.py::test_stage_fourteen_generic_validation_cannot_bypass_analysis_registration tests/codex_native/test_result_analysis.py::test_analysis_registration_cli_completes_public_workflow -q
FFFF                                                                     [100%]
FAILED ... required_outputs lacked analysis/report.md
FAILED ... await_stage_fourteen_support != prepare_analysis
FAILED ... generic Stage 14 task-packet error instead of dedicated analysis route
FAILED ... report_computational_package_milestone_only != unsupported_stage_15
4 failed in 7.28s
```

Initial integration GREEN:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_contracts.py::test_stage_fourteen_contract_declares_structured_and_readable_analysis_outputs tests/codex_native/test_handoff.py::test_stage_fourteen_handoff_routes_to_phase_specific_analysis_commands tests/codex_native/test_handoff.py::test_stage_fourteen_generic_validation_cannot_bypass_analysis_registration tests/codex_native/test_result_analysis.py::test_analysis_registration_cli_completes_public_workflow -q
....                                                                     [100%]
4 passed in 6.99s
```

Explicit Stage 15 generic-validation RED:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_result_analysis.py::test_analysis_registration_cli_completes_public_workflow -q
FAILED ... expected "Stage 15 research decisions are read-only and unsupported" but received generic task-packet error
1 failed in 2.62s
```

Metric source readability RED/GREEN:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_result_analysis.py::test_analysis_result_binds_same_metric_to_baseline_and_selected_sources -q
FAILED ... "Baseline result — `mae_cycles`: 2.5 cycles" not in report
1 failed in 20.88s

$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_result_analysis.py::test_analysis_result_binds_same_metric_to_baseline_and_selected_sources -q
.                                                                        [100%]
1 passed in 20.54s
```

Awaiting-synthesis handoff RED:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_handoff.py::test_stage_fourteen_handoff_routes_to_phase_specific_analysis_commands -q
FAILED ... KeyError: 'register_analysis_result' / ValueError: analysis_status_invalid
1 failed in 2.48s
```

Required combined source suite:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_result_analysis.py tests/codex_native/test_handoff.py -q
.........................................                                [100%]
41 passed in 127.70s (0:02:07)
```

Affected Stage 13 boundary regressions after updating the former read-only
Stage 14 expectation:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_refinement_execution.py::test_finalize_select_candidate_retains_verified_refinement_evidence -q
.                                                                        [100%]
1 passed in 20.30s

$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_stage13_multi_agent_e2e.py -q
..                                                                       [100%]
2 passed (observed in the combined affected-boundary run)
```

Fresh final affected integration selection, including the restored synthesis
route and report rendering:

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_handoff.py::test_stage_fourteen_handoff_routes_to_phase_specific_analysis_commands tests/codex_native/test_handoff.py::test_stage_fourteen_generic_validation_cannot_bypass_analysis_registration tests/codex_native/test_result_analysis.py::test_analysis_registration_cli_completes_public_workflow tests/codex_native/test_result_analysis.py::test_analysis_result_binds_same_metric_to_baseline_and_selected_sources tests/codex_native/test_result_analysis.py::test_analysis_result_preserves_dissent_and_publishes_retry_safe_report tests/codex_native/test_contracts.py::test_stage_fourteen_contract_declares_structured_and_readable_analysis_outputs -q
......                                                                   [100%]
6 passed in 29.59s
```

Static and skill validation:

```text
$ /opt/homebrew/bin/python3.11 /Users/jspark/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/researchclaw
Skill is valid!

$ /opt/homebrew/bin/python3.11 -m ruff check researchclaw/core/contracts.py researchclaw/core/handoff.py researchclaw/core/project.py researchclaw/core/task_packets.py researchclaw/core/analysis_report.py tests/codex_native/test_contracts.py tests/codex_native/test_handoff.py tests/codex_native/test_result_analysis.py tests/codex_native/test_refinement_execution.py tests/codex_native/test_stage13_multi_agent_e2e.py
(exit 0, no output)

$ /opt/homebrew/bin/python3.11 -m compileall -q researchclaw/core/contracts.py researchclaw/core/handoff.py researchclaw/core/project.py researchclaw/core/task_packets.py researchclaw/core/analysis_report.py
(exit 0, no output)

$ git diff --check
(exit 0, no output)
```

## Acceptance, deployment, and actual project status

The controller separately completed the actual-role acceptance on the disposable
copy at `/private/tmp/researchclaw-stage14-acceptance.MOV9ba/project`: three
genuine independent role reviews were registered before disclosure, one actual
challenge/response round was retained, the synthesis/report distinguished the
synthetic MAE improvement from scientific generalization, and resume stopped at
the read-only unsupported Stage 15 boundary. It reported no experiment rerun and
no mutation of prior evidence bytes.

This task worker did not mutate that copy or the user's live project. The user's
live project therefore remains under user control at its prior durable state;
only the isolated source worktree changed here. No package installation or
deployed release was performed or claimed. Final code review and any deployment
remain controller-owned follow-up work.

## Review fix round 1: example evidence references

The Task 3 review found four schema examples that used
`analysis/evidence_packet.json` as a substantive `evidence_refs` value instead
of demonstrating a path from the packet's `inputs`. The examples now use the
selected immutable result object or registered design input. Test submission
fixtures were aligned to the selected-result input as well; the validator and
canonical packet were not broadened or changed.

```text
$ /opt/homebrew/bin/python3.11 -m pytest tests/codex_native/test_result_analysis.py::test_analysis_rebuttals_require_all_roles_and_bind_actual_producers tests/codex_native/test_result_analysis.py::test_analysis_result_preserves_dissent_and_publishes_retry_safe_report -q
..                                                                       [100%]
2 passed in 4.87s

$ /opt/homebrew/bin/python3.11 /Users/jspark/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/researchclaw
Skill is valid!

$ /opt/homebrew/bin/python3.11 -m ruff check tests/codex_native/test_result_analysis.py
(exit 0, no output)

$ git diff --check
(exit 0, no output)
```
