# Agent-authored experiment bridge implementation report

Worktree: `.worktrees/agent-experiment-bridge`; branch:
`fix/agent-experiment-bridge`; requested base: `5bde3cf`.

## Implemented boundary

The new public-flow tests start from synthetic pre-Stage-9 setup, author a
consistent regression design and CSV before approving Stage 9, and then use
normal public prepare/validate/approval/registration transitions. Nothing above
Stage 9 replaces a validated package, rebinds durable artifacts, mocks a
validator, or writes an invented research result.

Stage 10 now declares the alternative complete v2 authoring set before files
are written. Static validation preserves the legacy v1 path and selects v2 only
from integer manifest `schema_version: 2`. V2 permits authored `fit`/`predict`
algorithms while the repository owns input decoding, target isolation, metric
calculation, environment/contract checks, timing and exclusive publication.

The training-mean authored fixture fits 6 from training x=0..5, y=2*x+1 and
produces independently expected held-out MAE 18 arbitrary units. The separately
authored least-squares candidate computes its slope/intercept from train data and
produces held-out MAE 0. The candidate passes the public council/self-test/run/
result-registration sequence and preserves the immutable baseline objects.
Automated council records are explicitly synthetic protocol tests; they do not
constitute live scientific approval. Stage 14 finalization policy is unchanged.

## Exact schema decisions

The exact schema was added to
`docs/superpowers/specs/2026-09-05-agent-experiment-bridge.md` before implementing
its consumers. The manifest exact fields are schema_version, project_id,
design_sha256, validation_type, entry_point, config_path, files. File entries
have exactly path, role, sha256. The eight outputs are manifest, package contract,
metric fixture and code/{README.md,main.py,algorithm.py,config.json,
self_test_config.json}. The manifest hashes the other seven files; normal Stage
10 registration and execution evidence bind the manifest itself.

Contract v2 retains v1 field names and adds algorithm_path and runtime_sha256.
The runtime mapping binds the actual installed agent_experiment.py,
agent_experiment_runtime.py and execution_environment.py source bytes. Version
numbers alone cannot bless changed runtime bytes. Dependency declarations are
empty; network_access, external_llm_calls and nested_agent_processes are closed
literal-false declarations.

Config exact fields are schema_version, project_id, design_sha256,
input_contract, split_strategy, columns, parameters, metrics. There is one
declared project-relative CSV. Columns explicitly map identity, group, split,
target, features. All headers must match those distinct names. Only mae is
supported and its unit must equal the approved design. All four partitions must
be nonempty, identities unique, groups disjoint and numeric values finite.
The algorithm sees numeric training feature/target mappings, feature-only test
mappings, and only the parameters object as config.

The distinct known-answer JSON fixture contains only targets and predictions.
Its self-test config contains schema_version and fixture_path. Self-test runs
the same real repository MAE implementation independently of the scientific
algorithm, compares expected/tolerance, and publishes no report for a wrong
answer. It is intentionally an independent metric oracle, not reuse of the
research input or a fixed passed report.

Candidate local files are code/model.py, code/algorithm.py, config/config.json,
tests/self_test_config.json, tests/self_test_fixture.json, and
package_metadata/{package_contract.json,package_manifest.json}. Their normal
registration manifest binds all seven and canonical provenance now maps the
algorithm to its immutable baseline source. Runtime identity, columns, design,
metric/unit, partition strategy and input contract remain baseline-bound.

## Trusted launch ruling

A focused RED test demonstrated that executing project main.py could import a
newly added shadow researchclaw.py before runtime validation. V2 therefore uses
the exact returned launch form:

```
<verified-interpreter> -P -m researchclaw.core.agent_experiment_runtime <suffix>
```

