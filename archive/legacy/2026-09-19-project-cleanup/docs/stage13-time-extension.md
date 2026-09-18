# One-shot Stage 13 run-window extension

`refinement extend-run-window PROJECT --candidate-id candidate-001
--confirm-time-extension --json` records explicit user approval of one extra
hour measured from CLI registration time. This is not an experiment run or a
result/finalization approval.

The original session and its hashes remain unchanged. The CLI writes the
append-only `refinement/time_extension.json`, bound to the original session and
registered candidate manifest. The derived run contract includes this reference
and its file identity. The extension is permitted only after the original
calendar deadline, with a registered self-test and no reserved runs. Run count,
algorithm limit and accumulated execution budget never reset or increase.

An exact retry returns the same deadline, even after that deadline expires.
There is no repeated extension or replacement. An interrupted write can adopt
only the validated existing record; a future-dated orphan or a missing/tampered
registered record fails closed. Existing reservations cannot receive an extension.

## Separate computation and result-review limits

New CLI `prepare-run` reservations bind a separate one-hour result-registration
window, measured from reservation time. The session deadline controls whether a
new run may be reserved; the registration deadline controls review and publication
of that reserved result. Replays cannot restart either timer. Registration still
requires explicit user confirmation.

The numerical algorithm remains constrained to `reserved_maximum_seconds` (15
seconds in the live fixture). Runtime validation rejects exceeding that limit.
Budget accounting charges the full reserved compute allowance, not human waiting
time and not an untrusted elapsed-time claim. Accordingly `wall_seconds_used` is
a conservative reserved-budget charge for these new contracts; the actual
algorithm duration remains in the result's `runtime.elapsed_seconds`.

Existing reservations without the new fields retain the old timing rule and
original hashes. The Python API defaults to the legacy policy for compatibility;
callers requesting the new policy pass `review_window_seconds=3600`. The public
CLI always requests the new policy for a new reservation.
