# U2 M1 UI implementation

Implemented the approved M1-only screen as a separate vanilla-JS research_ui
entry. Existing m1_ui, U1 views/server/CLI, and the live native project were not
modified. New modules cover the nine-node map and actual registration moves,
exact revision/parent comparisons, phase-disclosed council dialogue, global Issue
timeline, evidence/source/verification details, corpus approvals and handoffs.
M2/M3 remain explicitly unavailable. Council ready opinions are labeled as
opinions; structural readiness, publication, acceptance, transfer, and resolution
remain distinct. Imported pending/unknown states do not become completed.

Rendering uses textContent and native DOM elements. Raw links require an exact
four-field reference and a provided opaque selected-HEAD allowlist URL; missing
versions remain missing. External links accept only HTTP(S). Scientific prose is
not translated as an enum. The only fetch is the read-only public view GET.
Next-step guidance uses existing inspect/packet/apply CLI syntax and placeholders;
there are no execution, provider, or approval buttons.

Serial polling deduplicates same-HEAD updates. HEAD selection starts a new request
generation and rejects late results from prior modes. Past views stay pinned;
disconnections preserve the last complete screen. New renders are built off-DOM
before replacing the prior view. Selection, open details, focus, window scroll,
and detail scroll are restored. Native tab buttons support arrows/Home/End;
CSS supplies responsive 360/736 layouts, visible focus and light/dark/system modes.

RED: `node --test tests/codex_native/research_graph/test_research_ui.mjs`
reported 7 expected missing-function failures. Initial GREEN 7/7; expanded
focused GREEN 10/10. Final read-only native smoke:
`RESEARCH_UI_VIEW=/tmp/u2-native-view.json node --test tests/codex_native/research_graph/test_research_ui.mjs`
passed 11/11 in 65.42 ms. The optional native input was fetched only through
GET /api/view on port 8767, at HEAD
8d9fc32dc27e9c06f067a5275ed8cb42b3d7d9a661ced2827624fa732d4dba91.
The DOM harness rendered all 9 revisions, 63 disclosed statements and 11 Issues,
including all five detail panels. This checks public data/display linkage and
inert text, not browser layout or actual role independence.

`uv build --wheel --out-dir /tmp/research-ui-wheel-check` succeeded. ZIP inventory
confirmed all 9 research_ui files (8 served assets plus package.json); existing
Hatch package selection includes them, so no pyproject change was necessary.
`git diff --check` passed. No broad Python or predecessor suite was run.

Root's actual Chrome attempt currently reports ERR_BLOCKED_BY_CLIENT and the
in-app browser is unavailable. Therefore visual acceptance at 360/736, actual
keyboard behavior, theme contrast and browser scroll restoration remain pending;
DOM tests do not replace those checks. Root owns browser acceptance, independent
review, actual test continuation, and final integration/preservation checks.
