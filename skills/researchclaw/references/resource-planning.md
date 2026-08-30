# Stage 11 — Resource Planning

Stage 11 plans resources without running the experiment. It consumes the
prepared packet's declared inputs plus its `hardware_observation`, and writes
only `experiment/resources.json`. Do not install packages, download data,
access a network, call an LLM, spawn an agent, or execute generated code.

## Exact workflow

```text
researchclaw-codex stage prepare ROOT --json
# Read only packet inputs and hardware_observation; author only experiment/resources.json.
researchclaw-codex stage validate ROOT --json
# If needs_input, ask the user to satisfy listed prerequisites, then:
researchclaw-codex execution recheck ROOT --json
# Stop. Never run the deferred command in Stage 11.
```

For a synthetic fixture used only to develop the execution flow, use an
explicit project-relative manifest path:

```text
researchclaw-codex execution recheck ROOT \
  --input-manifest experiment/input_manifest.dev.json \
  --development --json
```

The development check is isolated from the approved execution gate. It does
not edit `experiment/resources.json` or durable project state, never makes the
fixture approval-eligible, and never executes the deferred command. A valid
fixture returns `ready_for_development` and records its path and SHA-256 in an
evaluation event.

If the user explicitly requests a development evaluation after that check,
require a fresh confirmation for that individual run:

```text
researchclaw-codex execution run ROOT \
  --input-manifest PROJECT_RELATIVE_PATH \
  --development --confirm-development-run --max-seconds 120 --json
```

This is the only executable development branch: it runs a fixed local
NumPy-only Ridge model, writes `experiment/dev_results.json`, and reports
`development_run_complete` with `approval_eligible: false`. The research
approval gate remains unchanged, and the resulting synthetic metrics are not
research evidence. Report the development result and stop; do not describe it
as research execution.

Before authoring, confirm the packet is Stage 11, its `project_root` is the
intended root, and read every path in `required_inputs`. The Stage-11 packet
declares exactly these inputs:

| Binding name | Path |
| --- | --- |
| `design` | `experiment/design.json` |
| `package_manifest` | `experiment/package_manifest.json` |
| `config` | `experiment/code/config.json` |
| `hardware_profile` | `scope/hardware_profile.json` |

Parse the packet's `profile_context.hardware_observation` JSON string and place
the resulting object unchanged in `hardware_observation`. Do not fabricate a
GPU fact. The packet also declares a fixed deferred entry-point description
and result path `experiment/results.json`; they describe future execution and
are not commands to run here. Only a later authoritative argv array beginning
with a verified absolute interpreter may be executed by the user.

After a valid plan, Stage 11 advances the durable project to the Stage 12
approval boundary. Show the plan, readiness, warnings, and prerequisites to
the user. Stage 12 begins with the approval boundary and remains non-executing
for ResearchClaw. An explicit `approve` or `reject` decision is required.
Approval records a hash-bound decision only; it never executes the experiment,
deferred command, or generated code. After approval, the separate explicit
handoff below can prepare a user-run command and later register only its
contract-bound result. A rejection remains locked; it requires a later
explicit re-decision (`approve`) after reconsideration. Never decide or
re-decide on the user's behalf.

## Closed `experiment/resources.json` schema

Every listed field is required. Every object is closed: omit no field and add
no field. The exception is `saved_hardware_profile`, whose JSON object is
copied exactly from `scope/hardware_profile.json`, and the `bindings` map whose
names are semantically constrained below. Strings are non-empty; resource
numbers are non-negative integers (not booleans).

```text
root
├── schema_version: 1
├── project_id: current durable project ID
├── bindings: object of { path, sha256 } entries
├── saved_hardware_profile: exact JSON object of scope/hardware_profile.json
├── hardware_observation: passive local host observation
├── inputs: input-readiness entries
├── tasks: resource tasks
├── budget: aggregate resources
├── deferred_command: fixed command
├── result_path: fixed output path
├── prohibitions: six false booleans
├── warnings: sorted drift-warning strings
├── unmet_prerequisites: sorted actionable strings
└── readiness: ready_for_execution | needs_input
```

