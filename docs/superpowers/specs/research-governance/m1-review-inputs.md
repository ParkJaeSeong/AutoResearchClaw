# B06 native M1 synthesis and hypothesis review inputs

This supplement freezes the B06 extension of `m1.node.register` and the pure
`m1_review.prepare_hypothesis_review(read_policy_snapshot(root))` projection.
It checks recorded structure, source linkage, and independent review completion;
it does not establish scientific truth, execute experiments, approve a corpus,
resolve an Issue, or accept a transfer.

## Native revision content

The existing closed native node envelope, fresh UUID revision/attempt/event,
immutable `previous_ref_key` lineage, stale HEAD handling, and command replay
rules apply. No caller readiness field is accepted. Exact parent keys are:

| Node | input_refs keys |
| --- | --- |
| synthesize | screen, collect, extract |
| hypothesize | screen, extract, synthesize |
| review | screen, extract, synthesize, hypothesize |

Each parent is the actual current native node version. `screen` must equal the
complete approved corpus from B05 `current_evidence`. Authorship requires that
B05 projection to be ready. Parent B06 councils and carried Issues may still
need work: registering a repair must remain possible. Final readiness separately
requires every current parent council and current source check to pass.

Closed content objects:

- `synthesize`: `findings`, `rejected_alternatives`, `limitations`.
  Each finding has `finding_id`, `claim`, `evidence_refs`,
  `counterevidence_refs`, `limitations`. Each alternative has `alternative_id`,
  `description`, `reason`, `evidence_refs`.
- `hypothesize`: `hypotheses`, `limitations`. Each hypothesis has
  `hypothesis_id`, `statement`, `population`, `prediction`,
  `falsification_condition`, `evidence_refs`, `alternative_ids`, `limitations`.
- `review`: `prior_issue_dispositions`, `open_questions`, `limitations`.
  A disposition has `issue_id`, `disposition`, `owner_assignment_id`,
  `hypothesis_ids`, `rationale`, `verification_refs`. The disposition enum is
  `carry_forward`, `verification_planned`, `native_resolved`, `transfer_proposed`.
  An open question has `issue_id`, `question`, `method`, `resolution_condition`,
  `owner_assignment_id`, `to_milestone`, `budget_ref`, `limitations`.

Lists are explicit, including empty limitations/counterevidence/alternatives.
Findings and hypotheses are nonempty. Their IDs and alternative IDs are unique
nonempty text within a revision; hypothesis alternative IDs name that exact
current synthesis. Evidence lists on findings/hypotheses/alternatives are
nonempty and reference only exact current B05 extraction claim objects.
Counterevidence uses the same evidence graph. No raw source alias or unrelated
approved screen can impersonate an extracted claim. Source grouping and access
limitations are derived from B05/B01, never inferred from the number of papers.

Dispositions and questions have unique Issue UUIDs. Hypothesis IDs name the
current hypothesis revision. Owner IDs may be null for honest pending imported
work, but readiness requires a responsible owner. Nonnull IDs equal the effective
owner derived from native Issue events (or the original Issue owner) and name an
active M1 owner assignment. Question and resolution-condition text match the
actual Issue exactly. `to_milestone` is M1 or M2; M2 questions require an empirical
Issue and `transfer_proposed`. Nullable `budget_ref` is a backed reference;
transfer completeness requires a supplied budget reference. It is recorded
planning evidence, not an execution allowance or a proof of available budget.

`verification_planned` requires actual bound A05 Verification references.
`native_resolved` requires native resolved status and the exact supporting
VerificationResult references from the resolution event, native A05
registration, the Issue/rule binding, and current verification inputs. A new
hypothesis, a rationale, an extraction observation, or a generic object cannot
substitute for independent native resolution. Transfer proposals remain
unresolved and require later B07 acceptance and explicit native owner events.
No transfer is produced by B06.

## Pure projection and issue accounting

The result contains `ready`, deterministic `reason_codes` and `required_actions`,
`node_refs` (`synthesize`, `hypothesize`, `review`, each nullable), `corpus_ref`,
`source_groups`, `prior_issues`, `unaccounted_issue_ids`, `unresolved_issue_ids`,
`transfer_obligations`, `limitations`, `council_id`, and `phase`.
Each prior issue row contains `issue_id`, `question`, `category`, `severity`,
`native_status`, `owner_assignment_id`, and nullable `disposition`.

All unresolved M1 issues, including unscoped major and optional issues, and all
Issues active at or carried in earlier native review revisions, and all imported
review Issues (even if subsequently resolved), are accounted for before
missing evidence/node checks. Imported source status never becomes native
resolution. No new issues in round two does not remove prior Issues. Missing
rows produce `prior_issue_unaccounted`; missing owners remain explicit;
nonoptional unresolved issues block completion. Optional issues remain listed.
B06 review councils must disclose every required prior Issue in their frozen
`issue_ids` packet. Final councils reuse the native exact domain/methodology/
critical roles, distinct author-independent actors, phase barriers, response
links, and final recommendations. Stale consumed refs yield `NODE_stale` and a
null node ref, allowing an explicit replacement while retaining old bytes.

## A03 imported Issues and explicit materialization

A03 stores typed Issue wrappers inside the verified import state without storing
individual canonical Issue objects. B06 reproduces the A03 projection from the
pinned archived commit/object bytes and requires exact native `m1_imported`
genesis, wrapper, source mapping, and import metadata equality. This display-only
adapter enumerates pending Issues without materializing or changing them.

The explicit registered operation `m1.issue.materialize` accepts exactly
`{issue_id: UUID}`. After the same authentic reconstruction it registers exactly
the existing Issue bytes under its immutable Issue-ID alias and emits
`import_issue_materialized`. It changes no state fields, owner, category, source
status, approval, or import-pending marker. Existing aliases are rejected;
normal same-command replay returns the original receipt and stale HEAD rejects.
There is no generic object/state import operation.

A subsequent caller can use an existing native council owner assignment, an
explicit backed budget prerequisite, A05 `verification.prepare`, and A04
`issue.event` to checking with `owner_assignment_id`. Effective responsibility
then comes from that real event; original Issue bytes stay unchanged. Materialize
all imported Issues before predecessor policies that require individually backed
Issue records. This command does not itself provide a budget, assign a role,
classify an imported Issue as empirical, or grant resolution authority.
