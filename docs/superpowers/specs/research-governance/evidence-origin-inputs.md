# B01 evidence origin inputs

`group_origins(commands.read_policy_snapshot(root))` is a pure M1 provenance
projection. It consumes verified history and bytes, creates no prerequisites or
commands, and preserves HEAD and old objects. It does not require approvals.

`state.evidence_sources` must be explicitly present as a UUID-keyed map. Missing
means `evidence_sources_missing`; an explicitly empty map is a verified empty
source selection. Each canonically object-backed record contains exactly the
common research-graph envelope plus `source_ref`, a four-field SnapshotRef of a
cited M1 item. The common envelope includes version/project/id/event/producer,
content_origin, provenance_status and observation_refs. Source and observation
references must resolve and be current. Missing future source producers fail
closed; B01 does not fabricate a source registry.

Source count is the number of distinct `(project_id, artifact_id, sha256)` cited
versions, never the number of registration UUIDs or ancestor heads. Historical
source selection is rejected as `evidence_source_stale`. Exact reference and
typed UUID resolution reuse A08's resolver, including current typed-ID ambiguity
checks. Original raw object aliases and namespaced typed objects are supported.

Backed `state.dependencies` records follow A08's fixed upstream `from_ref` →
dependent `to_ref` convention for all four relation labels. All dependency
records/endpoints/observations are checked and the full DAG must be acyclic.
Historical upstream versions remain exact; they are never substituted with
newer bytes. Approval records, receipts and authority are not consulted.

For each cited source, traverse every upstream dependency and collect its declared
`origin_group_id`. A shared dataset upstream of three papers with one declared
group yields `source_count: 3` and `origin_group_count: 1`. Multiple links with
the same group do not increase the group count. Group labels describe recorded
provenance; distinct labels are not proof of independent datasets or evidence.

No incoming dependency for a cited source, or any upstream edge labelled exactly
`unknown`, leaves that source in `unknown_refs`. A downstream known label cannot
erase unknown ancestry. Known group memberships may coexist with unknown status.
An upstream terminal artifact does not itself add uncertainty when its outgoing
edge explicitly declares an origin group. Unknown is never a known group or an
independent-evidence count.

The returned closed projection contains `source_count`, `origin_group_count`,
`origin_groups` (sorted `{origin_group_id, source_refs}` entries for known labels),
`unknown_refs`, and `reason_codes` (`[origin_unknown]` if uncertainty remains,
otherwise empty). References use the smallest canonical full source reference
for each immutable version and are canonically sorted. No statistical or
scientific independence count, approval status or readiness claim is produced.

Invalid shapes/backing/references raise ValueError. B01 adds
`evidence_sources_missing`, `evidence_sources_invalid`, `evidence_source_invalid`,
and `evidence_source_stale`; existing A08 reference/cycle and `_Inputs` backing
errors remain explicit. Synthetic fixture success checks recorded structure,
not actual research validity, source authenticity or scientific diversity.
