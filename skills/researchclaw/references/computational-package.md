# Stage 10 — Computational Package

Use this reference only when the prepared packet's `stage_id` is `10`. Read
the complete approved `experiment/design.json`; its hash-bound approval is the
authority for this stage. Stage 10 supports only
`validation_type: computational`. A `policy_evidence` or `laboratory` design
is unsupported at this stage: do not create a package for it. Do not download
data, run training or evaluation, collect results, invoke an external LLM, or
start another agent process. Codex authors but does not execute the package;
it will statically validate the authored files.

## Agent-authored scalar regression (v2)

For an executable scalar regression experiment, choose integer `schema_version: 2`
in the authored manifest. The prepared packet declares the complete alternative
file set in `profile_context.agent_regression_v2_outputs`, the exact wrapper in
`agent_regression_v2_wrapper`, and current runtime hashes in
`agent_regression_v2_runtime_sha256`. Write only that eight-file set. Do not mix
v1 and v2 layouts or rewrite already validated packages to switch versions.

The eight outputs are `experiment/package_manifest.json`,
`experiment/package_contract.json`, `experiment/self_test_fixture.json`, and
`experiment/code/{README.md,main.py,algorithm.py,config.json,self_test_config.json}`.
The manifest hashes every other file. Its exact fields are `schema_version`,
`project_id`, `design_sha256`, `validation_type`, `entry_point`, `config_path`,
and `files`; each file entry has `path`, `role`, `sha256`.

Copy the packet's exact wrapper to `main.py`. Author scientific code only in
`algorithm.py`, defining `fit(train_rows, config)` followed by
`predict(model, feature_rows, config)`. Use local assignments, arithmetic,
indexing, comprehensions/for loops, conditionals, and `sum`, `len`, `min`, `max`,
`abs`. Imports, attribute access, dynamic calls, helper functions, global work,
file/process/network access and unbounded loops are rejected. Arithmetic is
finite numeric only; powers require integer literal exponents from 0 to 8.
An instruction budget bounds authored evaluation. Models allow at most 10,000
value/key occurrences, depth 64, 1 MiB cumulative string bytes and 1 MiB serialized
JSON; repeated shared containers count again before serialization. This is a
restricted numerical interface, not a general Python sandbox or a scientific
validity check.

The authoritative v2 argv launches the installed runtime with
`<verified interpreter> -P -m researchclaw.core.agent_experiment_runtime`.
It validates package bytes before executing the algorithm. The canonical wrapper
remains a bound interface artifact and is not the launch authority. Keep the
installed environment and module search configuration trusted; do not prepend
the project to `PYTHONPATH` or substitute a project module for this runtime.
The runtime checks the actual interpreter flags/module and argument suffix, so
executing the wrapper directly is not equivalent to executing the returned argv.

The runtime passes only training rows to `fit`. Those rows have numeric features
and the target; prediction rows have features only. The `config` argument is
only the `parameters` object. Return a JSON model and one finite prediction per
test row. For example, a training-mean baseline is:

```python
def fit(train_rows, config):
    return sum(row["y"] for row in train_rows) / len(train_rows)

def predict(model, feature_rows, config):
    return [model for row in feature_rows]
```

Research config exact fields are `schema_version: 2`, `project_id`,
`design_sha256`, `input_contract: {required_paths: [<one CSV path>]}`,
`split_strategy: {isolation_key: <identity column>, overlap_policy: disjoint,
groups: [train, validation, calibration, test]}`, `columns`, `parameters`, `metrics`.
Columns are explicit `{identity, group, split, target, features: [<names>]}`;
all names must be distinct and CSV headers must match exactly. Unique cells,
disjoint groups, four nonempty partitions and finite numeric data are required.
`metrics` is exactly `[{name: mae, unit: <approved design unit>}]`.
There is no inferred column mapping, synthetic data fallback, or RMSE support.

The v2 package contract uses exactly `schema_version`, `entry_point`,
`algorithm_path`, `config_path`, `result_path`, `metrics`, `self_test`, `execution`,
`dependencies`, `prohibitions`, and `runtime_sha256`. Paths use the eight-file
layout above; `result_path` is `experiment/results.json`. Metrics add
`implementation: researchclaw.core.agent_experiment:mean_absolute_error` to the
config metric. Dependencies are `[]`; prohibitions are exactly `network_access`,
`external_llm_calls`, `nested_agent_processes`, each literal `false`.
Copy the packet's runtime mapping: changed repository runtime bytes invalidate
the approved package even if the installed distribution version is unchanged.

