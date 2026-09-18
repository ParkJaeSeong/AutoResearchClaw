# Agent role guidance

Inspect a stage's role profile without opening or creating a project:

```sh
researchclaw-codex roles describe --stage 7 --json
```

The command supports stages 1–15 and returns `guidance_only` role metadata. Each role has a `role_id`, `responsibility`, stage-specific `required_questions`, `judgment_criteria`, and `authority_limits`. The three modes are:

- `judgment_council`: three judgment roles (`domain`, `methodology`, and `critical_reproducibility`) plus a non-voting `coordinator`.
- `work_and_verify`: a `worker` plus an independent `verifier`.
- `implementation_council`: an `implementation` role separated from the three judgment roles and the non-voting coordinator, keeping implementation distinct from evaluation and approval.

## Boundaries

`guidance_only` does not certify review submissions, independent agent execution, or scientific validity. `existing_protocol` describes software support, not project completion.

Initial independent judgments are not shared until submitted. Use one response round by default and preserve unresolved disagreement. Follow the actual supported stage protocol: this guidance adds no new registration gates. In particular, do not create council artifacts or gates for stages 1–12 merely because their logical role profiles are available.

Use native Codex agents and only packet-authorized tools and inputs. Do not call an external LLM API, select a model or provider, invent participants, or fabricate replies. Real host task IDs support provenance; when those IDs are unavailable, keep the assignment unverified.

Role counts describe logical responsibilities, not simultaneous execution requirements. A single agent cannot impersonate independent producers.

Stage 13 retains its minimum-two matching recommendations rule. Stage 14 remains analysis synthesis rather than a direction vote. Stage 15 retains its all-three agreement rule. Do not automatically rejudge historical decisions.

User execution and approval authority, budget limits, and path boundaries remain unchanged. Report a short conclusion, evidence, differences, limits, and next action linked to the actual records; the summary does not replace those records.
