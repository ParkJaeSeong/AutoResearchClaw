# B05 implementation report

Scope: native collect/extract registration, supplied source/provenance objects,
independent source-check setup and observations, pure check/current-evidence
projections. Commands expose only m1.evidence.assign and m1.evidence.observe in
addition to the bounded existing node registry. A05 results and A04 resolutions
remain separate explicit commands. No CLI/UI/host execution or approval producer
was added.

Contract: docs/superpowers/specs/research-governance/m1-evidence-inputs.md.
The parent approved the closed schema before implementation. Raw UTF-8 captures
are supplied bytes; recorded access and origin labels are declarations. Unicode
codepoint spans and observed source text remain separate from extracted text and
interpretation. B01 source/dependency records derive from actual native source
objects after registration, preserving unavailable and unknown origins.

Readiness requires the exact current approved screen, complete kept-source
coverage, native A05 source_check results carrying independent native comparison
outputs, and independent A04 resolutions. A mismatch produces a separate explicit
Issue/event plan, never a vote or automatic resolution. Unsupported/inconclusive
checks and unavailable captures remain gaps. Old mismatches must be published
before replacement. Stale stage refs are withheld while replacement can repair
obsolete inputs; prior native publication obligations remain inspectable.

RED: the initial focused file reported 11 errors at collect registration with
m1_node_invalid, the intended missing feature. A separate native stale-repair
regression failed with issue_reference_stale before the projection/lineage fix.
GREEN: final focused result recorded below. Tests include complete native
collect/check/extract/check, supported-result mismatch rejection, abstract versus
full-text rejection and HEAD preservation, independent actors, generic-result
insufficiency, inconclusive gaps, exact source/corpus coverage and rejection,
unavailable/unknown source handling, publication obligations, stale-input repair,
and immutable original source bytes.

The parent ruled against expanding superseded policy. An additional real-command
regression confirms a prior inconclusive Issue can move checking→open, bind a
new A05 Verification to replacement evidence under the original criterion, then
receive a new result and independent A04 resolution. Original Issue/result bytes
remain intact. This required no A04/A05 policy changes or automatic resolution.

All fixtures declare synthetic captures/actors/authority. These tests establish
policy, reference and literal-byte behavior, not source authenticity, actual
network access or scientific correctness. Independent review and broader final
integration verification belong to the parent task.

Final focused verification: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_evidence.py -q` — **14 passed in 99.25s**. `git diff --check` passed. No broad suite was run.
