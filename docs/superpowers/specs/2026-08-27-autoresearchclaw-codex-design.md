# AutoResearchClaw-Codex Design

**Date:** 2026-08-27
**Status:** Approved in conversation; pending written-spec review
**Upstream:** `aiming-lab/AutoResearchClaw`
**Target repository:** `ParkJaeSeong/AutoResearchClaw-Codex`

## 1. Purpose

AutoResearchClaw-Codex is a Codex-native research orchestration plugin derived
from AutoResearchClaw. Codex performs the reasoning and tool-using work inside
the active Codex session. The Python engine supplies deterministic workflow
services: project state, stage contracts, checkpoints, approvals, experiment
execution, artifact validation, and evaluation records.

The default path must not call an external LLM API or spawn another Codex,
Claude, Gemini, or ACP agent. This avoids nested model sessions, duplicate API
costs, and the loss of Codex's native search, filesystem, terminal, and document
tools.

## 2. Product identity

- Repository: `AutoResearchClaw-Codex`
- Display name: **AutoResearchClaw Codex**
- Python distribution: `researchclaw-codex`
- CLI command: `researchclaw-codex`
- Plugin ID: `autoresearchclaw-codex`
- User-facing invocation: `$researchclaw`

The README and package metadata will identify the project as a Codex-native
derivative of AutoResearchClaw. The upstream MIT license and required
attribution will be retained.

## 3. Design principles

1. Codex owns research reasoning and tool use.
2. Durable files, rather than conversation history, are the source of truth.
3. Every stage has explicit inputs, outputs, and acceptance criteria.
4. Human approval is required for consequential research and execution gates.
5. Generated experiment code is reviewed and isolated before execution.
6. Quality claims must retain evidence and be independently checkable.
7. The Codex-native core is rebuilt selectively alongside the upstream code.
8. An upstream module is removed only after its replacement passes equivalent
   contract and integration tests.
9. Evaluation data is captured from the first usable version.

## 4. System architecture

```text
Explicit user invocation
        |
        v
Codex research skill
  - interpret the request
  - prepare and perform stage work
  - use Codex tools
  - request approvals
        |
        v
Codex research engine
  - project and state management
  - stage contracts
  - checkpoints and resume
  - validation and approvals
        |
        v
Tool services
  - literature discovery and verification
  - isolated experiment execution
  - statistics and visualization
  - Markdown, BibTeX, and LaTeX export
```

The new implementation lives in `researchclaw/codex/` and
`researchclaw/core/`. Existing modules remain available during migration but
must not be imported by the new default path when they introduce LLM, ACP,
OpenClaw, or MetaClaw dependencies.

## 5. Plugin layout

```text
AutoResearchClaw-Codex/
├── .codex-plugin/
│   └── plugin.json
├── skills/
│   └── researchclaw/
│       ├── SKILL.md
│       └── references/
│           ├── stages.md
│           ├── approval-policy.md
│           └── evaluation-rubric.md
├── researchclaw/
│   ├── codex/
│   │   ├── cli.py
│   │   └── task_packet.py
│   └── core/
│       ├── project.py
│       ├── state.py
│       ├── contracts.py
│       ├── validation.py
│       ├── approval.py
│       └── execution.py
├── evaluation/
│   ├── benchmarks/
│   ├── rubrics/
│   └── reports/
└── tests/
    ├── unit/
    ├── contracts/
    ├── integration/
    └── evaluation/
```

## 6. Activation policy

The initial plugin activates only when the user explicitly invokes
`$researchclaw` or clearly requests ResearchClaw by name. Ordinary research
questions must not automatically create a 23-stage project.

Activation policy is isolated from the engine and may later support:

```yaml
activation:
  mode: explicit  # explicit | suggested | automatic
```

Changing activation mode must not modify existing project state or research
artifacts.

## 7. Research workflow

The upstream 23 stage identifiers and artifact contracts are retained as a
migration reference. They are presented to users as eight phase groups:

1. Research scoping
2. Literature discovery
3. Knowledge synthesis and hypothesis generation
4. Experiment design
5. Experiment execution and refinement
6. Analysis and research decision
7. Paper writing and review
8. Verification and export

Each stage follows this data flow:

```text
Prior artifacts + project configuration
        -> structured task packet
        -> Codex research and tool use
        -> structured artifacts
        -> deterministic validation
        -> checkpoint update
```

## 8. Project state and resume

Each research project stores a canonical state document. Conversation history
may help the current session but is never required to resume.

```json
{
  "schema_version": 1,
  "project_id": "rc-...",
  "current_stage": 5,
  "status": "awaiting_approval",
  "completed_stages": [1, 2, 3, 4],
  "next_action": "review_literature_shortlist",
  "execution_policy": "approval_required",
  "artifacts": {},
  "evaluation": {}
}
```

State writes are atomic. Each completed stage records artifact paths, content
hashes, validation results, timestamps, retry history, and a concise handoff
summary. A new Codex session can reconstruct the next action from these files.

## 9. Codex-to-engine interface

The engine never calls Codex. Codex drives the engine through small,
deterministic CLI operations:

```bash
researchclaw-codex init
researchclaw-codex status
researchclaw-codex stage prepare
researchclaw-codex stage validate
researchclaw-codex approve
researchclaw-codex experiment run
researchclaw-codex resume
researchclaw-codex export
researchclaw-codex evaluate
```

