# Stage 9 — Validation Design

Use this reference only when the prepared packet's `stage_id` is `9`. The
upstream-compatible stage name remains `experiment_design`, while the supported
artifact is a broader validation design. Read the complete validated
`hypotheses/candidates.jsonl` and write only `experiment/design.json`. Do not
collect new evidence, generate implementation code, or execute the design.

Write one closed JSON object with exactly these top-level fields:

- `schema_version`: integer `1`.
- `project_id`: exact durable project ID.
- `validation_type`: `policy_evidence`, `computational`, or `laboratory`.
- `hypothesis_ids`: non-empty list of IDs present in the stage-8 artifact.
- `title`, `objective`: non-empty strings.
- `validation_questions`, `comparators`, `success_criteria`,
  `failure_criteria`, `bias_controls`: non-empty string lists.
- `evidence_sources`: non-empty list of objects with exactly `category`,
  `scope`, `inclusion_criteria`, `exclusion_criteria`, and `collection_method`.
  Criteria are string lists; `exclusion_criteria` may be empty.
- `metrics`: non-empty list of objects with exactly `name`, `definition`,
  `target`, `direction`, and `unit`. Every field is non-empty and `target`
  contains a numeric threshold, never a placeholder.
- `resources`: object with exactly `people`, `data`, `tools`, `duration`, and
  `budget`. The first three are non-empty string lists; the last two are
  non-empty strings.
- `reproducibility`: object with exactly `protocol_version`, `data_provenance`,
  `analysis_plan`, and `audit_trail`, all non-empty strings.
- `risks`: non-empty list of objects with exactly `risk` and `mitigation`.
- `method`: the exact type-specific object below.

Type-specific `method` fields:

| `validation_type` | Exact fields |
| --- | --- |
| `policy_evidence` | `data_sources` and `stakeholder_groups` as non-empty string lists; non-empty `candidate_selection`, `scoring_model`, `sensitivity_analysis`, and `conflict_of_interest_plan` strings |
| `computational` | `datasets` and `baselines` as non-empty string lists; `split_strategy` as a closed object containing only non-empty `description` and `isolation_key` strings; non-empty `evaluation_protocol` string |
| `laboratory` | `materials` and `controls` as non-empty string lists; non-empty `procedure` and `safety` strings |

Choose the validation type that directly tests the referenced hypotheses.
Policy and technology-planning questions are first-class `policy_evidence`
work; do not force them into a laboratory framing. Make success and failure
criteria mutually decision-relevant, state feasible resources, and expose
bias, conflicts, controls, provenance, and auditability.

Run `researchclaw-codex stage validate ROOT --json` and revise only the
declared output until validation succeeds. A valid stage-9 artifact is a human
gate: present the design and validation result, then request an explicit
approve or reject decision. A general instruction to continue is not approval.
After the user decides, record that decision with `approve`, then run `resume`.
For an approved `computational` design, prepare Stage 10 and follow
[computational-package.md](computational-package.md) to author and statically
validate the declared package without execution. `policy_evidence` and
`laboratory` designs remain unsupported at Stage 10; report that boundary and
stop. Do not execute the design.
