# Foundation evaluation rubric

Run `researchclaw-codex evaluate ROOT --json` whenever reporting a milestone. Preserve the returned JSON in the report or test evidence instead of reconstructing metrics from memory.

The foundation rubric interprets metrics as follows:

| Metric | Direction | Meaning |
| --- | --- | --- |
| `stage_completion_rate` | Higher | Completed contracts divided by all 23 declared stages. A validated stage 8 is `8 / 23`; it is not a complete research project or paper. |
| `validation_failure_count` | Lower | Invalid validation attempts recorded in the event log. |
| `retry_count` | Lower | Validation attempts beyond the first attempt for each stage. |
| `approval_count` | Higher | User approvals recorded at gates. |
| `resume_count` | Lower | Durable resume operations; report the observed count without treating all resumes as errors. |
| `artifact_count` | Higher | Artifacts tracked in durable state. |
| `external_llm_calls` | Lower | Must remain zero for the Codex-native foundation engine. |
| `nested_agent_processes` | Lower | Must remain zero for this workflow. |

Metrics are workflow evidence, not a claim of scientific quality. Summarize validation failures and approvals alongside the completion rate, and state that stage 9 experiment design, experiment execution, and paper work are deferred.
