# U1 M1 public view and CLI

`build_view(root, head_id=None)` verifies current committed ancestry once, chooses
its exact requested ancestor, and projects that one snapshot. A hash merely
present under commits is not selectable. No read changes HEAD, source roots or
object bytes. `current_head_id` identifies latest while `head_id` remains pinned.
All arrays below are explicit allowlists, never generic state/events inventories.

Top level retains schema_version, workflow_version, head_id, project_id,
content_origin, object_count, event_count and the existing optional `import`
summary. Additions are:

- current_head_id; project `{id,topic,content_origin}`.
- milestones `[{id:'M1',status:'active'},{id:'M2',status:'unavailable'},
  {id:'M3',status:'unavailable'}]`. Unavailable does not mean completed.
- heads `[{head_id,parent_head_id,selected}]`, only selected ancestry.
- nodes: nine entries in scope/questions/search/screen/collect/extract/synthesize/
  hypothesize/review order, each `{id,label,status,current_revision_id,
  revision_ids,reason_codes,required_actions,next_node}`. status is not_started,
  awaiting_input, stale or ready. Handoff is a separate panel / derived tenth
  display step, not an invented native node.
- revisions `[{record,ref,artifact_id,current,previous_ref}]`. record is exact
  registered native node content; previous_ref is decoded previous_ref_key for
  display. Revision order follows actual native registration events.
- transitions `[{head_id,from_node,to_node,revision_id,attempt}]`, generated only
  by native node registration; a same-node revision remains a same-node move.
- councils `[{id,session_id,node,attempt,phase,required_roles,submitted_counts,
  input_binding,authors,participants,disclosed_initials,disclosed_responses,
  disclosed_finals,isolation_level,identity_provenance,content_origin}]`.
  authors are assignment records; participants add council_role. Counts are
  aggregate phase progress. Disclosed arrays use B02 `{submission_ref,submission}`
  entries. There is no public own_submissions. Host/model fields are the supplied
  labels on disclosed submissions, not authenticated host isolation.
- issues `[{record,ref,artifact_id,status,imported_pending,history,import_context}]`.
  History entries are `{record,ref,head_id}` from authentic native IssueEvents,
  never issue_states cache. A03 public imported projections stay pending_policy_
  revalidation until native events; an unmaterialized import has null raw ref.
- verifications, results, source_checks, approvals, dependencies are explicit
  `{record,ref,artifact_id,kind}` entries. kind names the registered collection.
- handoffs `[{record,ref,artifact_id,assessment}]` with actual handoff_status.
- evidence is B05 current_evidence, corpus is B04 corpus_status, accounting is
  native accounting_status, or null when its prerequisites are absent. Actual
  reason_codes/required_actions remain separate from presence of records.
- artifacts `[{id,ref,label,media_type,raw_url}]` is the only raw allowlist.
  IDs are opaque `a-...`; URLs include the selected `?head=...`.
- reason_codes and required_actions aggregate public prerequisite limitations.

Undisclosed submission/embedded proposal/position IDs, event IDs and object hashes
are excluded, including nested dependency/observation/raw paths. Private objects,
archive bodies, generic store snapshots and collection containers are not raw
roots. Raw requests recompute the server-side selected-head allowlist; a forged
projection item, arbitrary digest, archive alias or filesystem path grants no
access. Foreign imported target metadata grants no raw archive access.

Read-only viewer: `research view ROOT --host 127.0.0.1 --port 0` prints its URL.
GET `/api/view?head=HEAD` and `/api/artifacts/OPAQUE_ID?head=HEAD` support pinning;
omitting head selects latest. Static allowlist is `/`, `/index.html`, `/app.js`,
`/graph.js`, `/detail.js`, `/timeline.js`, `/trace.js`, `/live.js`, `/styles.css` under research_ui. Only GET is
accepted; exact loopback Host, same-origin checks and no-store headers apply.
Existing m1 viewer/assets/routes are unchanged. U2 owns research_ui files.

Public CLI examples (the executable may be `.venv/bin/researchclaw-codex`):

```sh
researchclaw-codex research inspect ROOT --head HEAD --json
researchclaw-codex research packet ROOT --assignment ASSIGNMENT_ID --json
researchclaw-codex research apply ROOT --operation council.submit --payload submission.json --expected-head HEAD --command-id UNIQUE_ID --json
researchclaw-codex research view ROOT --port 0
```

`--payload` is a UTF-8 JSON file containing the exact registered operation payload;
duplicate keys are rejected. The operation must be in the public command registry.
Apply returns only version/id/head_id/operation metadata (including replay's
original receipt). Packet uses B02's selected reviewer projection and may contain
that reviewer's own private submissions; it is not served through public HTTP.
These commands do not create a provider, authenticate actors or grant approval.
