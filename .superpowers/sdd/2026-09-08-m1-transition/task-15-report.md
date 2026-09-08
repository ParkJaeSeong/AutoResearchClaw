# Task 15 — Read-only registered and historical decision views

Implemented after independently approved Task 14 (`bad1104`). Worker changes
are limited to `researchclaw/core/m1/views.py`, `researchclaw/codex/m1_cli.py`,
`tests/codex_native/m1/test_views.py`, and this report. Root owns all UI/viewer
files, actual project, transcripts, acceptance exports and documentation. No
subagents were used and the actual project was not modified by this worker.

## Public contract

```python
from researchclaw.core.m1.views import build_view, find_decision, validate_view
view = build_view(root, head_id=None)
decision = find_decision(view, 'decision-live-r1')
validate_view(view)
```

```sh
researchclaw-codex m1 inspect ROOT --json
researchclaw-codex m1 inspect ROOT --head REACHABLE_COMMIT_ID --json
```

One verified committed ancestry selects the immutable `head_id`. Arbitrary
commit files and pre-publication orphan commits are rejected with
`m1_view_head_not_reachable`. Only the selected state's records and object
registry contribute display data. Each object is read once during ancestry
integrity verification and at most once for the cached projection; wait and
approval calculations reuse selected state and cached bytes. They never call
current-root resume/approval APIs or read HEAD again.

The shared extensible core is `schema_version`, `workflow_version`,
`data_origin`, `project`, `nodes`, `edges`, `attempts`, `artifacts`, `sessions`,
`issues`, `responses`, `decisions`, `approvals`, and `next_actions`. The same
`validate_view` checks the supplied demo and actual registered projections,
including core collection types, unique display IDs, and graph endpoints.
It validates the presentation contract, not scientific correctness. Registered
views use `data_origin:registered`; demo remains `data_origin:demo`. Both retain
`content_origin` independently. Synthetic registered research remains synthetic.

Extra top-level fields are `head_id`, `content_origin`, `current_node_id`,
`budget`, `budget_changes`, `transitions`, `return_context`, `wait_reasons`, and
`missing_references`. `budget` has the native exact fields `max_returns`,
`returns_used`, `remaining`, `exhausted`. `next_actions` contains
`{node_id,action,label,reason,wait_reasons}`; labels only expand workflow action
identifiers, and reasons preserve engine waits and recorded decision rationale.
No scientific title, summary or conclusion is generated. Project title is the
recorded topic and decision title falls back to its registered ID. Node labels
and responsibilities come from the fixed graph/role contracts; current node
and each latest attempt's actual status remain separate fields.

## Disclosure and exact relationships

Sessions retain assignments and only the canonical frozen `disclosed_initials`,
`disclosed_responses`, and `disclosed_final_positions` arrays. Undisclosed maps,
command receipts/events, object registries, allowed-evidence copies and replaced
initial bodies are not exported. Initial completeness is checked from the three
active assignments, including failed/replaced sessions; each assignment exposes
safe `initial_status:submitted|waiting|failed` metadata. A pending role's text
and submission/object hashes cannot leak through sessions or top-level issues.
The raw artifact allowlist consists only of selected `state.artifacts` entries;
council initial objects never acquire raw delivery permissions.

Issue IDs are `<escaped session>/issue/<escaped original ID>` and response IDs
are `<escaped session>/response/<escaped original ID>`. Every projected issue
and response retains `original_id` and `session_id`; nested issue/response links,
final dispositions, decision threads, related issues, blockers and transitions
are rewritten consistently. Role/host IDs, reasoning, recommendations, stance,
change rationales, evidence references, dissent and limitations remain recorded
values. Registration status and `host_provenance_status:not_observed` are separate
from stored `provenance_status:declared_only`. A declared host ID does not become
an independently verified worker execution.

Actual artifact records have `registered:true`, `projection:false`, their exact
ArtifactRef identity, and `kind:registered_artifact`. Their `content` is the first
4000 Unicode characters of the registered UTF-8 bytes. `content_truncated`,
`content_length`, and `content_status:utf8_preview|non_utf8` make the preview
boundary explicit. This is text, not a scientific summary or an execution sink.

Each cumulative hypothesis JSON record becomes a separate `kind:hypothesis`
projection identified by `<escaped source artifact>/hypothesis/<escaped H ID>/rN`.
It preserves every authored field and adds `hypothesis_id`, `original_id`,
`source_artifact_id`, `source_artifact_sha256`, and an exact `source_json_pointer`.
It has `registered:false`, `projection:true`, and no raw object SHA field. The
same revision appearing in multiple cumulative artifacts retains those distinct
source identities. Native `claim_refs` and `gap_refs` remain native claim/gap
IDs, not invented ArtifactRefs. The UI's raw source link must resolve the actual
`source_artifact_id`, never the semantic display ID.

Decision `hypothesis_versions` and disposition `hypothesis_version_id` bind the
exact revision in that session's pinned hypothesis artifact. A child is added
only through that decision's recorded return transition, the returned attempt's
actual output, and a matching hypothesis ID/parent revision. Unrelated latest
versions and future state cannot replace this connection. Issue
`target_version_ids` follow the same source binding. Decision `evidence_refs`
is the deduplicated union of already recorded citations in frozen decision
records; `response_ids` identifies the disclosed responses in that session.
Missing exact artifacts/versions produce explicit `missing_references` records
with `owner_id`, `reference_id`, and `reason`; no latest version is substituted.

## Verification

- Initial TDD RED: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_views.py -q` reported **10 failed in 11.05s** from the
  absent view API and inspect CLI. During GREEN, the tests exposed the missing
  convenience `decision.evidence_refs`; that is now derived only from existing
  citations. Two fixture corrections selected the role that actually raised
  an issue and bound its new-session copy to that session's allowed evidence.
- Cache regression RED: the focused `snapshot_reuses` case reported **1 failed,
  13 deselected in 11.31s** because existing resume helpers reread some objects
  four times. Snapshot-only wait calculations removed those repeated reads.
- Focused GREEN: **14 passed in 20.21s**, including read-only historical r1/current
  r2 links, exact source pointers, private pending/replaced initials, qualified
  IDs, one ancestry traversal, object caching, orphan rejection, historical
  approval/budget separation, missing references, shared demo validation and CLI.
- Final scoped regression: `.venv/bin/python -m pytest
  tests/codex_native/m1/test_views.py tests/codex_native/m1/test_m1_cli.py
  tests/codex_native/m1/test_resume.py -q` reported **31 passed in 43.59s**.
  Added checks preserve frozen role narrative and nested references, bound exact
  Unicode previews, and reject unrelated latest hypothesis substitution. No
  broad M1 baseline or full legacy suite was repeated.
- The duplicate-session test additionally registers the same short response ID
  in a second session and verifies distinct projected response and issue links;
  its focused follow-up result is recorded below.
- `compileall -q` for all three changed Python files and `git diff --check`
  completed without diagnostics. Root-owned files remain unstaged by this worker.

## Actual acceptance boundary

The runnable API and exact schema were sent to root before final verification,
so root could run the actual registered viewer while this worker finished the
bounded tests. Root owns exporting the actual selected and historical JSON,
checking the actual r1 decision/return and r2 initial wait in the browser, and
recording execution provenance. This implementation does not alter actual
reviewer reasoning or use the synthetic fixture as evidence of actual execution.

The duplicate issue/response session follow-up passed: `.venv/bin/python -m
pytest tests/codex_native/m1/test_views.py -k scoped_issue_ids -q` reported
**1 passed, 16 deselected in 13.56s**. Both same-short-ID response records
resolve only to the issue in their own session.