### Bindings and saved profile

`bindings` must contain exactly `design`, `package_manifest`, `config`, and
`hardware_profile`. Each binding has exactly `path` and `sha256`; its path is
the corresponding table path above and its digest matches both the current
regular file and the durable validated artifact. `saved_hardware_profile` is
JSON-value-equal to the current `scope/hardware_profile.json` object.

### Passive hardware observation

`hardware_observation` has exactly:

```json
{
  "logical_cpu_count": 0,
  "total_memory_bytes": 0,
  "free_disk_bytes": 0,
  "platform": "string",
  "architecture": "string",
  "gpu_available": null,
  "method": "python_stdlib_passive",
  "observed_at": "ISO-8601 timestamp with timezone"
}
```

`gpu_available` is `true`, `false`, or `null`. The other numeric facts are
non-negative. Validation compares CPU, total memory, platform, architecture,
and GPU availability to a fresh passive local observation; declared free disk
must not exceed that observation by more than 16 MiB. Do not probe hardware or
turn an unknown GPU into an available GPU.

Saved-profile drift also recognizes conservative legacy aliases. A legacy
`cpu` JSON integer aliases `logical_cpu_count`; a finite, non-negative
`memory_gb` JSON number aliases `total_memory_bytes` using exactly 1073741824
bytes per GiB. Canonical fields take precedence when both forms are present;
invalid alias values and unknown fields remain untouched evidence. Alias
comparison never rewrites `scope/hardware_profile.json`.

### Input-readiness entries

Each `inputs` entry has exactly:

```text
path, required, exists, is_regular_file, size_bytes, sha256,
license_status, preparation_note
```

`required`, `exists`, and `is_regular_file` are booleans; `sha256` is a string
or `null`; `license_status` is exactly `confirmed`, `not_required`, or
`unconfirmed`; and `preparation_note` is a non-empty string. Input paths are
unique project-relative paths. They must resolve inside the project through no
symlink component, traversal, or absolute path. Facts must match the current
filesystem: a regular file has its actual byte size and SHA-256, while a
missing or non-regular input has size `0` and hash `null`.

Entries marked `required: true` must have exactly the same path set as the
current hash-bound config's `input_contract.required_paths`. A config-required
path marked `required: false` is invalid. Additional unique project-relative
paths are optional extras and must be marked `required: false`; they still
receive full path, filesystem-fact, SHA-256, and license validation.

### Tasks and budget

Each `tasks` entry has exactly:

```text
task_id, kind, depends_on, priority, cpu_count, memory_bytes,
gpu_count, temporary_disk_bytes, estimated_duration_seconds
```

`task_id` and `kind` are non-empty strings; task IDs are unique. `depends_on`
is an array of existing, non-empty task IDs without a self-dependency or a
cycle. `priority` and all resource/duration quantities are non-negative
integers. There must be exactly one task whose `kind` is `experiment`. If any
inputs are declared, at least one task kind must be `preparation` or
`readiness`.

`budget` has exactly:

```text
max_parallel_tasks, peak_cpu_count, peak_memory_bytes, peak_gpu_count,
peak_temporary_disk_bytes, total_estimated_duration_seconds
```

All are non-negative integers. `max_parallel_tasks` is exactly `1`; peak GPU
count is at most `1`. Its values are derived, not estimated independently:

- `peak_cpu_count`, `peak_memory_bytes`, `peak_gpu_count`, and
  `peak_temporary_disk_bytes` are the maximum respective values across tasks.
- `total_estimated_duration_seconds` is the sum across tasks.

### Fixed fields and derived status

`deferred_command` is a non-authoritative display description of the entry
point and config, and `result_path` is exactly `experiment/results.json`.
Stage 12 creates a separate authoritative argv array whose first item is the
verified absolute interpreter. Never execute the display description or
substitute a `python` alias.