The runtime verifies canonical wrapper and algorithm hashes before compiling the
validated algorithm. The wrapper remains a bound interface artifact but is never
executed as launch authority. Python -P removes unsafe script/current-directory
import injection; the installed environment and module search configuration must
still be trusted. The controller explicitly agreed to this ruling. Baseline and
candidate preparation both use the same versioned dispatch. V1 argv is unchanged.
Returned baseline self-test/research objects now include explicit cwd, which the
bridge tests use along with their returned interpreter and argv.
The runtime compares the actual flags/module/suffix from `sys.orig_argv` with
the authoritative command. Only argv[0] is normalized to the independently
fingerprinted interpreter: a direct macOS diagnostic showed Python's framework
launcher rewrites it to `Resources/Python.app/Contents/MacOS/Python` even when
the exact prepared `.../bin/python3.11` path was executed. Reconstructing flags
from the expected command would incorrectly accept a direct wrapper launch.
Legacy `ValidatedExperimentPackage` retains exactly its six public dataclass
fields; the v2 subtype overrides only command construction.

Models are traversed before JSON expansion, counting repeated shared objects
again. Limits are 10,000 value/key occurrences, depth 64, 1 MiB cumulative string
bytes, and 1 MiB serialized JSON. The shared-subtree regression proves a compact
16-iteration fit cannot force exponential serialization outside that bound.

## RED/GREEN record

- Initial fixture-only Stage-9 errors (closed metric fields and threshold syntax)
  were corrected before the product RED was accepted.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py`: RED, 1 failed
  at missing `profile_context.agent_regression_v2_outputs` after real Stage-9
  validation/approval.
- `PYTHONPATH="$PWD" pytest -q tests/codex_native/test_agent_experiment_bridge.py`:
  first baseline GREEN, 1 passed in 0.53s.
- Candidate public-flow RED exposed Stage-13's hard-coded legacy output set.
  Version-specific immutable evidence output selection and algorithm provenance
  mapping repaired it. The next candidate fixture issue was noncanonical JSON
  registration bytes and was corrected before registration, never afterward.
- `PYTHONPATH="$PWD" pytest -q tests/codex_native/test_agent_experiment_bridge.py -k public_candidate`:
  candidate GREEN, 1 passed / 13 deselected in 1.87s.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py -k numerical_subset`:
  RED, missing rejection of huge power expressions. Numerical-only arithmetic
  transformation, literal bounded powers and opcode budget repaired this boundary.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py`: intermediate
  GREEN, 27 passed in 4.94s.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py -k project_module_shadow`:
  RED, the synthetic shadow module wrote its marker before validation. Trusted
  module launch plus closed code-tree checks repaired this; GREEN 2 passed /
  28 deselected in 0.46s, including tampered wrapper with no side effect.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py -k model_serialization`:
  RED, 1 failed / 30 deselected, because shared-tree model serialization did not
  raise. Pre-serialization occurrence/depth/string limits repaired it.
- `pytest -q tests/codex_native/test_agent_experiment_bridge.py -k non_authoritative_wrapper`:
  RED, 1 failed / 31 deselected, because executing the wrapper directly could
  publish a self-test. Actual interpreter-argument comparison repaired it.
- During those fixes, an intermediate combined focused run had 10 failed /
  25 passed in 7.35s: nine bridge failures exposed the macOS argv[0] rewrite,
  one was the budget test's error-text regex. The three original broad-run
  failure nodes all passed in that run. The launcher normalization and precise
  budget regex resolved the bridge failures; no legacy test was weakened.
- Final `pytest -q tests/codex_native/test_agent_experiment_bridge.py`:
  **32 passed in 6.28s**. Both public-flow tests execute the exact returned
  interpreter/argv/cwd in child processes; baseline MAE 18, candidate MAE 0.

### Interrupted affected-module batch

Command (one batch only):

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py tests/codex_native/test_computational_package.py tests/codex_native/test_contracts.py tests/codex_native/test_task_packets.py tests/codex_native/test_validation.py tests/codex_native/test_experiment_package_contract.py tests/codex_native/test_resource_planning.py tests/codex_native/test_research_execution.py tests/codex_native/test_refinement.py tests/codex_native/test_refinement_execution.py tests/codex_native/test_stage13_multi_agent_e2e.py tests/codex_native/test_public_docs.py
```

