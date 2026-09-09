# U1 M1 view / CLI / read-only server

Scope is the M1 slice of E01 at base c9303c4. The parent approved the compact
schema before implementation; exact keys and CLI/API syntax are documented in
`docs/superpowers/specs/research-governance/m1-view-inputs.md`. U2 owns the new
research_ui assets; no UI or provider was implemented here. Existing legacy m1
routes and assets are unchanged, and M2/M3 remain explicitly unavailable.

Implemented build_view(root, head_id=None), selected-head read_artifact, the
loopback GET-only research_viewer and research inspect --head/view/apply/packet.
Inspect retains old metadata aliases and the safe import summary. CLI apply
accepts only registered operations and closed JSON files through apply_command,
returning minimal receipt metadata. Packet uses the selected reviewer B02
projection and is not available through public HTTP.

One request verifies current ancestry once and hydrates the selected prefix.
Public collections expose native node revisions/moves, phase-disclosed councils,
actor labels, native IssueEvent history and imported pending context, source
checks, exact evidence/corpus/accounting assessments, approvals and handoffs.
Undisclosed IDs/event IDs/hashes and nested private reference paths are excluded.
No generic state, event stream, object inventory or archive body is exported.
Opaque raw routes recompute the selected-head public allowlist; caller-invented
projection items, digests, filesystem paths and orphan commits grant no access.

RED evidence:
- View boundary tests initially failed because research_graph.views was absent.
- Server boundary tests initially failed because research_viewer was absent.
- The parent-requested timeline.js/trace.js route test failed404 before those two
  explicit static entries were added.

GREEN evidence:
- `.venv/bin/python -m pytest tests/codex_native/research_graph/test_views.py tests/codex_native/research_graph/test_viewer.py tests/codex_native/research_graph/test_cli.py -q -x`
  → **15 passed in 83.57s**. Includes one cached native nine-node M1 chain with
  B05 source checks, explicit corpus approval, B07 publication/acceptance and
  source-byte/HEAD preservation, plus focused privacy and historical boundaries.
- After the two explicit U2 static routes:
  `.venv/bin/python -m pytest tests/codex_native/research_graph/test_viewer.py tests/codex_native/research_graph/test_cli.py -q`
  → **6 passed in 0.78s**.
- `git diff --check` and staged diff check passed.

No broad suite, actual model execution or browser acceptance was performed in
this subtask. Native fixtures declare synthetic source/actor/authority data;
recorded host/model labels are not host authentication. Parent owns independent
review, U2 integration, actual-host U3 and final U4 checks.
