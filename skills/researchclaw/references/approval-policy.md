# Approval policy

Stages 5, 9, and 20 are human gates. In the current foundation milestone, stage 5 is the only reachable gate.

After a gate output validates, the project status becomes `awaiting_approval`. Stop work and present the validation result plus the declared gate artifact. Ask the user to approve or reject; silence, a prior decision, or a general request to continue is not a new gate decision.

Record the user's decision with:

```text
researchclaw-codex approve ROOT --decision approve|reject --note TEXT --json
```

Approval is bound to the validated artifact hashes. If a gate artifact changes after validation or approval, treat the approval as invalid and return to validation. Never edit an approval record manually. A rejection leaves the stage needing revision; revise only its declared outputs and validate again before requesting another decision.

Always run `resume ROOT --json` after recording a decision or when returning in a later session. The durable project files, not conversation memory, determine the next action.