The controller requested graceful SIGINT of owned PID 27130 after prolonged CPU
work in unchanged legacy refinement AST checks. `kill -INT 27130` produced
**3 failed, 726 passed in 907.71s** from 858 collected cases; **129 cases were
not completed**. Pytest then errored while formatting its KeyboardInterrupt
(`TypeError: unsupported operand type(s) for -: 'NoneType' and 'int'`). No full
batch pass is claimed. The interrupted case was the legacy parametrized
`test_register_refinement_result_rejects_schema_metric_runtime_or_provenance_tampering`,
inside existing `_validate_self_test_adapter` / `_nodes_rebind_os_capabilities`.

Failures:

1. `test_experiment_package_contract.py::test_validated_experiment_package_keeps_the_exact_public_field_contract`
   expected exactly six fields, found added `command_prefix`. Fixed by the
   version-specific subclass described above; existing regression now passes.
2. `test_research_execution.py::test_ordinary_event_append_fails_closed_while_registration_is_pending`
   failed at line 355: `assert registration_entered_append.wait(1.0)` returned
   False. The test has a one-second event wait and a two-second release wait;
   timing sensitivity is observed, but load causality is not proven. No timeout
   or production behavior was changed.
3. `test_research_execution.py::test_validate_research_result_rejects_invalid_payload_without_mutation[wrong_contract_hash]`
   expected regex `^research_result_contract_mismatch$`, received
   `execution_prerequisites_changed` from `_load_current_resource_plan` after
   `validate_stage_eleven`. The original output did not expose the underlying
   resource-plan issues. No causal hardware drift/order diagnosis is claimed.

All three nodes passed the isolated focused run (alongside the intermediate
bridge run noted above). To check immediate order effects without another broad
batch, ran this exact predecessor/failure selection:

```
pytest -q tests/codex_native/test_research_execution.py::test_result_mutation_during_success_append_does_not_change_immutable_registration tests/codex_native/test_research_execution.py::test_ordinary_event_append_fails_closed_while_registration_is_pending 'tests/codex_native/test_research_execution.py::test_validate_research_result_rejects_invalid_payload_without_mutation[wrong_contract_id]' 'tests/codex_native/test_research_execution.py::test_validate_research_result_rejects_invalid_payload_without_mutation[wrong_contract_hash]'
```

**4 passed in 8.94s**. This rules out a deterministic immediate-predecessor
reproduction in that run, not longer-range contamination or load effects.
The causes of failures 2 and 3 remain unresolved concerns for independent review.

### Final focused legacy and documentation verification

```
pytest -q tests/codex_native/test_stage13_multi_agent_e2e.py tests/codex_native/test_refinement_execution.py::test_context_bound_refinement_argv_produces_registrable_result tests/codex_native/test_refinement_execution.py::test_candidate_self_test_uses_verified_absolute_launcher_and_candidate_cwd tests/codex_native/test_refinement_execution.py::test_prepare_refinement_run_reserves_exact_authoritative_contract_without_execution tests/codex_native/test_public_docs.py tests/codex_native/test_plugin_package.py
```

**45 passed in 42.01s**. The three named legacy cases cover authoritative
research argv/result registration, self-test interpreter/cwd, and non-executing
run preparation. Public-doc tests and package metadata checks are included.
Earlier metadata verification caught a README boundary-marker mismatch (1 failed,
5 passed); restoring the established marker with an accurate qualification made
the standalone metadata run 6 passed in 0.03s.

`/opt/homebrew/opt/python@3.11/bin/python3.11 /Users/jspark/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/researchclaw`
reported `Skill is valid!`. Skill-creator/reference-skill guidance kept the edit
tied to the demonstrated Stage-10 authoring failure and executable API contract;
the invocation policy is unchanged. No pressure-test campaign or skill redesign
was introduced.

`ruff check researchclaw/core tests/codex_native/test_agent_experiment_bridge.py`
and `git diff --check` pass. Only the three new Python files were run through
`ruff format`; existing files retain their formatting outside changed snippets.

