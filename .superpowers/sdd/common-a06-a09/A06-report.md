# A06 implementation report

Implemented the two pure tuple validators in `positions.py` and a read-only
`commands.read_policy_snapshot(root)` accessor that reuses the same verified
ancestry and object-byte hydration as mutation handlers.

Position changes now require an exact registered Issue, active assignment,
frozen participant session, immutable input/evidence references, a fresh
position/event identity, and an exact prior Position by the same issue author.
Change-kind source rules compare artifact/hash identity, so a newer HEAD label
does not count as added evidence.

Decision rationale validation resolves registered issues, positions,
VerificationResults, claims, acknowledgements, and dissent links. Each claim
requires a role position and verification result. Acknowledgement records bind
the exact position, claim, summary text, disposition enum, assignment, and that
assignment's actor; unrelated acknowledgement records yield
`position_ack_missing`. Unknown or stale references yield `ref_unknown`.

TDD evidence:

- RED: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_positions.py -q`
  failed during collection because `researchclaw.core.research_graph.positions`
  did not exist.
- GREEN: the same focused command passed `7 passed in 0.59s`.
- `git diff --check` passed before staging.

Independent review follow-up added two focused regressions. Duplicate exact
claim dispositions now return `claim_disposition_duplicate`, and malformed
frozen-session participant arrays fail closed with `position_session_missing`
in both public validators rather than raising `TypeError`. The focused RED run
showed those two failures with 7 passing tests; the subsequent GREEN run passed
`9 passed in 0.61s`.

The fixtures are synthetic structural/linkage examples. Passing them does not
establish that a verification result or scientific claim is substantively
sufficient. No producer, mutation operation, CLI, UI, network, or experiment
execution was added. A04/A05 and the broad suite are reserved for the root's
final regression after A09.
