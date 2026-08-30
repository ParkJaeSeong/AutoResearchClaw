# Approval policy

Stages 5, 9, and 20 are human gates. In the current milestone, stages 5 and 9 are reachable; stage 20 remains a roadmap contract.

After a gate output validates, the project status becomes `awaiting_approval`. Stop work and present the validation result plus the declared gate artifact. Ask the user to approve or reject; silence, a prior decision, or a general request to continue is not a new gate decision.

Record the user's decision with:

```text
researchclaw-codex approve ROOT --decision approve|reject --note TEXT --json
```

Approval is bound to the validated artifact hashes. If a gate artifact changes after validation or approval, treat the approval as invalid and return to validation. Never edit an approval record manually. A rejection leaves the stage needing revision; revise only its declared outputs and validate again before requesting another decision.

Always run `resume ROOT --json` after recording a decision or when returning in a later session. The durable project files, not conversation memory, determine the next action.

Stage-12 execution approval has an additional evidence prerequisite. First run
`researchclaw-codex experiment prepare-self-test ROOT --json`; the user runs
its authoritative `argv` beginning with the verified absolute interpreter and
then uses its `registration_argv` for the exact `experiment register-self-test`
step. Show the
current registered report and resource plan before asking for the decision.
Approval never runs the self-test or research argv.

After user-run execution, `execution register-result ...
--confirm-research-result --json` may publish an immutable manifest and
content-addressed objects. Disk preflight and deduplication precede
publication. A legacy generic contract or mutable result is audit-only,
`legacy_untrusted`, and non-registerable; route it through `evidence audit`
rather than approval or migration. Quarantine requires separate confirmation.

Required future recovery behavior preserves a published partial quarantine
temp and uses a fresh inode instead of writing it; a complete read-only
candidate may be verified without mutation. This is a mandatory pending Task 8
release gate, not a current guarantee.
