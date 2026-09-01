# Stage 13 Multi-Agent Refinement Design

**Date:** 2026-09-01  
**Status:** Approved

## Purpose

Stage 13 turns one immutable Stage 12 research result into a bounded refinement
session. Research judgments come from deliberation among Codex agents. The
plugin supplies evidence, validates procedure and authority, executes approved
contracts, and preserves provenance. It does not call an LLM API or select a
candidate with a hard-coded score rule.

The first implementation supports computational experiments. Laboratory and
other physical-experiment modes may reuse the deliberation protocol later, but
Stage 13 must not claim that it can autonomously perform physical work.

## Project-Wide Governance Principle

Research judgments are made through independent agent assessments followed by
recorded deliberation. Deterministic code validates evidence, procedure,
authority, resource limits, and reproducibility.

This principle applies first to Stage 13 and is reusable in judgment-heavy
stages such as synthesis, hypothesis generation, experiment design, result
analysis, research decisions, peer review, and quality gates. Existing Stages
1-12 are not rewritten as part of this project. They may adopt the shared
deliberation foundation later through separately reviewed changes.

## Differences From Upstream

The upstream Stage 13 invokes an internal LLM client, rewrites experiment code,
and may rerun it for as many as ten iterations. The Codex fork replaces that
loop with an explicitly invoked agent workflow:

- no embedded or external LLM API client;
- no API key requirement;
- no single-agent unilateral research decision;
- no overwrite of the registered Stage 12 result;
- no experiment outside a user-approved resource envelope;
- no hidden metric-based auto-selection rule.

## Roles and Authority

### Coordinator agent

The coordinator owns workflow state but has no vote. It:

- opens the durable project and verifies the Stage 12 evidence registration;
- creates a common evidence packet;
- assigns bounded tasks to deliberation and implementation agents;
- routes assessments, rebuttals, and revised positions;
- invokes deterministic CLI operations;
- reports the final decision and dissent to the user.

The coordinator may not replace a council decision with its own preference.

### Deliberation council

The default council has three voting agents:

1. a topic-adapted domain researcher;
2. a methods and statistics reviewer;
3. an adversarial reproducibility reviewer.

All members receive the same closed evidence packet. They write initial
assessments independently before seeing other assessments. They then exchange
challenges, answer objections, and submit revised positions. At least two of
three valid votes are required for a decision. Initial positions, changes of
mind, dissent, and unresolved questions remain durable artifacts.

Agents use the currently available Codex model infrastructure. Role and context
separation reduce correlated bias but do not make agents statistically
independent models. The protocol leaves room for heterogeneous models later.

### Implementation agent

An implementation agent receives only a council-approved change request and a
candidate workspace. It may create or modify candidate code, configuration,
tests, and package metadata. It does not vote on a candidate it implemented and
cannot execute a research run or alter registered evidence.

### Deterministic plugin services

Plugin code:

- verifies artifact identities and the common evidence packet;
- validates schemas, package contracts, data-split isolation, and metric
  continuity;
- enforces the approved resource envelope;
- prepares self-test and research execution contracts;
- registers candidate results as immutable evidence;
- persists resumable session and deliberation state.

Plugin code must not decide that a candidate is scientifically better merely
because a fixed numeric threshold or iteration count was reached.

## Explicit Invocation and User Experience

The user starts one bounded Stage 13 workflow with an explicit plugin request,
for example:

> ResearchClaw로 이 프로젝트의 13단계 개선 세션을 수행해줘.

The user does not run every internal CLI command. The coordinator orchestrates
subagents and commands. Before research execution begins, the session records a
user-authorized envelope containing maximum wall time, maximum research runs,
resource limits, allowed inputs, and permitted change scope. Self-tests and
static checks do not consume a research-run slot.

Research-specific improvement and stopping criteria are proposed and decided
by the council from the evidence. Hard maxima exist only to prevent runaway
execution. Work outside the envelope requires new user authority.

## Session Artifacts

Stage 13 uses a new `refinement/` namespace and never treats mutable session
files as registered Stage 12 evidence.

```text
refinement/
├── session.json
├── evidence_packet.json
├── deliberations/
│   └── round-001/
│       ├── domain_review.json
│       ├── methodology_review.json
│       ├── critical_review.json
│       ├── rebuttals.json
│       └── decision.json
├── candidates/
│   └── candidate-001/
│       ├── code/
│       ├── package_contract.json
│       ├── self_test_report.json
│       ├── execution_contract.json
│       └── results.json
└── final_selection.json
```

Every durable record includes a schema version, project ID, session ID,
artifact bindings, creation time, and the producing role. Council artifacts
also bind to the exact evidence packet and candidate result identities they
evaluate.

## Workflow

### 1. Prepare session

The plugin requires a Stage 13 project grounded by exactly one verified Stage
12 registration. It snapshots references to the approved design, package,
resource plan, execution contract, registered result, and immutable evidence
manifest. It writes `session.json` and `evidence_packet.json` without modifying
the Stage 12 artifacts.