`prohibitions` has exactly these boolean fields, all `false`:

```text
network_access, downloads, package_installation, external_llm_calls,
nested_agent_processes, generated_code_execution
```

`warnings` exactly equals the sorted, unique saved-hardware-profile drift
warnings. `unmet_prerequisites` exactly equals the sorted, unique actionable
requirements generated from insufficient CPU, memory, disk, or GPU; missing or
non-regular required inputs; and required inputs with `unconfirmed` license
status. `preparation_note` is not a substitute for those engine-generated
messages. `readiness` accepts only `ready_for_execution` and `needs_input`:

- A valid-ready plan has no unmet prerequisites and sets
  `ready_for_execution`.
- A valid-missing plan has the exact derived prerequisite list and sets
  `needs_input`; it still completes planning but is not approval-eligible.
- An invalid plan has malformed/extra/missing fields, mismatched bindings or
  facts, an incorrect aggregate/status, unsafe paths, or a pre-existing
  `experiment/results.json`; validation reports issues and does not advance.

## Recheck and stop boundary

Only after a valid-missing plan has advanced to Stage 12 and the user has
satisfied the listed prerequisites, run `execution recheck ROOT --json`. It
refreshes only passive hardware, input facts, drift warnings,
`unmet_prerequisites`, and `readiness`; it rejects changed immutable planning
fields. Recheck must not add, remove, or change an input path, task, budget, or
deferred command. A passive `execution recheck` cannot erase a current human
rejection. Report its JSON readiness and then stop. Do not execute the
deferred display description; do not
write `experiment/results.json`; do not prepare or run a Stage-12 experiment.

## Explicit research handoff and registration

Before approval, obtain the complete self-test argv without undocumented
interpreter knowledge:

```text
researchclaw-codex experiment prepare-self-test ROOT --json
```

The user runs its returned authoritative `argv`, whose first item is the
verified absolute interpreter, then uses its `registration_argv` to register
the report:

```text
researchclaw-codex experiment register-self-test ROOT --report experiment/self_test_report.json --confirm-self-test --json
```

Only a current registered report is approval-eligible. Present it and the plan
so the user can review and decide; ResearchClaw never supplies the decision.
After approval, a separate explicit command may prepare the immutable
execution handoff:

```text
researchclaw-codex execution prepare-run ROOT --json
```

It writes `experiment/execution_contract.json` and returns an authoritative
argv array beginning with the verified absolute interpreter. A quoted command
is a display string only. It does not execute that argv. The user runs it
exactly in the project root. The fixed Stage-10 entry point validates the current
contract, all bound package files, and every required input before running its
bounded behavior and writing only `experiment/results.json`. Command stdout
and any development result are never research evidence, and a development
result is never registerable as research evidence.

Only the result path bound by that contract, `experiment/results.json`, can be
registered after the user-run command completes:

```text
researchclaw-codex execution register-result ROOT --result experiment/results.json --confirm-research-result --json
```

`--confirm-research-result` is required. Registration validates the contract
binding and result schema, performs descriptor-based disk preflight and
content-hash deduplication, then publishes immutable objects and a closed
immutable manifest. Only those objects ground Stage 13; mutable working files
do not. A successful registration advances to Stage 13; Stage 13 refinement
remains separate and is not executed or implemented by this interface.

Legacy generic contracts, mutable results, and ungrounded Stage-13 artifacts
are `legacy_untrusted`: audit-only and non-registerable. Use
`researchclaw-codex evidence audit ROOT --json`; never silently migrate them.
Quarantine actions require `--confirm`. Evidence objects are never operator-deleted.
Recovery preserves a published partial quarantine temp and
never writes it again; it uses a fresh inode when capacity permits or fails
closed for explicit manual/operator action. A complete read-only candidate may
be verified and published without mutation. The adversarial release gate
verifies this guarantee.
