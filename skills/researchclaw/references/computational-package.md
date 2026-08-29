# Stage 10 — Computational Package

Use this reference only when the prepared packet's `stage_id` is `10`. Read
the complete approved `experiment/design.json`; its hash-bound approval is the
authority for this stage. Stage 10 supports only
`validation_type: computational`. A `policy_evidence` or `laboratory` design
is unsupported at this stage: do not create a package for it. Do not download
data, run training or evaluation, collect results, invoke an external LLM, or
start another agent process. Codex authors but does not execute the package;
it will statically validate the authored files.

Write exactly these six packet-declared outputs and no other project artifacts:

1. `experiment/package_manifest.json`
2. `experiment/code/README.md`
3. `experiment/code/main.py`
4. `experiment/code/config.json`
5. `experiment/code/requirements.txt`
6. `experiment/code/tests/test_smoke.py`

All paths are project-relative. Do not add a results directory, downloaded
data, generated metrics, a notebook, a lockfile, or an undeclared output.

## Manifest

`experiment/package_manifest.json` is one closed JSON object with exactly
these fields:

- `schema_version`: integer `1`.
- `project_id`: exact durable project ID.
- `design_sha256`: SHA-256 of the exact approved `experiment/design.json`
  bytes.
- `validation_type`: exact string `computational`.
- `files`: exactly five objects, one for each `experiment/code/` output below;
  every object has exactly `path`, `role`, and `sha256`. `path` is the
  project-relative file path, `role` is non-empty text, and `sha256` is the
  SHA-256 of that file's exact bytes. Do not list the manifest itself.
- `entry_point`: exact string `experiment/code/main.py`.
- `config_path`: exact string `experiment/code/config.json`.
- `runtime`: a closed object with only a non-empty `python` constraint.
- `input_contract`: the exact closed input contract also used in config, with
  `design_binding`, a non-empty list of project-relative `required_paths`, and
  a non-empty text list of `required_fields`.
- `output_contract`: the exact closed later-execution contract also used in
  config, with `design_binding`, exact `result_path`
  `experiment/results.json`, and a
  non-empty text list of `required_fields`. Declaring this path does not create
  it during Stage 10.
- `commands`: exactly the command object below.
- `prohibitions`: exactly the closed object
  `{"stage_10_execution": false, "network_access": false,
  "external_llm_calls": 0, "nested_agent_processes": 0}`.
- `reproducibility`: exactly `design_sha256`, a non-empty integer `seeds`
  list equal to the config seed values, and `dependencies: "bounded"`.

The `files` paths are exactly:

- `experiment/code/README.md`
- `experiment/code/main.py`
- `experiment/code/config.json`
- `experiment/code/requirements.txt`
- `experiment/code/tests/test_smoke.py`

Set `commands` to exactly:

```json
{
  "dry_run": "python experiment/code/main.py --config experiment/code/config.json --dry-run",
  "smoke_test": "python -m pytest experiment/code/tests/test_smoke.py -q"
}
```

## Configuration and code

`experiment/code/config.json` is one closed JSON object with exactly these
fields:

- `schema_version`: integer `1`.
- `project_id` and `design_sha256`: exact values from the approved design
  binding.
- `datasets` and `baselines`: exact copies of the approved fields named by
  their traceability entries.
- `metrics`: the complete approved metric objects, including each target and
  threshold, copied without omission or substitution.
- `split_strategy`: exactly `design_binding`, `groups`, `isolation_key`, and
  `overlap_policy`. The binding equals the approved closed split-strategy
  object; `groups` contains each of `train`, `validation`, `calibration`, and
  `test` exactly once; `isolation_key` exactly equals the approved
  split-strategy `isolation_key`; and `overlap_policy` is `disjoint`.
- `seeds`: exactly `design_binding` and `values`; the binding equals the
  approved reproducibility source selected by traceability and `values` is a
  non-empty list of JSON integers.
- `input_contract`: exactly `design_binding`, `required_paths`, and
  `required_fields`. Its binding equals the approved source selected by
  traceability; paths are non-empty, project-relative, non-traversing, and
  contain no symlink component; and fields are non-empty text.
- `output_contract`: exactly `design_binding`, `result_path`, and
  `required_fields`. Its binding equals the approved metric/success/failure
  source selected by traceability, and its path is exactly the later-stage-safe
  `experiment/results.json`. This path is disjoint from the approved design
  and all six Stage-10 package outputs.