`execution` is `{argv_suffix: [--config, experiment/code/config.json]}`.
`self_test` is `{argv_suffix: [--config, experiment/code/self_test_config.json,
--self-test], fixture_path: experiment/self_test_fixture.json,
expected_metrics: [{name: mae, expected: <known value>, tolerance: <nonnegative>}]}`.
The self-test config is exactly `{schema_version: 2, fixture_path:
experiment/self_test_fixture.json}`. The independent fixture is exactly
`{targets: [...], predictions: [...]}`. For example `[1,3]` versus `[1.5,2.5]`
has known MAE `0.5`. This executes the same metric implementation on independent
fixture values, not the research data or a prewritten success report.

Run normal `stage validate` after authoring. Stage 11 still authors only the
resource plan. At Stage 12, obtain `experiment prepare-self-test`, run its exact
returned `argv` in returned `cwd`, and register with `--confirm-self-test`.
Explicit execution approval is then required before `execution prepare-run`.
Run its exact returned `argv` in returned `cwd` and register the produced result
with `--confirm-research-result`. Both publications refuse overwrite. Stage 10
validation imports or executes no authored Python. CLI preparation never runs
the experiment; execution occurs through the explicitly handed-off command.

## Legacy v1 static scaffold

The remainder of this reference describes the retained v1 path only. Its fixed
`run_experiment` is unimplemented; it is a planning scaffold, not the executable
agent-authored bridge. Existing v1 validation and approved evidence are retained.
For v1, write exactly these six packet-declared outputs and no other artifacts:

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
  "dry_run": "<verified-absolute-interpreter> experiment/code/main.py --config experiment/code/config.json --dry-run",
  "smoke_test": "<verified-absolute-interpreter> -m pytest experiment/code/tests/test_smoke.py -q"
}
```

These are human-readable package descriptions, not execution authority. The
Stage-12 contract stores an authoritative argv JSON array and binds its first
item to a verified absolute interpreter. Never replace it with a `python`
alias or reconstruct it from a display string.

Before approval, obtain the self-test argv only with `researchclaw-codex
experiment prepare-self-test ROOT --json`; execute its returned `argv` and use
its returned `registration_argv` for the exact `experiment register-self-test`
step.

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
  For an already-approved legacy design whose traced split strategy is a
  string, preserve that string exactly as `design_binding`. Select one atomic
  `isolation_key` from `cell_id`, `batch_id`, `condition_id`, `source_id`, or
  `dataset_id`. The approved string must contain the exact `cell_id` token for
  `cell_id`; it may contain either the selected key or its closed legacy alias
  (`batch`, `condition`, `source`, or `dataset`) for each corresponding `_id`
  key.
  The approved string may mention multiple candidates, but the selected config
  value must be one key, not an invented key such as `row_id` or a composite.
  Token recognition uses an NFKC-normalized inspection copy and ASCII
  identifier boundaries, so compatibility-width text and attached Korean
  particles are accepted. A format character or combining mark anywhere in
  the approved string disables this compatibility path. The `design_binding`
  still preserves the original string exactly; do not rewrite the approved
  design to perform this legacy translation.
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

The same fixed entry point is the bounded Stage 12 runner when invoked without
`--dry-run`. Stage 10 never invokes that path. After `prepare-run`, the user runs
the exact returned authoritative argv outside ResearchClaw; the entry point recomputes and
checks the execution contract and result template, streams and verifies package
and input bindings, enforces the declared prohibitions and resource budget, and
exclusively creates `experiment/results.json`.

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
snapshot is marked `legacy_missing`; the default remains fail-closed and plain
prepare refuses to create a baseline from its current filesystem. For an
operator-reviewed legacy project that is currently at Stage 10 and has not
started Stage-10 authoring, explicitly run:

```bash
researchclaw-codex stage prepare ROOT --establish-legacy-baseline --json
```

This opt-in is valid only for `legacy_missing` Stage-10 state. It refuses the
migration if any declared package output, any `experiment/code` path, any
notebook, or any result/download-like artifact exists. On success it captures
the typed, content-hashed baseline once, appends a durable
`legacy_stage_10_baseline_established` audit event, and returns the normal task
packet. Never use this option to bless a project where Stage-10 authoring may
already have begun.

Recovery preserves every published partial
quarantine temp and uses a fresh inode instead of writing it; a complete
read-only candidate may be verified without mutation. The adversarial release
gate verifies this guarantee.

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
