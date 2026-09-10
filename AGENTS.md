# Research workflow guidance

For autonomous research work and its UI/orchestration in this repository, read
[the research operating guides](docs/research/guides/README.md), especially
[the coordinator guide](docs/research/guides/coordinator.md).

When preparing research-agent instructions, incorporate the relevant rules from
[the research-agent guide](docs/research/guides/research-agents.md). Do not assume
that a child agent receives this file automatically; include the applicable
instructions in its permitted inputs.

These guides do not replace runtime validation, user authorization, or immutable
research records. Report any mismatch between the operating guide and implemented
workflow; do not bypass gates or fabricate approval, evidence, or resolution.

Before changing research UI, read [the UI guidelines](docs/ui/README.md), use
[shared component rules](docs/ui/components.md), and check the relevant
[acceptance scenarios](docs/ui/review.md). Record deviations instead of adding
one-off wording or layout patterns silently.
