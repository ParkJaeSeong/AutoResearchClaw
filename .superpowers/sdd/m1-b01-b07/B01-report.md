# B01 implementation report

Base: a4388da. Owned scope: evidence_origins.py, test_evidence_origins.py,
evidence-origin-inputs.md and this report. No shared code, commands, producer,
CLI/UI or host execution changed.

The concise input contract was written before implementation. A backed explicit
evidence_sources map holds closed common-envelope/source_ref selections. Missing
selection differs from verified empty selection. Exact current cited versions
are deduplicated by project/artifact/digest; historical upstream versions remain
exact. A08's resolver handles raw aliases and typed UUIDs/current collisions.
Dependency DAG validation is local and narrow to avoid requiring unrelated
approval authority checks from plan_revalidation.

Upstream Dependency origin_group_id labels form deterministic declared groups.
Three papers sharing one dataset group yield source_count 3 and origin_group_count
1. Repeated source registrations/heads/links do not inflate either count. Missing
provenance or any upstream unknown label retains an unknown source entry even if
downstream labels are known. Known groups and unknown status may coexist; the
projection exposes no independent-evidence count or independence certificate.

Focused TDD evidence:

- Initial RED: 16 failures from the missing module after valid fixture creation.
- Initial GREEN: 16 passed (0.40s).
- Closed-envelope regression RED: three extra top-level reference fields were
  hidden by the envelope validation adapter (3 failed, 16 passed, 0.72s).
  These extra fields are now explicitly rejected before adaptation.
- Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_evidence_origins.py -q`:
  19 passed (0.44s). `git diff --check`: clean.

Tests exercise current source selection versus historical upstream, unknown
ancestry, duplicate source/group links, missing/empty prerequisites, rejected
closed/unbacked records, unknown references, cycles, typed UUID collisions, and
unrelated unbacked approval records. Accepted and rejected calls assert snapshot,
HEAD and all prior object bytes remain unchanged.

Only synthetic structural checks ran; no actual research/source-authenticity/
scientific-diversity verification, host action, broad suite or user acceptance
was performed. Parent owns independent review, shared task-board updates and
the later B02–B07 work. No claim that the whole M1 plan is complete.
