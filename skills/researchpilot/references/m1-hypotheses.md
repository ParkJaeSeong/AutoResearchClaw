# M1 hypotheses and independent review

Use this contract only for the `m1-graph-v1` workflow. Existing hypothesis generation rules remain unchanged for legacy projects.

Author `hypotheses/hypotheses.json` and the accompanying readable `hypotheses/hypotheses.md` in the packet work directory. The JSON is authoritative. Read only packet-bound evidence: the selected synthesis, the extraction version that synthesis consumed, and prior registered hypothesis revisions when present. Do not substitute a newer extraction or an edited working draft.

## Record contract

```json
{
  "schema_version": 1,
  "hypotheses": [
    {
      "id": "H1",
      "revision": 1,
      "parent_revision": null,
      "author_assignment_id": "author-assignment-1",
      "change_reason": null,
      "statement": "The observed difference depends on context.",
      "claim_refs": ["C1"],
      "gap_refs": [],
      "predicted_observation": "The difference diminishes under comparable conditions.",
      "falsification_condition": "The difference persists under comparable conditions.",
      "alternatives": ["Selection effects explain the observation."],
      "feasibility_notes": "Comparable observations appear accessible; access remains unverified.",
      "open_design_questions": ["Which conditions and measurements should M2 use?"],
      "disposition": "draft"
    }
  ]
}
```

This example is synthetic and assumes `C1` exists in the exact bound extraction. All displayed fields are required. ID, author ID, statement, prediction, falsification condition and feasibility notes are nonempty strings. Revision is a positive integer, not a boolean. Reference lists contain unique nonempty IDs resolving against the bound extraction or synthesis gaps. A candidate requires at least one claim or gap reference; gap references alone do not establish scientific support, especially when the synthesis marks a gap as an unverified question.

`alternatives` and `open_design_questions` are lists of nonempty strings. They may be empty when there is nothing justified to record. Do not invent a count of candidates, a numerical improvement, or a mandatory opposite hypothesis. A single evidence-linked hypothesis and qualitative prediction are allowed. Preserve plausible competing explanations and limits; put unresolved measurements, effect sizes, comparisons and experimental details in `open_design_questions` for M2.

Allowed dispositions are `draft`, `revise`, `selected`, `rejected`, and `deferred`. `selected` is a recorded disposition, not proof that a hypothesis is true or permission to advance the graph. An initial no-candidate outcome can be recorded as:

```json
{"schema_version": 1, "hypotheses": [], "no_hypotheses_reason": "Current evidence does not support a testable proposal."}
```

A no-candidate record is not an M1 handoff. Later records must still preserve previously registered hypotheses; use later dispositions and reasons to retain rejected or deferred history.

## Revisions

The envelope is cumulative: copy every previously registered record exactly, including metadata, then append each new record. Do not change or omit old revisions. Each existing hypothesis may add its next revision only: `revision = parent_revision + 1`, with the parent present in the bound prior registered envelope. A parent copied only into the new draft is insufficient. A new ID begins at revision 1 with explicit null `parent_revision` and `change_reason`.

For revision 2 and later, `change_reason` must be a nonempty explanation of the change, and `author_assignment_id` preserves the initial author ID. A text/hash change without a reason does not qualify. Changed historical content must become a new revision. Old records retain their historical evidence binding; new records must resolve against the current packet evidence. Immutable registered artifact bytes and producer input references preserve those earlier bindings.

## Review boundaries

The pure `can_review(author_assignment_id=..., reviewer_assignment_id=...)` gate only checks that the two IDs differ. Nonempty author IDs are checked by record validation. ID strings, role names or model labels do not authenticate a person, worker, host, or independent execution. Assignment provenance and authority checks belong to the independent review engine, not this validator.

Review the candidate through three distinct questions:

- **Domain:** What contribution does the hypothesis make, and which bound evidence supports or limits it?
- **Methodology:** Which observation distinguishes it from alternatives, and what falsification condition would reject it? Which design questions remain for M2?
- **Critical/reproducibility:** Which competing explanation remains plausible, and under which conditions does the hypothesis fail? Is the evidence reproducible, including contradictory evidence?

The coordinator organizes questions and preserves disagreement without voting or writing others' positions. Registration validates structure and references and leaves the attempt `review_pending`, with scientific validation `not_performed`. It does not run reviewers, resolve objections, approve research, advance the graph, or execute M2 experiments.
