# AutoResearchClaw Codex

AutoResearchClaw Codex is a Codex-native research orchestration plugin derived
from [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw). Codex
does the reasoning and tool-using work in the active session; a small local
Python engine provides deterministic task packets, validation, durable state,
hash-bound approvals, resume, and evaluation records.

The Codex-native path does not call an external LLM API or start a nested
Codex, Claude, Gemini, OpenClaw, or ACP agent. The plugin activates only when
the user invokes `$researchclaw` or clearly requests ResearchClaw by name.

Codex-native supported execution boundary: stages 1–11. This release continues
past the user-approved literature-screen gate to provenance-aware knowledge
extraction, evidence synthesis, and provenance-linked hypothesis generation
without an external LLM API key, then creates a reproducible validation design
for policy evidence, computational, or laboratory work. Stage 9 is an approval
gate. After an approved computational design, Stage 10 authors and statically
validates a fixed six-file computational package but does not execute it.
Policy-evidence and laboratory Stage 10 packages are unsupported. Stage 11
authors and validates only `experiment/resources.json` from declared inputs
and passive local hardware facts. Stage 12 begins with an explicit user
approval that records a hash-bound decision but does not execute the
experiment. After approval, Stage 12 supports an explicit handoff and
contract-bound user-result registration; ResearchClaw never executes the
experiment. Stage 13 refinement, experiment execution by ResearchClaw, and
full-paper production remain roadmap work; later declared contracts are not
claims of implemented capability.

Stages 1–11 are implemented planning and validation work. Stage 12 additionally
supports only the explicit approved handoff and contract-bound result
registration boundary; it is not an experiment-execution capability.

## Install the CLI

The Python distribution is `researchclaw-codex`, and its supported Codex-native
command is `researchclaw-codex`.

```bash
git clone https://github.com/ParkJaeSeong/AutoResearchClaw-Codex.git
cd AutoResearchClaw-Codex
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
researchclaw-codex --help
```

Installing the Python distribution provides the CLI. It does not install,
enable, or implicitly activate the Codex plugin.

## Use the plugin

Install and enable this repository as a Codex plugin through an explicit local
plugin workflow. No marketplace action is required for development. Once the
plugin is enabled, invoke it by name:

```text
$researchclaw Start a materials research project on formation-energy prediction.
```

Ordinary research questions do not activate the skill.

## Codex-native CLI workflow

All paths returned in task packets are relative to the project root. JSON mode
writes one JSON value to stdout; diagnostics go to stderr.

```bash
researchclaw-codex init ./demo-research \
  --topic "Formation-energy prediction" --profile materials_ai --json
researchclaw-codex status ./demo-research --json

researchclaw-codex stage prepare ./demo-research --json
# Read every required input and create only the declared outputs.
researchclaw-codex stage validate ./demo-research --json
```

Repeat `prepare` → artifact creation → `validate` through stage 5. After the
stage-5 output validates, stop for the user's explicit decision. An approval
advances to stage 6; prepare the extraction packet, create only its declared
knowledge artifacts, and validate them:

```bash
researchclaw-codex approve ./demo-research \
  --decision approve --note "Literature corpus accepted" --json
researchclaw-codex resume ./demo-research --json
researchclaw-codex stage prepare ./demo-research --json
# Access permitted source material and write only the two declared outputs.
researchclaw-codex stage validate ./demo-research --json
researchclaw-codex resume ./demo-research --json
# Prepare stage 7, then have Codex write only knowledge/synthesis.md.
researchclaw-codex stage prepare ./demo-research --json
researchclaw-codex stage validate ./demo-research --json
researchclaw-codex resume ./demo-research --json
# Prepare stage 8, then have Codex write only hypotheses/candidates.jsonl.
researchclaw-codex stage prepare ./demo-research --json
researchclaw-codex stage validate ./demo-research --json
researchclaw-codex resume ./demo-research --json
# Prepare stage 9, then have Codex write only experiment/design.json.
researchclaw-codex stage prepare ./demo-research --json
researchclaw-codex stage validate ./demo-research --json
# Stop here and ask the user to approve or reject the validated design.
researchclaw-codex approve ./demo-research \
  --decision approve --note "Validation design accepted" --json
researchclaw-codex resume ./demo-research --json
# For an approved computational design, prepare and author only the six Stage-10 outputs.
researchclaw-codex stage prepare ./demo-research --json
researchclaw-codex stage validate ./demo-research --json
researchclaw-codex resume ./demo-research --json
# Prepare Stage 11, author only experiment/resources.json, then validate it.
researchclaw-codex stage prepare ./demo-research --json
researchclaw-codex stage validate ./demo-research --json
# If validation reports needs_input, have the user satisfy prerequisites first.
researchclaw-codex execution recheck ./demo-research --json
# Stop. Do not run the deferred experiment command.
```

To validate a small synthetic fixture while developing the Stage-12 flow,
select it explicitly without changing the approved research input or execution
gate:

```bash
researchclaw-codex execution recheck ./demo-research \
  --input-manifest experiment/input_manifest.dev.json \
  --development --json
```

This development-only check verifies the manifest, referenced CSV row counts
and hashes, group isolation, and feature cutoffs. It returns
`ready_for_development` with `approval_eligible: false`; it never executes the
experiment or makes synthetic data eligible as research evidence.

To run the bounded development evaluation itself, make the same synthetic
intent explicit for every run:

