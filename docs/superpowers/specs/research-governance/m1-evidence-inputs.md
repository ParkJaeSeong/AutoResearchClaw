# B05 supplied sources and independent checks

The bounded native node registry adds collect (input_refs exactly `{screen}`)
and extract (exactly `{screen, collect}`). Screen must be the same current native
complete corpus. Extraction additionally requires its current user approval and
completed independent collect check. These nodes use source checks, not councils.

Collect content is `{sources, limitations}`. Every kept source appears exactly
once as `{source_id, access_status, access_url, accessed_at, raw_text,
origin_group_id, origin_description, limitations}`. Access never exceeds screen's
declaration; accessed_at is ISO text. raw_text is supplied UTF-8 text, not proof
of network fetching or full-text authenticity. Unavailable requires null raw_text
and nonempty limitations. Other levels require nonempty text; abstract/metadata
access retains explicit limitations. Known origin labels require a supplied
description; unknown uses null description and never implies independence.

Registration stores exact raw text, source metadata and declared origin objects
under safe source-ID-derived aliases, preserving old object bytes. Metadata does
not contain a fabricated original for unavailable entries. No host_observed status
is inferred merely because bytes were supplied or loaded.

Extract content is `{claims, limitations}`. Claims are closed `{claim_id,
source_id, source_ref, locator, span_start, span_end, extracted_text, access_level,
interpretation, limitations}`. source_ref binds that kept source's exact collected
raw version. Access equals the recorded collected access level. Spans are Unicode codepoint
offsets `[start,end)` in the exact supplied text (not byte offsets); locator is a
recorded bibliographic label, not authenticated location truth. extracted_text
and interpretation remain separate from later observed text. Node limitations
are `{source_id, reason}` entries; each kept source without a claim needs an
explicit limitation. Unavailable sources never get fabricated claims.

`m1.evidence.assign` has exactly `{setup_id, node_ref, checker_assignment,
resolver_assignment}`. It registers only closed active M1 A04 owner/resolver
assignments with distinct actors independent of the node author, plus a backed
setup and budget snapshot derived from existing configured limits/counters/cost
state. Unknown observed cost stays unknown; this creates no execution permission.
One setup binds each exact node revision. Collect setup derives current B01
evidence_sources and versioned Dependency records from already native source and
origin object refs; known labels remain declared and unknown is preserved.

`prepare_evidence_check(snapshot,node_id=...)` is pure. It derives a deterministic
planned source-check Issue (an explicit verification question, not a claimed
error), fixed A05 Verification, and sequential command_plans for existing
issue.event/open, verification.prepare, and issue.event/checking. Each plan is
available only when its prior native prerequisite exists. The same node revision
cannot get fresh work IDs to erase its check history. Actual observation is
refused until this exact work is prepared and checking.

`m1.evidence.observe` has exactly `{observation}`: common envelope plus
`verification_ref, node_ref, checker_assignment_id, comparisons, limitations`.
Comparison fields are exactly `{item_id, source_ref, locator, span_start,
span_end, access_level, observed_text, interpretation}`. item_id is source_id for
collect or claim_id for extract. Every available source/claim is covered exactly
once. Observed text must equal the exact source span. Extract comparisons retain
the native claim's source, span, locator and access; extracted_text is read from
that claim, never from a checker-supplied replacement. Unavailable entries have
no invented comparisons and remain explicit gaps.

Mismatch between observed and extracted text is preserved. The pure projection
returns a separate explicit source-mismatch Issue/event proposal; it neither
publishes that issue nor treats it as the planned check Issue. A mismatch blocks
readiness even if someone supplies a supported result or resolves the planned
question. Replacement cannot erase an unpublished mismatch obligation.

The caller separately registers the actual A05 VerificationResult with this
native observation as output, then an independent A04 resolver event. A result
alone, an observation alone, ready flags, extractor self-check, or issue_states
cache cannot certify readiness. Inconclusive/failed/refuted results remain gaps.
The planned criterion is fixed before observation. No source check or issue is
automatically resolved by this producer. A prior inconclusive/failed planned
check remains an obligation after replacement. Its existing Issue can explicitly
move checking → open; prepare a new A05 Verification ID against the repaired
current node, retaining that original Issue's resolution_condition; move open →
checking, record a new result using the actual replacement comparison, and have
an independent A04 resolver resolve it. This uses existing issue.event and
verification.prepare/result commands, preserves the old Issue/result bytes, and
does not reuse the old stale Verification or treat superseded as resolved.

`current_evidence(snapshot)` returns `{ready, reason_codes, required_actions,
corpus_ref, collect_ref, extract_ref, kept_source_ids, collected_source_refs,
extraction_refs, source_groups, limitations}`. collected_source_refs maps source
IDs to `{metadata_ref, raw_ref|null, access_status}`; extraction_refs maps claim
IDs to exact native claim object refs. source_groups is B01's validated grouping
(null if its setup/index is absent or stale). Missing stages return nonready
projections. Stale collect/extract inputs return collect_stale/extract_stale with
no usable ref for that stage, so a replacement can repair old input bindings.
Predecessor publication checks inspect native historical mismatch observations
without requiring obsolete upstream refs to remain current. Complete readiness requires the same approved corpus, complete kept
coverage, authentic native A05 source_check results with the bound observations,
and independent native A04 resolutions. Unavailable sources remain nonready
limitations; abstract/metadata limits remain visible even for supported checks.
B06/B07 must preserve this exact screen and evidence chain.

These checks validate supplied bytes, recorded roles, exact linkage and declared
judgments. They do not authenticate publishers, source capture, checker identity,
scientific correctness or statistical independence. Tests use synthetic captures
and synthetic declared authority; no network/source access is performed.
