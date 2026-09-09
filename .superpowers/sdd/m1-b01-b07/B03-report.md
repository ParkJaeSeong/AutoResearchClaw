# B03 implementation report

Base: ab07e88 (approved B02). Scope: m1_nodes.py, m1_scope.py,
test_m1_scope.py, narrow commands.py registration/context hydration,
m1-node-inputs.md and this report. No B04/B05 producer, approval decision,
CLI/UI, host execution or broad suite was added.

Implemented actual bounded `m1.node.register` for scope/questions only. Closed
content separates declared user goal/constraints from agent assumptions and
records each question's selection rationale. Native node revisions have fresh
IDs/attempts, exact current upstream inputs, explicit previous revision/reason,
preserved immutable bytes, and a current per-node object alias. Stored
previous_ref_key encodes validated same-node lineage as historical metadata;
this avoids B02 mistaking a deliberately old revision for current evidence.

The pure prepare_scope_council projection supplies concrete B02 council binding
and consumes actual native council preparation/submission records. Author actor,
node, attempt, current input, required independent reviewers, explicit phases,
response links and final judgments are bound. Issue-free judgments need no
invented Issue/Position. Formal positions require an authored final stance or
exact retained acknowledgement. New revisions need a fresh council. Unreviewed
scope cannot register questions, and search is only exposed after reviewed
questions; B03 does not register search output.

Readiness uses native A07 issue status/scoped blocking, including unresolved
optional visibility and explicit nonoptional proposal publication requirements.
No per-round human approval is introduced: scope/questions review readiness is
not A07's authority gate and is not an approval or execution grant. Original
native record/event equality rejects replacement bodies masquerading as earlier
submissions; mutable issue_states cannot erase a native block.

Focused TDD evidence:

- Initial RED: 16 failed (0.19s), all missing m1.node.register/unknown_operation.
- Initial GREEN: 16 passed (5.56s).
- Additional malformed-discriminator RED: 2 failed, 21 passed (6.95s).
  Explicit string checking now rejects list/dict node values as policy errors.
- Final `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_scope.py -q`:
  23 passed (7.01s). `git diff --check`: clean.

Fixtures register real native nodes and B02 councils/submissions; no node maps
are seeded directly. They cover actual fresh revision review, author self-review,
declared-author mismatch, final and response barriers, stale scope inputs,
unpublished and native scoped issues, formal stance retention, immutable object
preservation, replay/conflict and rejected-command HEAD preservation. Deliberate
raw synthetic tampering is limited to refusal regressions.

Synthetic policy checks are not actual research, host independence, user-input
authentication, scientific correctness or user acceptance. Parent owns
independent review, acceptance and shared task-board updates before B04 proceeds.

## Independent review correction wave

Confirmed both P2 findings with native command regressions: an obsolete scope
input prevented a legitimate questions replacement; a new scope revision could
drop its predecessor's disclosed major proposal. Focused RED: 2 failed,
23 passed (10.43s).

Predecessor lookup now validates exact current revision identity without requiring
its consumed inputs to remain current; replacement inputs still require current
reviewed parents. Before replacement, disclosed nonoptional proposals must be
published as native Issues while original target refs remain current. Publication
does not require resolution and does not forbid legitimate edits: the same
unresolved native issue remains visible/scoped after replacement. The refusal
regression asserts HEAD preservation, then publishes and successfully edits.

Focused GREEN: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_scope.py -q`
→ 25 passed (14.16s). Only m1_nodes.py, the focused test, this report and the
node-input supplement changed; no broad suite or additional feature scope.

## Re-review repair-path correction

Confirmed the induced P2 with a native incorrectly declared council author:
focused RED was 1 failed, 25 deselected (0.12s). Replacement had inadvertently
required old council readiness validation through `_council`. Publication
prechecking now reads backed native councils/proposals scoped to the predecessor
node/attempt without imposing old author/independence/readiness success. Existing
disclosed publication obligations still apply; a fresh revision and correctly
authored new council can repair setup mistakes.

Focused full B03 GREEN: 26 passed (14.65s). The regression exercises registration,
refused old readiness, successful revision and successful fresh three-phase
council. No broad suites or other feature changes. `git diff --check`: clean.