No duplicated full-tree suite was used. After the single interrupted affected
batch, verification was limited to the new bridge, observed failure cases,
named dispatch regressions, Stage-13 E2E and documentation/metadata checks.

## Files and review notes

- New agent_experiment.py: closed schema and pure AST validation, bounded numeric
  arithmetic, CSV decoding, train isolation and actual MAE.
- New agent_experiment_runtime.py: trusted module entry, existing protocol/context
  binding, OS-attested environment identity, real self-test/result production and
  exclusive publication.
- computational_package.py, contracts.py, task_packets.py, validation.py:
  explicit v2 authoring/discriminator/output validation, with unchanged v1 rules.
- experiment_package_contract.py and research_execution.py: versioned launch and
  static validation dispatch; existing registration/approval transactions reused.
- refinement.py and refinement_execution.py: v2 baseline output/provenance and
  immutable declaration checks, same launch dispatch and existing transactions.
- New bridge test module: public baseline/candidate, train isolation, safety and
  identity negatives. Existing test helpers were not rewritten or used to replace
  Stage-10 packages.
- README, computational-package/refinement/resource-planning references and two
  narrowly scoped SKILL.md workflow lines explain the new executable contract and
  retained legacy scaffold. Invocation and approval policy remain intact.

Limitations: this is a bounded scalar-regression interface, not a general Python
sandbox, scientific-validity guarantee, general scheduler, automatic model
selector, provider client or Stage-14 analysis implementation. No new dependency,
installation, production project mutation, deployment, merge or push occurred.

## Controller installed smoke handoff

The source-tree bridge test fixture sets child PYTHONPATH to the parent directory
of the actually imported researchclaw package, retaining exact returned argv and
interpreter. When the parent import is the isolated site-packages installation,
the children also use that installation. Assert the parent import first and run
from a copied tests tree outside the repository.

Copy tests/ (or at minimum bridge test, helpers.py, test_refinement.py,
test_stage13_multi_agent_e2e.py and its imported test helpers, package __init__.py
files, plus tests/codex_native/fixtures/). Core researchclaw data are wheel package
resources. The controller may replace only helpers.run_cli with the real installed
`sys.executable -m researchclaw.codex.cli` subprocess adapter; no validator or
post-approval state substitution is needed.

## Review fix round 1 (base c603cc6)

The independent review demonstrated recursive collection comparisons can bypass
the authored opcode budget: 28 bounded iterations build independent shared
binary lists, then `a == b`, `min(a, b)` or `max([a, b])` performs exponential
C-level recursive work before model serialization. Confirmed with three
subprocess regressions, each guarded by a three-second parent-owned watchdog:

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py -k recursive_collection_comparisons
```

RED: **3 failed, 33 deselected in 9.32s**, each with
`subprocess.TimeoutExpired` after three seconds. Subprocess cleanup terminated
each probe; the pytest parent did not hang.

The AST transformer now wraps comparison operands in a finite-numeric-scalar
guard before native comparison, retaining native chained short-circuit behavior.
Authored min/max dispatch to bounded wrappers: finite scalar positional values,
or a list/tuple/generator of finite scalars, at most 100,000 items. Recursive
collections fail before comparison. A positive numerical comparison/extrema test
preserves useful supported behavior. Spec and reference document the restriction.

The interpreter review finding was also verified: copying a standalone binary
is not a portable runnable environment (controller's installed Python 3.13
failed importing encodings before reaching application code). The negative now
creates a pip-free copied venv with stdlib home and system-site access, verifies
`import encodings, researchclaw` succeeds and prints `ready`, and only then
replaces the interpreter slot of the exact prepared argv. There are no installs.

That realistic fixture exposed a genuine baseline self-test identity gap:
`prepare_experiment_self_test` is read-only, and the runtime recomputed its
environment from the substituted interpreter. Intermediate full bridge run:
**1 failed, 35 passed in 6.66s**, with the alternate application returning 0 and
publishing a report instead of rejecting. The comparison regressions passed.

Controller approved the smallest v2-only correction: baseline preparation adds
`--self-test-environment <prepared fingerprint>` to the authoritative launch,
after the closed authored suffix. The runtime requires/matches it before report
publication. It is not an authored schema field and is not placed in the package
`self_test.argv_suffix`. Preparation still performs no writes. Candidate context
already carries its environment identity and remains unchanged; legacy commands
remain unchanged. The alternate-interpreter regression now requires the exact
application message `execution environment changed`, not arbitrary startup errors.

`pytest -q tests/codex_native/test_agent_experiment_bridge.py` then reported
**36 passed in 8.60s** on source Python 3.11, including normal public baseline
and candidate self-tests/results and the runnable alternate-interpreter negative.

A focused legacy response compatibility check found the original bridge commit
had unconditionally added cwd to the v1 self-test JSON response:

```
pytest -q tests/codex_native/test_cli.py::test_prepare_self_test_cli_returns_complete_authoritative_argv tests/codex_native/test_public_docs.py
```

RED: **1 failed, 34 passed in 0.50s**; exact legacy response-key assertion at
test_cli.py:1596 reported extra `cwd`. With controller approval, explicit cwd
metadata is now emitted only for v2 baseline self-test/research preparation;
legacy JSON shape is preserved. This does not alter the launch or authority.

Final source verification:

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py tests/codex_native/test_cli.py::test_prepare_self_test_cli_returns_complete_authoritative_argv
```

