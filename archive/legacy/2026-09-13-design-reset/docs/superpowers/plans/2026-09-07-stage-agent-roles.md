# Stage Agent Roles A Implementation Plan

> 아카이브: 이전 단계 구조 또는 철회한 제안의 개발 이력이다. 새 개발의 작업 지시로 사용하지 않는다. [현재 설계 정리](../../../../../../docs/superpowers/specs/2026-09-13-pilot-autonomous-research-design.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a validated, bundled, read-only description of stage 1–15 research roles without changing research execution or approval behavior.

**Architecture:** A pure core module validates a closed JSON catalog and returns a fresh stage description. A projectless CLI command exposes that description. Skill guidance explains the separation between recommended roles, actual submissions, and verified agent execution.

**Tech Stack:** Python >=3.11, standard-library JSON/pathlib, existing argparse CLI, pytest, hatchling packaging. No new runtime dependency.

**Spec:** [Approved design](../specs/2026-09-07-stage-agent-roles-design.md), implementation unit A only. Baseline main: `1264553`.

## Global Constraints

- `schema_version=1`, `protocol_version=1`, `activation="guidance_only"`.
- Support stages 1–15 only. CLI errors use stderr and exit 2; successful JSON is exactly one stdout value.
- No project argument/loading, state/file/event/approval mutation, agent launch, application cache, external service initialization, API key or model/provider configuration.
- No modifications to TaskPacket, ProjectState, existing artifact schemas, registration, approval, recovery, evidence hashes or council rules.
- Preserve stage 13's existing minimum-two matching recommendation quorum, stage 15's three-way agreement, and stage 14's analysis synthesis rather than direction voting.
- Native Codex agents perform judgments; programmatic checks do not establish scientific validity or independence.
- A does not create early-stage council artifacts, migrate projects, rerun experiments, or implement stage 16. B–E require their own designs.
- No live tool/plugin replacement, main merge or GitHub push in this implementation unit without user authorization.
- Use apply_patch for source/document edits. Do not create uv.lock. Do not run concurrent uv operations during environment-sensitive tests.

## Files and boundaries

| File | Responsibility |
| --- | --- |
| `researchclaw/core/agent_roles.py` (new) | Read, validate and return catalog; standard library only |
| `researchclaw/core/data/agent_roles.json` (new) | Fifteen explicit stage descriptions with concrete role questions |
| `tests/codex_native/test_agent_roles.py` (new) | Closed schema, mappings, content coverage and mutation isolation |
| `researchclaw/codex/cli.py` (edit) | Parser entry, projectless dispatch, non-JSON rendering |
| `tests/codex_native/test_cli.py` (edit) | CLI output, failure and read-only behavior |
| `skills/researchclaw/references/agent-roles.md` (new) | Guidance boundaries and use of roles |
| `skills/researchclaw/SKILL.md` (edit) | Short reference link; retain existing protocols verbatim |
| `tests/codex_native/test_plugin_package.py` (edit) | Reference and bundled-data checks |

## Execution setup

- [ ] Resolve the user's execution/isolation choice. Follow using-git-worktrees before creating an isolated worktree; retain existing worktrees and acceptance projects.
- [ ] Check `git status --short --branch`, ancestor instructions, and the approved spec in the selected checkout.
- [ ] Run a bounded baseline before edits:

```sh
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' python -m pytest tests/codex_native/test_plugin_package.py tests/codex_native/test_task_packets.py -q
```

Expected: all selected tests pass. Record counts; report preexisting failures before proceeding. Do not replace this with the roughly twelve-minute full suite at every task.

### Task 1: Versioned catalog and pure validation/access API

**Files:** Create core module, catalog and `test_agent_roles.py` listed above.

**Interfaces:**

- Consumes: packaged `researchclaw/core/data/agent_roles.json` containing a JSON list of exactly fifteen output-shaped descriptions. Using the output shape directly avoids a second envelope/schema.
- Produces: `describe_stage_roles(stage_id: int) -> dict[str, object]`.
- Internal validation seam: `_validate_catalog(raw: object) -> dict[int, dict[str, object]]`. Raises `ValueError("agent_roles_catalog_invalid")` on invalid data. It is not a project registration API.
- Unsupported public stage input raises `ValueError("agent_roles_stage_unsupported")`; reject bool, float and string inputs, not merely out-of-range integers.
- Read the file each call; never retain mutable returned objects. No caching is needed for fifteen small records.

- [ ] Write the following RED contract tests before implementing:

```python
import copy
import json
from pathlib import Path
import pytest
from researchclaw.core import agent_roles

CATALOG = Path(agent_roles.__file__).parent / "data" / "agent_roles.json"
FIELDS = {"schema_version", "stage_id", "protocol_version", "activation",
          "mode", "roles", "existing_protocol"}
ROLE_FIELDS = {"role_id", "responsibility", "required_questions",
               "judgment_criteria", "authority_limits"}
JUDGES = {"domain", "methodology", "critical_reproducibility", "coordinator"}

@pytest.mark.parametrize("stage", range(1, 16))
def test_stage_description_contract(stage):
    result = agent_roles.describe_stage_roles(stage)
    assert set(result) == FIELDS
    assert result["stage_id"] == stage
    assert result["schema_version"] == result["protocol_version"] == 1
    assert result["activation"] == "guidance_only"
    mode = ("work_and_verify" if stage in {4, 6, 11, 12} else
            "implementation_council" if stage in {10, 13} else "judgment_council")
    expected = ({"worker", "verifier"} if mode == "work_and_verify" else
                JUDGES | {"implementation"} if mode == "implementation_council" else JUDGES)
    assert result["mode"] == mode
    assert {r["role_id"] for r in result["roles"]} == expected
    protocol = {12: "user_execution_handoff", 13: "registered_refinement_council",
                14: "registered_analysis_council", 15: "registered_decision_council"}
    assert result["existing_protocol"] == protocol.get(stage, "single_author_validation")
    for role in result["roles"]:
        assert set(role) == ROLE_FIELDS
        assert role["responsibility"].strip()
        for key in ("required_questions", "judgment_criteria", "authority_limits"):
            assert role[key] and all(isinstance(s, str) and s.strip() for s in role[key])

@pytest.mark.parametrize("stage", [0, 16, 23, -1, True, 7.0, "7", None])
def test_unsupported_stage(stage):
    with pytest.raises(ValueError, match="^agent_roles_stage_unsupported$"):
        agent_roles.describe_stage_roles(stage)

def test_returned_nested_data_does_not_contaminate_next_read():
    original = agent_roles.describe_stage_roles(7)
    changed = agent_roles.describe_stage_roles(7)
    changed["roles"][0]["required_questions"].append("mutation")
    changed["roles"][0]["responsibility"] = "mutation"
    assert agent_roles.describe_stage_roles(7) == original

@pytest.mark.parametrize("field,value", [
    ("schema_version", 2), ("schema_version", True), ("protocol_version", 2),
    ("activation", "enforced"), ("mode", "automatic"), ("stage_id", True),
    ("existing_protocol", "registered_analysis_council"), ("unknown", "x"),
])
def test_invalid_stage_fields(field, value):
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw[0][field] = value
    with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
        agent_roles._validate_catalog(raw)

@pytest.mark.parametrize("field,value", [
    ("role_id", "invented"), ("responsibility", " "), ("responsibility", None),
    ("required_questions", []), ("required_questions", [" "]),
    ("required_questions", "not a list"), ("judgment_criteria", []),
    ("judgment_criteria", [4]), ("authority_limits", []), ("unknown", "x"),
])
def test_invalid_role_fields(field, value):
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw[0]["roles"][0][field] = value
    with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
        agent_roles._validate_catalog(raw)

def test_duplicate_missing_and_malformed_catalog_entries():
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    duplicate_role = copy.deepcopy(raw)
    duplicate_role[0]["roles"].append(copy.deepcopy(raw[0]["roles"][0]))
    duplicate_stage = copy.deepcopy(raw)
    duplicate_stage[-1] = copy.deepcopy(raw[0])
    missing_field = copy.deepcopy(raw)
    del missing_field[0]["roles"][0]["authority_limits"]
    wrong_mode = copy.deepcopy(raw)
    wrong_mode[0]["mode"] = "work_and_verify"
    for invalid in (None, {}, [], raw[:-1], raw + [raw[0]], [None] * 15,
                    duplicate_role, duplicate_stage, missing_field, wrong_mode):
        with pytest.raises(ValueError, match="^agent_roles_catalog_invalid$"):
            agent_roles._validate_catalog(invalid)
```

- [ ] Run RED:

```sh
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' python -m pytest tests/codex_native/test_agent_roles.py -q
```

Expected initial failure: missing `agent_roles` module. Confirm the failure is not a dependency/environment issue.

- [ ] Implement the validator with explicit type checks before indexing and `set()` comparisons. The following lookup functions define the mapping shared by validator and loader (tests keep their independently specified expectations):

```python
def _mode(stage_id: int) -> str:
    if stage_id in {4, 6, 11, 12}:
        return "work_and_verify"
    if stage_id in {10, 13}:
        return "implementation_council"
    return "judgment_council"

def _protocol(stage_id: int) -> str:
    return {12: "user_execution_handoff", 13: "registered_refinement_council",
            14: "registered_analysis_council", 15: "registered_decision_council"}.get(
                stage_id, "single_author_validation")

def describe_stage_roles(stage_id: int) -> dict[str, object]:
    if type(stage_id) is not int or not 1 <= stage_id <= 15:
        raise ValueError("agent_roles_stage_unsupported")
    path = Path(__file__).parent / "data" / "agent_roles.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _validate_catalog(raw)[stage_id]
```

Validation order: raw is list of length15; each stage is a dict with exactly FIELDS; numeric versions are exact int1; stage exact int1–15 and unique; activation literal; mode equals `_mode(stage)`; protocol equals `_protocol(stage)`; roles nonempty list; every role is dict with exactly ROLE_FIELDS; ID is string and unique; responsibility nonblank string; each of three list fields nonempty list of nonblank strings; collected IDs equal the exact expected set for mode. Finally verify stage keys equal `set(range(1,16))`. Raise the specified ValueError at each failed predicate, not accidental TypeError/KeyError. Return the indexed descriptions only after validating the entire catalog.

- [ ] Author explicit catalog records. Use English prose matching existing role identifiers and CLI style. Each role has at least two stage-specific questions and one substantive criterion, plus authority limits. Do not copy one generic question to all stages. The required coverage is:

| Stage | Domain/worker emphasis | Methodology/verifier emphasis | Critical emphasis |
| --- | --- | --- | --- |
| 1 | User requirement vs assumption; value and non-goals | Feasible success criteria and resources | Unsupported assumptions and alternative objectives |
| 2 | Relationships between questions | Alternative decompositions and causal structure | Missing causes and confounding |
| 3 | Domain terminology and synonyms | Reproducible search query and coverage | Search/publication bias |
| 4 | Source/title/identifier match, duplicates and access failures | Independently crosscheck identifiers and collection completeness; collection is not screening | Not a council |
| 5 | Include/exclude rationale and borderline relevance | Methodological fit and consistent criteria | Disconfirming sources and selection bias; preserve user approval |
| 6 | Extract claims, values and conditions with locations | Crosscheck original observation vs author interpretation vs agent inference | Not a council |
| 7 | Agreement, conflict and gaps | Evidence strength and comparability | Competing explanations; source count does not establish a conclusion |
| 8 | Domain value and candidate rationale | Falsifiability and discriminating observations | Rejection conditions and competing hypotheses |
| 9 | Approved objective and controls | Splits, leakage, metrics and analysis plan | Failure criteria, reproducibility, budget and user approval |
| 10 | Approved design vs code | Fit/predict isolation and metric implementation | Static validity does not establish scientific adequacy |
| 11 | Grounded resource estimates and input readiness | Feasibility and alternatives within approved scope | Not a council |
| 12 | Approved execution and result correspondence | Missing/failure records and registration boundary | Not a council |
| 13 | Improvement rationale and candidates | Bounded allowed changes and fair comparison | Stop criteria, dissent and preserved budget |
| 14 | Hypothesis assessment within evidence | Observation/calculation/interpretation distinction | Alternative explanations, uncertainty and reproducibility limits |
| 15 | Proceed/refine/pivot rationale and claim scope | Readiness and missing evidence | Unresolved issues; mandatory disclosure is not unfinished work |

For each council coordinator, ask which stage-specific conclusions conflict and which evidence resolves or leaves them unresolved. Require a faithful summary of conclusion, evidence, differences, limits and next action; non-voting, no fabricated responses or consensus. Stage13/15 coordinator criteria explicitly preserve their different existing quorum policies; stage14 has no direction vote.

For stage10/13 implementation role, ask which approved design/change authorizes each code edit and which checks demonstrate correspondence. Prohibit self-evaluation/voting/approval and unapproved execution; stage10 explicitly does not execute experiments. Worker cannot approve its own artifact; verifier must be independent. Stage12 support cannot replace user execution confirmation. All roles use packet-authorized inputs/tools, distinguish observed/calculated/inferred/unknown evidence, and cannot change approvals or expand budgets.

- [ ] Add content-coverage and authority tests using concrete stage terms (these are regression checks, not scientific-quality evaluation):

```python
@pytest.mark.parametrize("stage,terms", [
    (1, ("assumption", "success")), (2, ("causal", "confounding")),
    (3, ("search", "bias")), (4, ("identifier", "screening")),
    (5, ("exclude", "disconfirming")), (6, ("observation", "inference")),
    (7, ("conflict", "competing", "source count")),
    (8, ("falsifi", "rejection")), (9, ("leakage", "budget")),
    (10, ("fit", "predict", "static")), (11, ("resource", "readiness")),
    (12, ("execution", "failure")), (13, ("stop", "dissent")),
    (14, ("uncertainty", "interpretation")), (15, ("pivot", "disclosure")),
])
def test_stage_content_is_specific(stage, terms):
    text = json.dumps(agent_roles.describe_stage_roles(stage)["roles"]).lower()
    assert all(term in text for term in terms)

@pytest.mark.parametrize("stage", [1, 2, 3, 5, 7, 8, 9, 10, 13, 14, 15])
def test_coordinator_does_not_vote(stage):
    roles = agent_roles.describe_stage_roles(stage)["roles"]
    coordinator = next(r for r in roles if r["role_id"] == "coordinator")
    assert "non-voting" in " ".join(coordinator["authority_limits"]).lower()
```

- [ ] Repeat focused RED/GREEN for added tests, inspect all fifteen records manually against the spec, then run the complete new test file. Record command/counts.
- [ ] Review task 1 independently, fix confirmed defects with failing regression tests, then commit its three files with `feat: add stage-specific research role catalog`.

### Task 2: Projectless CLI, guidance and package verification

**Files:** Modify CLI, CLI tests, skill and plugin tests; create the reference listed above.

**Interfaces:**

- Consumes `describe_stage_roles(stage_id: int) -> dict[str, object]` from task1.
- Produces `researchclaw-codex roles describe --stage N [--json]` with no ROOT argument, no other workflow change.
- JSON mode uses the existing shared JSON emitter. Non-JSON mode prints a short stage/mode line and explicitly says `guidance_only`.

- [ ] Add RED CLI tests, including all success stages and representative argparse failures:

```python
@pytest.mark.parametrize("stage", range(1, 16))
def test_roles_describe_is_projectless_and_readonly(stage, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sentinel").write_bytes(b"unchanged")
    def forbidden(*args, **kwargs):
        raise AssertionError("roles must not load or create a project")
    for name in ("open", "open_readonly", "create"):
        monkeypatch.setattr(ResearchProject, name, forbidden)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main(["roles", "describe", "--stage", str(stage), "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["stage_id"] == stage
    assert payload["activation"] == "guidance_only"
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

@pytest.mark.parametrize("args", [
    ["--stage", "0"], ["--stage", "16"], ["--stage", "23"],
    ["--stage", "-1"], ["--stage", "abc"], ["--stage", "7.0"], [],
    ["--stage", "7", "unexpected-root"],
])
def test_roles_describe_rejects_bad_arguments(args, capsys):
    assert main(["roles", "describe", *args, "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err

def test_roles_describe_text_names_guidance_only(capsys):
    assert main(["roles", "describe", "--stage", "7"]) == 0
    captured = capsys.readouterr()
    assert "stage 7" in captured.out and "guidance_only" in captured.out
    assert captured.err == ""
```

- [ ] Run RED via `uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' python -m pytest tests/codex_native/test_cli.py -k roles -q`. Expected: unknown subcommand before implementation.
- [ ] Add import and parser block near `build_parser` subcommand creation:

```python
from researchclaw.core.agent_roles import describe_stage_roles

# Within build_parser, after subcommands is created:
roles = subcommands.add_parser("roles", help="inspect research role guidance")
role_commands = roles.add_subparsers(dest="roles_command", required=True)
describe = role_commands.add_parser("describe", help="describe stage roles without a project")
describe.add_argument("--stage", type=int, choices=range(1, 16), required=True)
describe.add_argument("--json", action="store_true", help="emit JSON")
```

Add `elif args.command == "roles"` to main's dispatch before the fallback that opens a project, setting `payload = describe_stage_roles(args.stage)`. In the non-JSON output chain, add:

```python
elif args.command == "roles":
    print(f"stage {payload['stage_id']}: {payload['mode']} ({payload['activation']})")
```

Keep the existing ValueError/OSError stderr/exit2 path. Test the catalog failure path by monkeypatching the imported CLI function to raise `ValueError("agent_roles_catalog_invalid")`, then assert exit2, empty stdout and diagnostic stderr.

- [ ] Read the applicable skill-editing instructions before changing SKILL.md. Add only a short link and these exact boundaries, adapted to the existing document's placement/style:

> For stage-specific responsibilities and review questions, consult [agent role guidance](references/agent-roles.md). `roles describe` is projectless, read-only guidance for stages 1–15, not an execution or registration command. Current task packets, stage-specific protocols and user approvals remain authoritative. Do not invent new council artifacts for stages 1–12 from this catalog.

Reference content must include the command example, three role modes, responsibility/question/criterion/authority fields, and all the following statements:

- `guidance_only` does not certify review submissions, independent agent execution or scientific validity. `existing_protocol` describes software support, not project completion.
- Three judgment roles are domain, methodology, critical_reproducibility, plus a non-voting coordinator. Work stages have worker+independent verifier; implementation stages also separate implementation from evaluation/approval.
- Initial independent judgments are not shared until submitted; default one response round, preserve unresolved disagreement. Follow the actual supported stage protocol; A adds no new registration gates.
- Use native Codex agents and packet-authorized tools/inputs. No external LLM API, model/provider selection, invented participants or fabricated replies. Real host task IDs support provenance; unavailable IDs stay unverified.
- Role counts are logical responsibilities, not simultaneous execution requirements. A single agent cannot impersonate independent producers.
- Stage13 retains minimum-two matching recommendations; stage15 retains all-three agreement; stage14 remains analysis synthesis. No automatic rejudgment of historical decisions.
- User execution/approval and budget boundaries remain unchanged. Show a short conclusion/evidence/differences/limits/next-action summary linked to the actual records, not replacing them.

- [ ] Extend the existing reference-link test's expected list with `agent-roles.md`. Add a package-source check that imports `describe_stage_roles`, asserts all fifteen stage IDs can be described, and verifies the bundled JSON exists using `importlib.resources.files("researchclaw.core").joinpath("data/agent_roles.json").is_file()`. Add doc assertions for `guidance_only`, no early council artifacts, and distinct13/14/15 rules. These checks protect documentation presence, not agent behavior.
- [ ] Run focused GREEN and compatibility checks:

```sh
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' python -m pytest tests/codex_native/test_agent_roles.py tests/codex_native/test_cli.py tests/codex_native/test_plugin_package.py tests/codex_native/test_task_packets.py -q
```

- [ ] Verify a built installation outside the checkout, without replacing the live tool. Use a fresh `mktemp -d` path and record its resolved value. Substitute that exact path for `/ABS/TEMP` below; this is the runtime-created path, not a repository file to invent:

```sh
uv build --wheel --out-dir /ABS/TEMP/dist
uv venv --python /opt/homebrew/bin/python3.11 /ABS/TEMP/venv
uv pip install --python /ABS/TEMP/venv/bin/python /ABS/TEMP/dist/researchclaw_codex-0.1.0-py3-none-any.whl
```

From `/ABS/TEMP`, with PYTHONPATH unset, run installed `venv/bin/researchclaw-codex roles describe --stage 7 --json`, plus1,12,13,14,15; parse output and check expected exact fields/roles/protocols. Run16 to verify exit2. Record module `__file__` to prove it comes from the temporary installation, not the checkout or live tool. Run Python with `-B` to avoid interpreter bytecode if checking file immutability. Leave temporary paths explicitly identified; do not perform broad recursive cleanup.

- [ ] Inspect `git diff --check` and scoped Ruff, then review this task's diff. Ensure no state/packet schemas or existing stage instructions were changed. Commit only task2 files with `feat: expose read-only stage role guidance`.

## Final integration gate

- [ ] Read verification-before-completion and requesting-code-review. Obtain scoped review of A against the spec, explicitly including all15 profiles, validation failure cases and the read-only CLI boundary.
- [ ] Fix confirmed defects using focused RED/GREEN, not repeated full-suite runs.
- [ ] At the stable integration point run the full regression suite once, with no simultaneous uv operations:

```sh
uv run --no-project --python /opt/homebrew/bin/python3.11 --with '.[dev]' --with pytest-xdist python -m pytest -n auto -q
```

Report baseline/current counts honestly; a historical `4648 passed, 56 skipped` is not a current result. Record any warning separately from failures. If this suite is deferred, explicitly say so; do not claim full regression success.

- [ ] Record tested commit, commands, passes/failures/skips, installed-wheel smoke results, and changed-file scope. Confirm no original research projects or acceptance results were mutated.
- [ ] Final handoff: A now describes roles; actual7–9 council registration and content-quality proof remain B. State branch/worktree and whether changes are committed. Do not claim merged, pushed or deployed absent those actions and authorization.

## Plan self-review

Coverage: spec sections3/7A map to globals, task1 validation, task2 read-only CLI and compatibility checks. Sections4/5 map to role data and profile review. Sections6/9 map to reference guidance and deployment boundaries. Section8 maps to focused tests, installed-wheel check and one final regression gate. Sections7B–E are explicitly excluded.

Interface check: task2 imports the exact task1 public function; output/catalog share one closed shape. No new project fields or downstream schema expectations. No API/service dependency. Implementation execution choice remains a user-controlled handoff.