`stage prepare` emits a versioned task packet containing the objective,
required inputs, required outputs, acceptance criteria, allowed tool classes,
and approval requirements. Codex writes the requested artifacts and calls
`stage validate`. Validation advances state only when deterministic checks and
required approvals pass.

Qualitative judgments are stored as evidence-backed reports against versioned
rubrics. A bare model assertion cannot mark a stage complete.

## 10. Human approval gates

Three gates are mandatory in the initial version:

- Stage 5: approve the literature shortlist and exclusion rationale.
- Stage 9: approve hypotheses, experiment design, resource estimates, and
  execution risks.
- Stage 20: approve the final claims, evidence alignment, and quality report.

Approval records include the gate, artifact hashes, decision, timestamp, and
optional user notes. Changing an approved artifact invalidates its approval.

## 11. Experiment safety

Experiment execution has three phases:

1. **Plan:** Codex writes code, dependencies, data sources, expected resource
   use, filesystem access, and network requirements. No experiment runs.
2. **Validate:** static checks detect dangerous commands, broad filesystem
   mutation, secret access, unapproved subprocesses, and network use.
3. **Execute:** after explicit approval, run with limits and capture a complete
   provenance record.

Docker is the preferred isolation boundary. A project-specific Python virtual
environment may be used when Docker is unavailable, but the interface must
state that a virtual environment isolates dependencies, not operating-system
access.

Defaults:

- network disabled during experiment execution;
- only the project artifact directory is writable;
- explicit time, memory, CPU, and iteration limits;
- dependency installation and data download require declared approval;
- automatic execution can be enabled only per project, never globally by
  accident.

Execution records include commands, source hashes, dependency lock data, input
data hashes, environment and hardware information, stdout/stderr, exit status,
timing, and result artifacts.

## 12. Error model

Errors use three operator-facing classes:

- `retryable`: a transient operation may be retried without changing the plan;
- `needs_revision`: an artifact, experiment, or premise must be changed;
- `blocked`: user authority, data, credentials, or an external environment is
  required.

Every failure records its cause, attempt number, relevant artifact hashes, and
recommended next action. Repeating the same failure beyond the configured
limit stops automatic retry and surfaces the evidence to the user.

## 13. Testing strategy

Four test layers protect the migration:

1. Unit tests for state transitions, schemas, checkpoints, paths, approvals,
   and execution policies.
2. Contract tests for the inputs, outputs, and completion rules of all 23
   stages. The same contract suite is used before and after module migration.
3. Integration tests for init, prepare, validate, approve, resume, experiment
   execution, and cross-session recovery.
4. End-to-end evaluations on fixed research tasks, including comparison with
   manual workflows and the installed `academic-research-suite` where a fair
   comparison is possible.

## 14. Evaluation design

Evaluation is multidimensional rather than a single self-reported score.

| Dimension | Example measures |
| --- | --- |
| Factuality | Real-paper rate; DOI, title, and author agreement |
| Grounding | Proportion of material claims linked to evidence |
| Research quality | Testable hypotheses; protocol defects and leakage |
| Reproducibility | Clean-environment rerun success rate |
| Statistical validity | Test-selection errors and unsupported conclusions |
| Efficiency | Time, retries, and user interventions |
| Deliverable quality | Rubric scores and human revision volume |
| Reliability | Stage completion and resume success rates |

Machine-checkable measures use code and authoritative external sources.
Qualitative measures use fixed, versioned rubrics and retain both human and
Codex ratings so disagreement can be studied.

The initial benchmark set will eventually include:

- a public-data materials/AI experiment;
- a systematic literature review without experiment execution;
- a small statistical or machine-learning reproduction task.

Exact benchmark topics and evaluator composition are deferred until the core
workflow is usable.

## 15. Initial materials/AI profile

The core remains domain-general. The first bundled profile specializes the
workflow for materials science and AI, including terminology, common public
data sources, leakage checks, baseline expectations, materials-property
metrics, and evidence conventions. Domain rules extend stage task packets and
validation without forking the core state machine.

## 16. First-version scope

Included:

- installable Codex plugin with explicit activation;
- project creation and status inspection;
- 23 stage contracts grouped into eight user-facing phases;
- task-packet generation and artifact validation;
- atomic checkpoints and cross-session resume;
- three approval gates;
- experiment plans, risk review, and approved local Python execution;
- Markdown, JSON, and BibTeX artifact management;
- evaluation event capture;
- a materials/AI default profile.

Deferred:

- unattended end-to-end execution;
- SSH, remote GPU, and cloud execution;
- voice, messaging, and web dashboards;
- multi-model debate or reviewer calls;
- self-evolution and automatically learned skills;
- comprehensive conference-format export;
- broad deletion of upstream modules.

## 17. Migration and deletion policy

Development begins in the new `core/` and `codex/` packages. A migration unit
is complete only when:

1. its public behavior is expressed in tests;
2. the Codex-native replacement passes unit, contract, and relevant integration
   tests;
3. the new default path has no dependency on the old implementation;
4. retained functionality and attribution are documented.

Deletion happens in later, reviewable changes. The first version does not
delete broad upstream subsystems merely to reduce file count.

## 18. Success criteria for the first milestone

A milestone is successful when a user can explicitly invoke the plugin, create
a research project, complete at least the scoping and literature phases, stop
at the literature approval gate, close the session, resume from durable state
in a new session, and produce a validation and evaluation record without an
external LLM API key or a nested agent process.