**37 passed in 7.29s** (36 bridge cases plus the exact legacy CLI regression).
`ruff check researchclaw/core/agent_experiment.py researchclaw/core/agent_experiment_runtime.py researchclaw/core/experiment_package_contract.py researchclaw/core/research_execution.py tests/codex_native/test_agent_experiment_bridge.py`
and `git diff --check` exited 0. Skill `quick_validate.py skills/researchclaw`
again reported `Skill is valid!` after the narrowly updated API reference.

The controller will reinstall the final commit into its isolated Python 3.13
environment and repeat the real CLI bridge; no source/installed Python 3.13 pass
is claimed here. The earlier 129 uncompleted broad-batch cases and two unexplained
research-execution failures remain explicit limitations. No broad suite was
repeated, and no deployment, provider access or approval-policy change occurred.

## Review fix round 2: interpreter negative portability (base f42353c)

Controller's isolated Python 3.13 real-CLI run reported **35 passed, 1 failed in
24.55s**. The alternate-interpreter probe succeeded, and the actual trusted
runtime rejected with `ValueError: execution_environment_unavailable`, rather
than the test's sole accepted `ValueError: execution environment changed`.
There was no publication. This was an inspector rejection, not Python startup
failure; no production inspection relaxation was warranted.

Narrow source reproduction with controller Python 3.13 initially also exposed a
fixture dependency difference: a nested venv's system-site-packages does not
include its parent test venv's packages. The runtime import failed on `packaging`
even though the weak `import researchclaw` probe succeeded. Original copied-venv
probe: **1 failed in 1.05s**; experimental symlink venv: **1 failed in 0.42s**,
both on missing packaging. These failures were not accepted as valid negatives.

With parent dependency paths explicitly retained, direct inspector diagnostics
proved the symlink venv is recognized but shares the original fingerprint
(`ff17c648...`) because its resolved interpreter and process image are identical.
Only launcher paths differ. It cannot exercise a changed-interpreter fingerprint
under the existing identity design. A copied uv Python 3.13 interpreter imports
the complete runtime, then fails the existing OS-image check in
`execution_environment.py::_current_runtime_paths` (line 282), surfaced through
`inspect_execution_environment`. A byte-identical symlink alias shares identity;
an actual distinct copied interpreter is rejected. No new launcher identity
semantics or flag was introduced.

Controller approved the minimal portable fixture-only correction:

- Keep the copied, pip-free runnable venv.
- Retain the parent purelib/platlib paths only in the alternate child's environment;
  do not alter the returned command or global runtime environment.
- Probe `import encodings, researchclaw.core.agent_experiment_runtime` before
  attempting the prepared self-test, ensuring its dependencies actually import.
