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

Stage 12 is a non-executing trust boundary. ResearchClaw validates and records
evidence; it does not compute research metrics. Use this order:

1. Ask ResearchClaw for the complete known-answer self-test argv:

   ```bash
   researchclaw-codex experiment prepare-self-test ROOT --json
   ```

   This pre-approval command validates the current package and environment and
   returns `readiness`, `argv`, `environment_fingerprint`,
   `package_contract_sha256`, `report_path`, and `registration_argv`. Run the returned `argv` array exactly
   outside ResearchClaw. Its first item is the verified **absolute
   interpreter**; the authoritative argv requires no undocumented interpreter
   lookup and is never reconstructed from a quoted display string.
2. Register the externally written report explicitly:

   ```bash
   researchclaw-codex experiment register-self-test ROOT \
     --report experiment/self_test_report.json --confirm-self-test --json
   ```

   Success JSON has exactly `path`, `sha256`, and `size`. Registration verifies
   the exact known-answer metric value and package, fixture, and environment
   identities; it does not rerun the self-test.
3. Show the ready plan and registered self-test to the user. The user must
   review the execution approval and decide explicitly:

   ```bash
   researchclaw-codex approve ROOT \
     --decision approve|reject --note "User-reviewed execution decision" --json
   ```

4. Only after approval, prepare the durable handoff:

```bash
researchclaw-codex execution prepare-run ROOT --json
```

This writes `experiment/execution_contract.json`. JSON mode returns an `argv`
array whose first element is the verified absolute interpreter path. That
**authoritative argv** array, not a shell alias or the non-JSON quoted display
string, is the execution contract. ResearchClaw does not execute it. The user
runs the array exactly, without changing `PATH`, from the project root. The
entry point verifies every binding and exclusively creates
`experiment/results.json`; stdout and development results are not evidence.

5. Register only that contract-bound result:

```bash
researchclaw-codex execution register-result ROOT --result experiment/results.json --confirm-research-result --json
```

Registration performs a descriptor-based disk preflight, reuses already
published content by hash (deduplication), streams every accepted source into
the content-addressed object store, and publishes a closed **immutable
manifest**. State, event, and manifest recovery form one transaction. Stage 13
is grounded only in the manifest and immutable objects, never in mutable
working-tree inputs or `experiment/results.json`. Successful JSON reports the
registered result identity and Stage-13 transition.

For compatibility, `register-result --json` preserves the public keys
`readiness`, `approval_eligible`, `result_path`, `result_sha256`,
`current_stage`, and `next_action`; immutable-manifest details are obtained
with `evidence audit`. `prepare-run --json` returns exactly `readiness`,
`approval_eligible`, `argv`, `environment_fingerprint`, `result_path`,
`contract_path`, `contract_sha256`, `bindings`, `inputs`, and
`result_template`. Errors keep their existing category string on stderr as
`error: CATEGORY` and exit with status 2, including
`execution_environment_changed`, `execution_contract_stale`,
`research_result_file_invalid`, and
`research_result_registration_recovery_invalid`.

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

The enforced recovery behavior is that a published partial quarantine temp is
never resumed or written: recovery preserves that inode and starts with a
fresh inode when capacity permits, otherwise failing closed with explicit
manual/operator action. A complete read-only candidate may be verified and
published without mutation. The adversarial release gate verifies this guarantee.

### Stage-12 recovery routes

| Condition | Safe action |
| --- | --- |
| Environment drift | Keep Stage 12 unchanged; rerun the known-answer self-test with the verified current environment, register it, obtain a new approval, and prepare again. |
| Existing result | Run `execution quarantine-result ROOT --reason invalid_result --confirm --json`, inspect the retained copy, then use the separately confirmed cleanup route before a rerun. |
| Stale contract | Keep Stage 12; run `execution prepare-run ROOT --json` to replace only the stale contract after current bindings validate. |
| Insufficient disk | Make no evidence mutation; inspect `evidence quarantine-inventory ROOT --json` and arrange operator-managed capacity. Evidence objects are never operator-deleted. |
| Interrupted registration | Run `status`, `resume`, or the same registration command; recovery verifies the pending immutable transaction and either completes it or restores Stage 12. |
| Legacy Stage 13 evidence | Run `researchclaw-codex evidence audit ROOT --json`; `classification: "legacy_untrusted"` is audit-only and cannot be registered or silently migrated. Return to Stage 10 package validation for new trusted evidence. |
| Published partial quarantine temp | Preserve it unchanged and use a fresh inode if capacity permits; otherwise stop for manual/operator action. A complete read-only candidate may be verified and published without mutation. |

`evidence audit` returns exactly `project_id`, `classification`, and
`registration`. `classification` is `immutable_registered` only when the
closed manifest and its objects ground the current registration; otherwise it
is `legacy_untrusted` and `registration` is `null`. Legacy generic execution
contracts, mutable results, and Stage-13 artifact references are audit-only,
non-registerable evidence. Automatic migration is intentionally unsupported.

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

### Stage-12 release verification trust boundary

Run `scripts/verify_stage12_evidence.sh` only in a trusted, operator-controlled
local environment. Set `PYTHON_BIN` to the preferred Python 3.11+ interpreter;
it must import pytest. Project virtual environments and PATH executables are
also treated as trusted candidates. The script validates Python/pytest
capability and catches accidental no-op or malformed wrappers, but portable
shell cannot authenticate a responsive same-user executable that can observe
and emulate every probe. Such a malicious local executable is outside this
release gate's threat model.

Candidate validation alone is insufficient for success. Each mandatory pytest
run must emit executed test-node markers and a positive, clean pass summary with
no skips, xfails, xpasses, deselections, or errors. Compileall must emit its
exact per-run marker. Missing, empty, malformed, or oversized command output
fails the release gate even when the selected executable returns status zero.

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