```bash
researchclaw-codex execution run ./demo-research \
  --input-manifest experiment/input_manifest.dev.json \
  --development --confirm-development-run --max-seconds 120 --json
```

This runs only the fixed local NumPy-only Ridge model and writes
`experiment/dev_results.json`. It reports `development_run_complete` with
`approval_eligible: false` and leaves the research approval gate unchanged. It neither
creates `experiment/results.json` nor makes synthetic results research
evidence.

## Explicit Stage-12 research handoff and registration

After the user has explicitly approved a ready Stage-12 research plan, prepare
the durable handoff:

```bash
researchclaw-codex execution prepare-run ROOT --json
```

This writes `experiment/execution_contract.json` and returns the approved
command. It does not execute that command: the user runs the returned command
in the project root. The fixed Stage-10 entry point consumes that exact current
contract, streams and verifies every bound package file and required input,
runs its bounded generated experiment behavior, and creates only the declared
`experiment/results.json`. Command stdout and every development result are
never research evidence. Only that contract-bound result can be registered:

```bash
researchclaw-codex execution register-result ROOT --result experiment/results.json --confirm-research-result --json
```

If recovery identifies an invalid unregistered result, the confirmed
`execution quarantine-result` command copies the exact descriptor-validated
bytes into the private evidence quarantine and removes the result only from
durable project state. It deliberately does **not** move, overwrite, or delete
the mutable `experiment/results.json` pathname. Before rerunning the exclusive
external command, the handoff requires the separately confirmed
`execution cleanup-quarantined-result` action. Cleanup revalidates the exact
no-symlink single-link source identity and preserves it under the private
quarantine before clearing the pathname; a replacement, symlink, or ambiguous
hardlink is refused. This explicit second confirmation keeps quarantine itself
non-mutating while making cleanup honest and actionable.

Result quarantine is intentionally retained evidence, not garbage-collected
capacity. Before either copy or confirmed pathname cleanup, ResearchClaw uses
descriptor-based filesystem capacity plus bounded no-follow scans of both
`quarantine/copies` and `quarantine/results`. Entry-count, retained-byte, unsafe
entry, and free-space limits fail before the requested mutation and direct the
operator to the structured inventory:

```bash
researchclaw-codex evidence quarantine-inventory ROOT --json
researchclaw-codex evidence quarantine-operator-cleanup ROOT --confirm --json
```

The confirmed operator route does not unlink, truncate, or claim to reclaim
same-user quarantine files: it returns `reclaimed_bytes: 0`, preserves every
listed path, and reports when manual filesystem/operator action is required.
Unknown or crash-abandoned copy candidates are likewise inventoried and left
untouched. This policy prefers unrelated-byte safety over automatic capacity
recovery.

Successful registration records the validated result and advances the project
to Stage 13. Stage 13 refinement remains a separate boundary; this CLI does
not refine or execute research on the user's behalf.

Approval is tied to exact validated artifact hashes. Changing an approved
artifact rewinds the durable workflow to its producing stage; changing the
approved shortlist also requires a new user decision. After an unchanged
approval, `resume` points to stage-6 extraction. After valid stage-6 output it
points to stage-7 synthesis, after valid stage 7 it points to stage-8 hypothesis
generation, and after valid stage 8 it reports the hypothesis milestone and
points to stage-9 validation design. A valid stage-9 design requires the user's
explicit approval or rejection. After approval of a computational design,
`resume` points to Stage 10. Codex authors and statically validates only the
declared computational package, without execution. A valid Stage 10 advances
to Stage 11, where Codex reads only packet-declared inputs and the passive
hardware observation, and authors only `experiment/resources.json`. A valid
ready plan reaches Stage 12 for the user's explicit approval or rejection;
approval does not execute the deferred command. After approval, the explicit
handoff may return a user-run command and a contract-bound result may be
registered, but ResearchClaw never executes the experiment. A valid
`needs_input` plan lists prerequisites, which the user must satisfy before the
constrained `execution recheck`.

## Durable project data

A project stores its canonical state at `.researchclaw/state.json`, approvals
under `approvals/`, and append-only evaluation events under `evaluation/`.
Conversation history is never required to resume. Artifact reads reject
absolute paths, traversal, symlinks, and paths that resolve outside the project.

## Versioning and identity

The Python distribution and Codex plugin use the same derivative release
version. This derivative is `0.1.0`. Upstream AutoResearchClaw release numbers
are tracked separately and do not determine the derivative's version.

Product identity:

- Repository: `AutoResearchClaw-Codex`
- Python distribution: `researchclaw-codex`
- CLI: `researchclaw-codex`
- Plugin ID: `autoresearchclaw-codex`
- Explicit skill: `$researchclaw`

## Upstream attribution and legacy workflow

This project retains the upstream MIT license and attribution. The inherited
autonomous/API-backed workflow remains in the repository during migration but
is not the default Codex-native path. Its original documentation is preserved
in [LEGACY_UPSTREAM_README.md](LEGACY_UPSTREAM_README.md), and its original
agent bootstrap guide is preserved in
[LEGACY_UPSTREAM_AGENT_GUIDE.md](LEGACY_UPSTREAM_AGENT_GUIDE.md). Those files
are labeled legacy and may describe external LLM credentials, nested agents,
or automatic approval; their instructions do not apply to `$researchclaw`.

See [LICENSE](LICENSE) for licensing terms and
[the upstream project](https://github.com/aiming-lab/AutoResearchClaw) for its
current releases and documentation.