- Require the final traceback line to be exactly one of
  `ValueError: execution environment changed` or
  `ValueError: execution_environment_unavailable`, and require trusted-runtime
  traceback evidence. For unavailable, additionally require
  `execution_environment.py` and `in inspect_execution_environment` evidence.
  Arbitrary startup/import exceptions are not accepted. Require no report.

Verification (only the amended case):

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py::test_changed_interpreter_cannot_publish_self_test
```

Source Python 3.11: **1 passed in 1.05s**.

```
PYTHONPATH="$PWD" /private/tmp/researchclaw-agent-bridge-installed.sduku3/venv/bin/python -m pytest -q tests/codex_native/test_agent_experiment_bridge.py::test_changed_interpreter_cannot_publish_self_test
```

Source package on controller Python 3.13: **1 passed in 1.00s**. This is not an
installed-wheel full-bridge claim; controller owns that verification.
`ruff check tests/codex_native/test_agent_experiment_bridge.py` and
`git diff --check` exited 0. Only test fixture and this report changed.
Earlier partial-suite limitations remain unchanged; no broad suite was rerun.

## Final review wave: implicit dictionary keys (base 877af8b)

Independent review identified the same bounded-runtime issue at implicit Python
dictionary hashing/equality, not explicit Compare: allowed shared nested tuple
keys could require exponential C work on construction or lookup. This wave is
limited to those dictionary/index paths, not a general sandbox expansion.

RED command:

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py -k 'recursive_dictionary_keys or dictionary_unpacking'
```

**5 failed, 38 deselected in 12.29s**. Four three-second subprocess watchdogs
expired on shared tuple keys built in 32 bounded training iterations:

- `ignored = {a: 1}` (implicit tuple hashing).
- `ignored = {a: 1, b: 2}` (hashing plus possible collision equality).
- `ignored = {0: 1}[a]` (lookup hashing).
- `for table[a] in train_rows` (permitted loop-target Store hashing).

The fifth failure was static validation accepting `ignored = {**config}`;
the chosen deliberate subset prohibits dictionary unpacking. The watchdogs
terminated only their own child probes, keeping the test runner responsive.

Implemented `_index_key` before every authored Dict key and Subscript index:
only finite numeric scalars or strings of at most 65,536 characters can enter
implicit hashing/equality. Tuple/collection keys are rejected in constant-shape
type checks before Python sees them as keys. The Subscript transformation covers
both Load and Store contexts, including allowed loop/comprehension assignment
targets. Direct assignment statements already require local Name targets and
remain prohibited; no new mutation capability was added. Dict unpacking is
rejected during static validation. Dict comprehensions/calls/attribute methods
remain outside the existing allowed syntax/call set. Returned model dictionaries
still pass the existing JSON string-key check and serialization budget.

Positive tests cover numeric temporary dictionary keys, string-keyed model
serialization, parameter indexing, nested train-row indexing and real prediction
from a model dictionary. A direct dictionary-assignment rejection test preserves
the existing static rule. Spec/reference document these precise boundaries;
tuples remain values, not keys. Production changes are confined to
`agent_experiment.py`; no execution, registration, approval or legacy schema
behavior changed.

Final GREEN commands/results:

```
pytest -q tests/codex_native/test_agent_experiment_bridge.py
```

**43 passed in 7.04s** on source Python 3.11. This includes the complete real
public baseline/candidate bridge, prior comparison watchdogs, new key watchdogs,
unpacking rejection, model-dictionary positive and alternate-interpreter test.

```
pytest -q tests/codex_native/test_public_docs.py
```

**34 passed in 0.07s**.
`ruff check researchclaw/core/agent_experiment.py tests/codex_native/test_agent_experiment_bridge.py`
and `git diff --check` exited 0. Skill `quick_validate.py skills/researchclaw`
reported `Skill is valid!`; only the directly relevant API reference changed.

Controller owns the single scoped re-review and isolated installed verification
after this commit. The earlier 129 uncompleted broad-batch cases and two
unexplained research-execution failures remain limitations, not claimed fixed.
No broad suite, installation, deployment, provider access or subagent run occurred.