- `traceability`: an object with exactly `datasets`, `baselines`,
  `split_strategy`, `metrics`, `seeds`, `input_contract`, and
  `output_contract`, mapping every preceding translation field to its approved
  design path. Use only these mappings: `datasets` →
  `method.datasets`; `baselines` → `method.baselines` or `comparators`;
  `split_strategy` → `method.split_strategy`; `metrics` → `metrics`; `seeds`
  → `reproducibility` or `reproducibility.protocol_version`; `input_contract`
  → `evidence_sources` or `method.datasets`; `output_contract` → `metrics`,
  `success_criteria`, or `failure_criteria`.

`main.py` defines `load_config`, `validate_inputs`, `build_plan`, and `main`.
The entry point accepts `--config` and `--dry-run`, loads JSON configuration,
validates declared input paths and schemas, constructs the documented
split/evaluation plan, and invokes `main` from its module guard. The dry run
establishes readiness only; it does not fit a model, evaluate data, or write a
result.

`test_smoke.py` imports and calls all four entry-point functions to check
importability, configuration loading, input-contract validation, plan
construction, and `--dry-run` readiness only. It must not write any artifact,
run research computation, use network access or a subprocess, or generate a
result. `README.md` must state the
approved-design binding, required input preparation, entry point, both exact
commands above, expected later outputs, limitations, and that Stage 10 did not
execute the validation.

`main.py`, `requirements.txt`, and `tests/test_smoke.py` are a closed canonical
scaffold, not agent-authored Python. Obtain their repository-owned content
from `canonical_computational_scaffold()` in
`researchclaw.core.computational_package` and copy each returned UTF-8 string
to its matching project-relative path byte-for-byte. Do not reformat, add a
comment, rename a symbol, change a dependency, add a helper, or otherwise
customize these three files. The helper is the sole authority for canonical
requirements and scaffold content; do not duplicate or infer those bytes from
this prose. All research-specific variation lives only in the
approved-design-bound `experiment/code/config.json`; the manifest records the
resulting canonical file hashes.

The validator compares all three files to this repository-owned scaffold
before semantic acceptance and reports `scaffold_mismatch` for any difference.
It also retains static syntax, capability, reachability, mutation, and PEP 508
checks as defense in depth, but those checks never authorize noncanonical
Python or requirements. Thus aliases, private reexports, alternate control
flow, harmless-looking local strings, variable open modes, and even safe extra
helpers are outside the Stage-10 authoring contract.

## Validate, repair, and stop

After authoring all six files and calculating their manifest hashes, run:

```bash
researchclaw-codex stage validate ROOT --json
```

Validation is static: it checks the approved-design binding, exact file set and
hashes, JSON schemas, Python syntax, prohibited capabilities, requirements,
traceability, and README/manifest command agreement. It does not import or
execute the generated package. If it returns issues, revise only these six
declared outputs using the reported issues and the prepared packet, then run
the same validation command again. Do not create outputs to bypass a failure.

The first Stage-10 `prepare` durably records one immutable typed snapshot of
all authored/data filesystem entries: ordinary directories (including empty
ones), symlinks hashed by link-target bytes, and regular files hashed by
content. Engine-owned state, approvals, and evaluation logs are outside this
authoring snapshot. Repeated prepare calls and Stage-9 invalidation/reapproval
never refresh or discard it. After an upstream producing stage successfully
revalidates, only already-snapshotted entries named by that validation's
verified artifact lineage may transition to their newly verified hashes and
types; no untracked path or directory is absorbed. Static validation permits
only the six declared output files and their necessary parent directories as
additions; it rejects
new empty directories, removed entries, type changes, changed symlink targets,
and byte changes to pre-existing files. A revalidated upstream artifact may
change only through its separately verified durable artifact lineage. Thus a
pre-prepare supplied input remains allowed but cannot be modified during
Stage-10 authoring, and an undeclared path cannot be laundered through
reapproval.

Legacy state migration is conservative. A legacy state encountered before
Stage 10 is explicitly migrated to `not_prepared` and may capture its first
snapshot later. A legacy state already at Stage 10 or beyond without a typed
snapshot is marked `legacy_missing`; prepare and validation refuse to create a
new baseline from its current filesystem. Restoration requires an explicitly
authorized state recovery outside this authoring workflow.

When validation succeeds, run:

```bash
researchclaw-codex resume ROOT --json
researchclaw-codex evaluate ROOT --json
```

Report only the completed `10 / 23` computational-package milestone and its
six declared outputs. The durable state reaches the Stage 11 reporting
boundary, but Stage 11 resource planning is unsupported. Stop before
unsupported Stage 11; do not execute the package, prepare Stage 11, or claim a
validation result. Keep `external_llm_calls` and `nested_agent_processes` at
zero.
