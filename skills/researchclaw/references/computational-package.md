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
  config, with `design_binding`, a project-relative `result_path`, and a
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
  `overlap_policy`. The binding equals the approved split strategy; `groups`
  contains each of `train`, `validation`, `calibration`, and `test` exactly
  once; `isolation_key` is non-empty text; and `overlap_policy` is `disjoint`.
- `seeds`: exactly `design_binding` and `values`; the binding equals the
  approved reproducibility source selected by traceability and `values` is a
  non-empty list of JSON integers.
- `input_contract`: exactly `design_binding`, `required_paths`, and
  `required_fields`. Its binding equals the approved source selected by
  traceability; paths are non-empty, project-relative, and non-traversing; and
  fields are non-empty text.
- `output_contract`: exactly `design_binding`, `result_path`, and
  `required_fields`. Its binding equals the approved metric/success/failure
  source selected by traceability, and its path is project-relative and
  non-traversing.
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
split/evaluation plan, and invokes `main` from its module guard. It must use
only project-relative paths and must not download
data, use a network client, invoke an LLM or remote/nested agent, run a shell
or subprocess, use `eval`/`exec`, manufacture synthetic results, or silently
replace absent inputs. The dry run establishes readiness only; it does not fit
a model, evaluate data, or write a result.

`test_smoke.py` imports and calls all four entry-point functions to check
importability, configuration loading, input-contract validation, plan
construction, and `--dry-run` readiness only. It must not write any artifact,
run research computation, use network access or a subprocess, or generate a
result. `README.md` must state the
approved-design binding, required input preparation, entry point, both exact
commands above, expected later outputs, limitations, and that Stage 10 did not
execute the validation.

`requirements.txt` contains only valid PEP 508 runtime requirements with an
exact (`==`), compatible (`~=`), or bounded lower-and-upper version range.
Requirement-file options, direct references, URLs, local paths, and VCS
sources are forbidden even when their text resembles a version pin. Do not
include external LLM SDKs, remote-agent frameworks, network/download clients,
or unbounded dependencies. In particular, prohibited imports and
distributions include OpenAI, Anthropic, Google Generative AI, requests,
httpx, urllib, socket, FTP/HTTP clients, subprocess and multiprocessing,
LiteLLM, LangChain, LlamaIndex, AutoGen, CrewAI, Pydantic AI, Semantic Kernel,
Haystack, `haystack-ai`, and `farm-haystack`.

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
