# B04 implementation report

Base: approved B03 1b06db7. Scope: m1_search.py, bounded m1_nodes extensions,
narrow commands registration/hydration, focused test_m1_search.py, search/node
input supplements and this report. No B05 producer, broad suite, CLI/UI, source
access or actual user authority invocation was performed.

Concrete closed search/screen/corpus contracts were sent to root and rg_a07 and
written before implementation. Native search requires reviewed current scope and
questions. Native screen binds those plus reviewed search; closed logs/candidates/
complete decisions use the legacy content-only validators without old-store
writes. Search IDs refer to actual logged declarations. Excluding a declared
opposing source requires a native nonoptional source Issue with exact screen
target and source-specific local ID; publication is not resolution.

The full current screen bytes form the complete corpus binding, covering all
candidate metadata, logs and kept/excluded decisions plus exact scope/questions/
search input refs. Public current_corpus and corpus_status expose derived kept
sources and the canonical four-reference approval scope for B05–B07 connectivity.

The dedicated m1.corpus.decide operation records only explicit user-declared
approve/reject decisions with note in a native event and a closed prior-authority
receipt. m1.corpus.bind separately consumes the latest native approved receipt
and derives an A07 ApprovalBinding, preserving receipt-before-binding chronology.
No council recommendation or imported receipt grants corpus authority. Latest
same-corpus rejection writes revoked current binding records while retaining old
bytes; renewal needs a new derived binding. Exact historical corpus rejection
remains possible after replacement without making its old review ready.

Both new commands are synchronized in dispatch and verified snapshot hydration.
Pure screen projection separates review_ready from approved and waits without a
current corpus binding. B05 will derive B01 source/provenance records from actual
kept native source/observation inputs; no fixture-only production map was added.

Focused verification:

- Corrected a test helper package import before policy RED. Initial policy RED
  reached unsupported native search registration: 1 failed and 11 dependent
  cached-baseline setup errors. Fixture node content matched the frozen new
  contract; the implementation lacked those node types.
- Initial GREEN: 12 passed (30.34s). The module builds real scope/questions/search/
  screen councils once, then copies the immutable native baseline per test.
- Malformed receipt collection regression RED: 1 failed, 14 deselected (7.36s),
  from typed lookup on a list. Reference-collection preflight now rejects this
  with dependency_collection_invalid and unchanged HEAD.
- Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_search.py -q`:
  15 passed (34.86s). Checks include real user-declared receipt/binding chronology,
  revocation, renewal, changed corpus, historical revoke, replay/conflict,
  opposing exclusion/native issue handling, provenance refusal and imported
  receipt refusal. `git diff --check`: clean.

All declarations/approvals in these tests are synthetic. Identity and authority
remain declared, not authenticated; no real research, source-body observation,
scientific independence or user acceptance is claimed. Parent owns independent
review, acceptance and later full related regression after B07.