### 2. Decide the refinement target

Council members independently diagnose the baseline. After rebuttal they
either:

- approve a bounded change request;
- conclude that no justified refinement is available;
- request a small discriminating experiment within the approved envelope; or
- return `inconclusive` with the missing evidence.

Only a council-approved change request can open a candidate workspace.

### 3. Build and validate a candidate

The implementation agent writes one candidate in an isolated directory. The
plugin validates its traceability to the Stage 9 design and council decision,
then prepares and registers a candidate self-test using the Stage 10-12
contracts. A failed candidate remains recorded but is not eligible for research
execution.

### 4. Execute within the envelope

For an eligible candidate, the coordinator asks the plugin for an execution
contract and runs only its authoritative argv. The plugin rejects stale
bindings, input drift, budget violations, undeclared outputs, and attempts to
replace prior results. A completed candidate result is registered as a new
immutable evidence object.

### 5. Deliberate on results

The council evaluates the baseline and all eligible candidates. It decides
whether to refine again, select a candidate, retain the baseline, or finish
inconclusively. Automated code validates that the decision references existing
evidence and valid votes; it does not evaluate scientific merit.

### 6. Finalize

`final_selection.json` records the selected evidence, rationale, supporting
votes, dissent, limitations, and issues for Stage 14. Finalization never deletes
or rewrites the baseline or non-selected candidates. A conclusive selection or
an explicit `inconclusive` decision advances the project to Stage 14.

## Deliberation Protocol

Each round has four phases:

1. **Independent assessment:** private initial position and evidence links.
2. **Challenge:** each voter identifies omissions, counterexamples, and weak
   assumptions in the other positions.
3. **Response and revision:** each voter answers challenges and submits a final
   position with any change rationale.
4. **Decision:** the coordinator records the vote without changing it.

A decision requires at least two matching final positions from three valid
voters. The decision schema distinguishes `refine`, `select_candidate`,
`retain_baseline`, `request_discriminating_run`, and `inconclusive`.

## Failure, Disagreement, and Resume

- A failed agent task is retried once with a fresh agent in the same role.
- If that retry fails, the session continues only when at least two voters
  remain valid; the vacancy is recorded.
- Fewer than two valid voters pauses the session.
- A first disagreement triggers one challenge and revision round.
- If no two-thirds decision follows, the council may request a discriminating
  run inside the existing envelope.
- If evidence remains insufficient or additional authority is required, the
  session pauses and reports the exact dispute to the user.
- Contract, integrity, containment, or budget failures cannot be overridden by
  a vote.
- All partial state is durable and resumable. Resume revalidates every bound
  artifact before assigning new work.
- The Stage 12 baseline remains unchanged under every failure path.

## Security and Integrity Boundaries

- Stage 12 manifests and evidence objects remain immutable.
- Candidate directories are isolated and have declared writable paths.
- Candidate code cannot modify council records, session authority, or evidence
  objects.
- Decisions bind artifact hashes rather than unverified paths.
- Metric names, directions, split strategy, and primary evaluation inputs may
  change only when the council explicitly requests a design-level change and
  the user grants expanded authority. Such a change is not silently comparable
  to the baseline.
- An agent-authored statement is never treated as evidence without a registered
  artifact binding.

## CLI Primitives

The plugin command is the user-facing entry point. The underlying deterministic
CLI is intentionally granular so operations are testable and resumable:

- `refinement prepare-session`
- `refinement register-assessment`
- `refinement register-deliberation`
- `refinement register-decision`
- `refinement register-candidate`
- `refinement prepare-self-test`
- `refinement register-self-test`
- `refinement prepare-run`
- `refinement register-result`
- `refinement status`
- `refinement finalize`

These commands never invoke an LLM. They validate and persist agent-produced
artifacts or return authoritative execution instructions.

## Testing Strategy

Implementation follows test-driven development. Required coverage includes:

- Stage 13 cannot start without verified immutable Stage 12 evidence;
- session preparation is read-only with respect to Stage 12;
- all voters receive the identical evidence packet identity;
- assessments written before disclosure remain independently registered;
- an implementation agent cannot cast a selection vote;
- invalid quorum, fabricated evidence references, and rewritten votes fail
  closed;
- candidate writes are contained and cannot replace the baseline;
- self-test and execution follow the installed `uv tool` launcher contract;
- resource-envelope exhaustion prevents another run;
- interrupted commands resume without duplicate evidence or votes;
- finalization preserves every baseline and candidate result;
- conclusive and `inconclusive` outcomes both provide a valid Stage 14 handoff;
- existing Stage 1-12 tests remain green.

End-to-end tests use small synthetic experiments and deterministic agent
artifacts. They do not require a live LLM or network call.

## Delivery Scope

The first delivery includes the reusable deliberation records, Stage 13
session/candidate lifecycle, computational candidate execution, final selection,
and Stage 14 handoff. It excludes retrofitting earlier stages, physical
laboratory execution, heterogeneous model routing, and unbounded autonomous
loops. Those remain separate future decisions.
