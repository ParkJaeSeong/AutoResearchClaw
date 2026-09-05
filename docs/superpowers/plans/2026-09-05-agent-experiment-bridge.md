# Agent Experiment Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the real Stage 10 → 12 → 13 path without injecting a test package.

**Architecture:** A repository-owned runner consumes a separately authored pure
regression module. Versioned package validation binds all algorithm, runtime,
self-test and config bytes while retaining legacy evidence semantics.

**Tech Stack:** Python 3.11+, existing stdlib/pytest tools and installed CLI; no
new dependencies or external services.

**Spec:** docs/superpowers/specs/2026-09-05-agent-experiment-bridge.md

## Global Constraints

- No external LLM API, provider configuration, model subprocess, new package installation, network call or paid service is part of the new runtime.
- Codex agents own algorithms and scientific decisions; CLI owns deterministic validation and evidence. Low MAE does not automatically approve a candidate.
- Preserve old approved evidence byte-for-byte.
- Do not relax legacy capability checks globally to make a new package pass.
- Do not implement Stage 14 analysis, a general experiment scheduler or a model provider.
- No test helper package substitution is permitted above approved Stage 9 in the decisive integration test.

## Task 1: Complete the authored-package execution vertical slice

This is one coupled integration unit: the runtime cannot be accepted without
its normal authoring contract and registration path. Do not split it into
independently claimed completions that depend on test-only package replacement.

**Files:**
- Create focused runtime/algorithm-validation module(s) under researchclaw/core/
  (agent_experiment.py for authored interface; agent_experiment_runtime.py for IO).
- Modify researchclaw/core/computational_package.py, contracts.py, task_packets.py
  for explicit new package outputs and static validation, maintaining the legacy
  path as required by the spec.
- Modify researchclaw/core/experiment_package_contract.py and research_execution.py
  only at versioned dispatch and identity integration boundaries.
- Modify researchclaw/core/refinement.py and refinement_execution.py only where
  necessary for a new-format baseline/candidate; reuse existing transaction gates.
- Modify researchclaw/codex/cli.py only for declared authoring/version selection
  if needed; never add an approval-bypassing run command.
- Update tests/codex_native helpers only to author new-format inputs before
  validation, never to replace or rehash packages after validation in the new gate.
- Create tests/codex_native/test_agent_experiment_bridge.py and targeted unit tests.
- Update skills/researchclaw/references/computational-package.md and affected
  runtime/refinement instructions, plus concise README support boundaries.

**Interfaces:**
- Authored module: `fit(train_rows, config)` and
  `predict(model, feature_rows, config)` as defined in the spec.
- Existing public CLI names, required confirmation flags and exact returned
  argv/cwd remain execution authority.
- New package version, path sets and column mappings must be explicitly closed
  and documented; record the chosen exact schema in the report and spec before
  its consumers are implemented. Legacy schema dispatch stays separate.

- [ ] Write a failing public-flow test first. Construct normal approved Stage 9
  setup with consistent regression design, then prepare Stage 10 and author the
  declared package. The test must not import or call
  `_install_known_answer_stage_twelve_package` or rebind durable artifacts.

```python
# Independent numerical assertions for the eventual real public-flow test:
assert baseline_result["metrics"]["primary"]["name"] == "mae"
assert baseline_result["metrics"]["primary"]["unit"] == "arbitrary_units"
assert baseline_result["metrics"]["primary"]["value"] == 18.0
assert status["current_stage"] == 13
assert original_baseline_objects == current_baseline_objects
```

- [ ] Run `pytest -q tests/codex_native/test_agent_experiment_bridge.py` and record
  the expected failure caused by the missing product contract/runtime.
- [ ] Implement pure authored-module validation and the trusted runtime; do not
  embed the baseline or candidate algorithm into production model-selection logic.
  Test actual computed values and fitting isolation using authored fixture code:

```python
def fit(train_rows, config):
    return sum(row["y"] for row in train_rows) / len(train_rows)

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
```

  The candidate test authors a separate least-squares fit, computed from train
  x/y covariance and variance. Its predictions must not receive test y values.
- [ ] Integrate the complete closed authoring file set and distinct known-answer
  fixture with package validation. Keep static validation non-executing, reject
  unsupported metric names, and bind every executed/read file.
- [ ] Route self-test and baseline execution through existing authoritative CLI
  preparation/registration. Use actual returned argv in subprocess tests, not an
  inferred interpreter. Test wrong expected values and tampered bytes reject.
- [ ] Prove one candidate self-test/run/result registration from the newly
  registered baseline; keep automated votes labelled synthetic and preserve
  existing finalization/Stage 14 rules.
- [ ] Run the focused bridge tests and affected regression modules once on final
  code. Record exact commands, counts, any failures and limitations. Do not rerun
  long unaffected full-tree suites after each small edit.
- [ ] Update user-facing instructions to match the real new path and remove
  contradictory claims of fixed unimplemented code being a research runner.
- [ ] Self-review, commit implementation and tests, and write the full report.

## Controller verification after Task 1 review

- Build an isolated temporary installed tool from this worktree without changing
  the user's current CLI or plugin, and repeat the public bridge smoke.
- Check that the installed imports are from that environment, not repository CWD.
- Run final whole-branch review, resolve findings, and report the genuine covered
  boundary. Merge, production reinstall and push require the user's deployment
  request; no production research approval is inferred from development tests.
