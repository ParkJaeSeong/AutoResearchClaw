# B04 search, screening and corpus authority

B04 extends the bounded m1.node.register producer with search and screen.
Search input_refs is exactly `{scope, questions}`; screen input_refs is exactly
`{scope, questions, search}`. All are exact current reviewed native nodes.
Search content is exactly `{queries, sources, inclusion_criteria,
exclusion_criteria}` with nonempty lists of nonempty text.

Screen content is exactly `{search_log, candidates, decisions}`. Each search_log
row is closed `{search_id, query, source, searched_at, result_count}`: unique
nonempty ID, query/source from the declared search plan, ISO timestamp, and
nonnegative integer count. Candidates have exactly `{source_id, title, doi,
arxiv_id, url, source_type, access_status, search_ids, stance}`. IDs/titles/types
are nonempty text; DOI/arXiv/URL are nullable text with at least one nonempty
identifier. Access is full_text/abstract/metadata_only/unavailable; search_ids
is a nonempty unique list of existing log IDs. Stance is the declared
support/oppose/neutral/unknown relation to the research question, not a scientific
classification certificate. Duplicate source IDs are rejected.

Decisions are closed `{source_id, decision, reason}` and account for every
candidate exactly once with include/exclude and a nonempty reason. At least one
candidate is kept. A derived complete shortlist preserves candidate metadata;
legacy content-only search/collection/screening validators check log provenance,
counts and complete selection without touching the old M1 store.

An excluded candidate declared oppose requires an actual native nonoptional
source Issue targeted at the exact current screen ref, node blocking_scope
screen, and origin.local_issue_id `opposing-exclusion/{source_id}`. Native status
governs blocking; publication is not resolution. Council votes cannot substitute
for recording or handling this omission. B02 proposals use the existing explicit
issue.event publication path.

The complete current screen node ref is the corpus binding: its immutable bytes
contain all candidates, search logs and kept/excluded decisions, and exact input
refs bind scope/questions/search. `current_corpus(snapshot)` returns
`{corpus_ref, scope_refs, kept_sources}`. scope_refs is the canonically sorted set
of the four full references scope/questions/search/screen. Kept sources are
sorted by source_id; they are selected metadata, not observed original texts.
This component and its full input chain must feed later collect/extract and
hypothesis review; a caller cannot choose an unrelated approved component.

`m1.corpus.decide` has exactly `{receipt_id, corpus_ref, decision, note}`. IDs are
fresh UUIDs; decision is approve/reject; note is nonempty. This dedicated API
records an explicit user-declared decision, never a council recommendation.
The trusted caller must supply an actual user decision; B04 tests invoke only
synthetic declarations. Authority is declared, not authenticated. Approval
requires the current reviewed screen and complete corpus; rejection may revoke
an exact historical native screen without requiring that old review to pass.

The native receipt uses A07's exact `{id, project_id, producer_id, decision,
binding, scope_refs}` with producer_id `user`, decision approved/rejected and
computed complete binding/scope. Note and actor=user remain in the native event.
Latest native decision for the same immutable corpus controls. Reject revises
matching current ApprovalBinding validity to revoked while retaining old bytes.
Neither imported receipts nor unrelated generic receipts count as native user
corpus decisions.

`m1.corpus.bind` has exactly `{binding_id, event_id, receipt_ref}`. It consumes the
exact prior native latest-approved receipt and current reviewed corpus, deriving
a schema-valid ApprovalBinding with existing_receipt_ref, complete binding/scope,
validity valid, producer_id m1-corpus-approval-adapter and declared_only provenance.
The separate command satisfies A07's receipt-before-binding chronology. It asks
for no second human approval and cannot create authority from an absent receipt.
Revoked bindings are never revived; renewed approval requires a new binding.

`corpus_status(snapshot)` adds current approval_ref (or null), approved, and
reason_codes to current_corpus. `prepare_search_council(snapshot,node_id=...)`
uses native node review for search/screen. Screen additionally returns
review_ready, corpus_ref, approval_ref, approved, and refuses extraction readiness
without a current native corpus binding. This is a pure projection, not execution.
Changed corpus or upstream bytes cannot reuse old approval.

B05 owns the subsequent bounded collected-source/observation producer and derives
B01 evidence_sources/dependencies from the kept native source inputs, preserving
unknown origins. B04 creates no fixture-only provenance map and claims no source
body observation, confidence, statistical independence or actual research success.
