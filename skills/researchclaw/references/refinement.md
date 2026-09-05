# Stage 13 council refinement

Use this protocol only for one explicit user request to refine an already-grounded Stage-13 ResearchClaw project. Do not infer a request from a result, a status report, or a prior conversation.

## Roles and isolation

- The coordinator has no vote. It prepares the envelope, assigns the fixed roles, records artifact hashes, and invokes only the Task-7 `researchclaw-codex refinement` argv returned by the CLI.
- Assign exactly three voting tasks: `domain`, `methodology`, and `critical_reproducibility`. Each produces an independent assessment from the packet and registered artifacts before seeing another assessment, a rebuttal, or a vote.
- Do not disclose any assessment until all three are registered. The coordinator then registers exactly one challenge/revision round and each voter records its final vote. Preserve every assessment, challenge, response, final vote, and minority rationale as dissent; never rewrite the dissent to make a consensus appear unanimous.
- The implementation agent must not vote. It may create only the winning bounded candidate, run its returned self-test argv, and report a result. It has no council role and cannot approve, select, or finalize.

## User boundaries and deterministic flow

The coordinator must pause for the user at each explicit boundary: request to start refinement, each `--confirm-refinement-self-test`, each `--confirm-refinement-result`, and `--confirm-refinement-finalization`. These confirmations register reviewed artifacts; they never authorize an unbounded run or a substitute command.

Use no invented shell command, Python call, provider setting, or reconstructed display string. The Task-7 CLI argv is authoritative: use the literal `researchclaw-codex refinement` command and arguments below (or its checkout fallback), and execute a candidate only through the returned `argv` array in its returned `cwd`.

1. `researchclaw-codex refinement prepare-session ROOT --envelope refinement/envelope.json --json`
2. Register all three independent assessments, then `researchclaw-codex refinement register-deliberation ROOT --rebuttals ... --json` for the single challenge/revision round.
3. Register the 2–1 council decision. A `refine` decision may register one candidate; the implementation agent registers its returned self-test report only after the user confirms it.
4. Prepare the one bounded run, have the user run only its returned argv, and register the result only after the user confirms it. Candidate evidence must remain in `.researchclaw/evidence/refinement-manifests/`; never modify the Stage-12 baseline bytes or reuse the generic evidence-manifest namespace.
5. Repeat the three independent assessments and one challenge/revision round over the registered candidate evidence. Register the 2–1 final selection, retain the dissenting role and rationale, and finalize only after the user confirms it. A successful finalization advances to Stage 14.

If the run, wall-time, candidate-time, path, or scope envelope is exhausted, stop. Report the retained evidence and dissent, then ask the user for an explicit authority escalation; do not loosen the envelope, add a run, or reinterpret a rejection.

## No-provider rule

Do not configure a provider, request a key, initialize an SDK, or make a network call. The coordinator, voters, and implementation agent must not call an LLM API. This protocol uses the current authorized Codex tasks and deterministic local CLI only.
