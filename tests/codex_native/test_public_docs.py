from pathlib import Path
import re

import pytest

from researchclaw.core.computational_package import canonical_computational_scaffold
from researchclaw.core.contracts import SUPPORTED_STAGE_MAX


ROOT = Path(__file__).parents[2]
SKILL_ROOT = ROOT / "skills" / "researchclaw"
SUPPORTED_BOUNDARY = re.compile(
    r"Codex-native supported execution boundary:\s*stages?\s*1\s*[\N{EN DASH}-]\s*(\d+)",
    re.IGNORECASE,
)
PUBLIC_BOUNDARY_FILES = (ROOT / "README.md", ROOT / "RESEARCHCLAW_AGENTS.md")
STAGE_TWELVE_PUBLIC_FILES = (
    *PUBLIC_BOUNDARY_FILES,
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "references" / "computational-package.md",
    SKILL_ROOT / "references" / "resource-planning.md",
    SKILL_ROOT / "references" / "approval-policy.md",
)
RESOURCE_REFERENCE = SKILL_ROOT / "references" / "resource-planning.md"
STAGES_REFERENCE = SKILL_ROOT / "references" / "stages.md"
REFINEMENT_REFERENCE = SKILL_ROOT / "references" / "refinement.md"
RESOURCE_PROHIBITIONS_CONTRACT = """`prohibitions` has exactly these boolean fields, all `false`:

```text
network_access, downloads, package_installation, external_llm_calls,
nested_agent_processes, generated_code_execution
```"""
REFINEMENT_NORMATIVE_POLICY = {
    "arbitrary_python": "forbidden",
    "arbitrary_shell": "forbidden",
    "challenge_rounds": "1",
    "confirmation_flags": "self_test,result,finalization",
    "coordinator_vote": "forbidden",
    "disclosure": "after_all_independent_assessments",
    "dissent": "retained",
    "envelope": "immutable_escalate",
    "execution_argv": "task7_returned_only",
    "execution_cwd": "task7_returned_only",
    "implementation_vote": "forbidden",
    "llm_api": "forbidden",
    "network": "forbidden",
    "normative_scope": "map_and_anchors_only",
    "provider_configuration": "forbidden",
    "provider_key": "forbidden",
    "run_context": "read_only_no_discovery",
    "runtime_boundary": "algorithm_monotonic_ns",
    "voter_roles": "domain,methodology,critical_reproducibility",
}
REFINEMENT_OBLIGATION = re.compile(
    r"(?ms)^### Obligation `(?P<key>[a-z_]+)`\n"
    r"(?P<body>.*?)(?=^### Obligation `|^## |\Z)"
)
REFINEMENT_NORMATIVE_VALUE = re.compile(
    r"(?m)^Normative value: `(?P<value>[a-z0-9_,]+)`\.$"
)


def _assert_refinement_contract(text: str) -> None:
    pairs = re.findall(r"(?m)^([a-z_]+)=([a-z0-9_,]+)$", text)

    assert len(pairs) == len(REFINEMENT_NORMATIVE_POLICY)
    assert dict(pairs) == REFINEMENT_NORMATIVE_POLICY
    assert "researchclaw-codex refinement" in text.lower()
    obligations = tuple(REFINEMENT_OBLIGATION.finditer(text))
    obligation_keys = tuple(match.group("key") for match in obligations)
    assert len(obligations) == len(REFINEMENT_NORMATIVE_POLICY)
    assert len(set(obligation_keys)) == len(obligation_keys)
    assert set(obligation_keys) == set(REFINEMENT_NORMATIVE_POLICY)

    for obligation in obligations:
        key = obligation.group("key")
        body = obligation.group("body")
        values = tuple(REFINEMENT_NORMATIVE_VALUE.finditer(body))
        assert len(values) == 1
        assert values[0].group("value") == REFINEMENT_NORMATIVE_POLICY[key]
        prose = REFINEMENT_NORMATIVE_VALUE.sub("", body)
        assert len(re.findall(r"[A-Za-z0-9]+", prose)) >= 6


def test_refinement_workflow_requires_council_and_forbids_llm_api_calls():
    _assert_refinement_contract(REFINEMENT_REFERENCE.read_text(encoding="utf-8"))


def _replace_obligation(text: str, key: str, body: str) -> str:
    pattern = re.compile(
        rf"(?ms)^### Obligation `{re.escape(key)}`\n"
        rf".*?(?=^### Obligation `|^## |\Z)"
    )
    replaced, count = pattern.subn(f"### Obligation `{key}`\n{body}\n\n", text)
    assert count == 1
    return replaced


@pytest.mark.parametrize("key", tuple(REFINEMENT_NORMATIVE_POLICY))
def test_refinement_contract_rejects_missing_obligation_anchor(key):
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(?ms)^### Obligation `{re.escape(key)}`\n"
        rf".*?(?=^### Obligation `|^## |\Z)"
    )
    mutated, count = pattern.subn("", text)

    assert count == 1
    with pytest.raises(AssertionError):
        _assert_refinement_contract(mutated)


@pytest.mark.parametrize("kind", ("duplicate", "unknown"))
def test_refinement_contract_rejects_duplicate_or_unknown_anchor(kind):
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    if kind == "duplicate":
        addition = (
            "### Obligation `network`\n"
            "Normative value: `forbidden`.\n\n"
            "This duplicate must not define the network boundary twice.\n"
        )
    else:
        addition = (
            "### Obligation `unregistered_policy`\n"
            "Normative value: `forbidden`.\n\n"
            "Unknown obligation identifiers are outside the closed contract.\n"
        )

    with pytest.raises(AssertionError):
        _assert_refinement_contract(f"{text}\n{addition}")


def test_refinement_contract_rejects_permissive_map_or_anchor_values():
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    permissive_map = text.replace("network=forbidden", "network=authorized", 1)
    permissive_anchor = _replace_obligation(
        text,
        "provider_key",
        "Normative value: `acceptable`.\n\n"
        "Provider credentials would be acceptable under this altered declaration.",
    )

    with pytest.raises(AssertionError):
        _assert_refinement_contract(permissive_map)
    with pytest.raises(AssertionError):
        _assert_refinement_contract(permissive_anchor)


def test_refinement_contract_requires_meaningful_anchored_prose():
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    empty_prose = _replace_obligation(
        text,
        "confirmation_flags",
        "Normative value: `self_test,result,finalization`.",
    )

    with pytest.raises(AssertionError):
        _assert_refinement_contract(empty_prose)


def test_refinement_contract_allows_harmless_anchored_prose_rewording():
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    reworded = _replace_obligation(
        text,
        "network",
        "Normative value: `forbidden`.\n\n"
        "No network activity belongs inside this locally bounded workflow.",
    )

    _assert_refinement_contract(reworded)


def test_refinement_contract_unanchored_commentary_cannot_override_values():
    text = REFINEMENT_REFERENCE.read_text(encoding="utf-8")
    unanchored_commentary = (
        "\n## Non-normative example\n\n"
        "A quoted example might claim that network calls are authorized or that "
        "provider keys are acceptable. It cannot alter the anchored contract.\n"
    )

    _assert_refinement_contract(f"{text}{unanchored_commentary}")


def test_public_docs_advertise_stage_eleven_boundary():
    for path in PUBLIC_BOUNDARY_FILES:
        text = path.read_text(encoding="utf-8")
        match = SUPPORTED_BOUNDARY.search(text)

        assert match is not None, f"{path.name} must state the supported boundary"
        assert int(match.group(1)) == SUPPORTED_STAGE_MAX == 11
        assert "Stages 1–11" in text or "Stages 1-11" in text
        assert "Stage 12" in text
        assert "explicit" in text.lower() and "approval" in text.lower()


def test_resource_planning_reference_contains_safety_literals():
    text = RESOURCE_REFERENCE.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "experiment/resources.json" in text
    assert "ready_for_execution" in text
    assert "needs_input" in text
    assert "absolute interpreter" in text.lower()
    assert (
        "Parse the packet's `profile_context.hardware_observation` JSON string "
        "and place the resulting object unchanged in `hardware_observation`."
        in normalized
    )
    assert (
        "Stage 12 begins with the approval boundary and remains non-executing "
        "for ResearchClaw." in normalized
    )
    assert (
        "Approval records a hash-bound decision only; it never executes the experiment, "
        "deferred command, or generated code."
        in normalized
    )
    assert RESOURCE_PROHIBITIONS_CONTRACT in text
    assert (
        "Recheck must not add, remove, or change an input path, task, budget, or "
        "deferred command."
        in normalized
    )
    assert "A passive `execution recheck` cannot erase a current human rejection." in normalized
    assert "later explicit re-decision (`approve`)" in normalized
    assert (
        "Entries marked `required: true` must have exactly the same path set as "
        "the current hash-bound config's `input_contract.required_paths`."
        in normalized
    )
    assert (
        "Additional unique project-relative paths are optional extras and must be "
        "marked `required: false`; they still receive full path, filesystem-fact, "
        "SHA-256, and license validation."
        in normalized
    )
    assert (
        "A legacy `cpu` JSON integer aliases `logical_cpu_count`; a finite, non-negative "
        "`memory_gb` JSON number aliases `total_memory_bytes` using exactly 1073741824 "
        "bytes per GiB."
        in normalized
    )
    assert "Alias comparison never rewrites `scope/hardware_profile.json`." in normalized


def test_stage_ten_and_eleven_docs_author_and_validate_without_execution():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references" / "computational-package.md").read_text(
        encoding="utf-8"
    )
    stages = STAGES_REFERENCE.read_text(encoding="utf-8")

    assert "[references/computational-package.md](references/computational-package.md)" in skill
    assert "[references/resource-planning.md](references/resource-planning.md)" in skill
    assert "authors but does not execute" in reference.lower()
    assert "statically validate" in reference.lower()
    assert "execution recheck ROOT --json" in skill
    assert "Never run the deferred research argv in Stage 11." in skill
    assert "Stage 12" in skill
    assert "computational" in stages
    assert "policy_evidence" in reference and "unsupported" in reference.lower()
    assert "laboratory" in reference and "unsupported" in reference.lower()
    assert "canonical_computational_scaffold()" in reference
    assert "byte-for-byte" in reference.lower()
    assert "sole authority" in reference.lower()
    assert "pytest==8.3.0" not in reference
    assert "--establish-legacy-baseline" in reference
    assert "default remains fail-closed" in reference.lower()
    for path in canonical_computational_scaffold():
        assert path in reference


def test_public_docs_describe_the_explicit_development_run_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = RESOURCE_REFERENCE.read_text(encoding="utf-8")

    for text in (readme, skill, reference):
        assert "execution run" in text
        assert "--input-manifest" in text
        assert "--development" in text
        assert "--confirm-development-run" in text
        assert "dev_results.json" in text
        assert "NumPy-only Ridge" in text

    assert "research approval gate unchanged" in readme
    assert "After reporting the development result, stop." in skill
    assert "Do not describe it as research execution." in skill


def _markdown_section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    assert marker in text
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_public_docs_describe_explicit_research_result_registration_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agent_guide = (ROOT / "RESEARCHCLAW_AGENTS.md").read_text(encoding="utf-8")
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = RESOURCE_REFERENCE.read_text(encoding="utf-8")
    stages = STAGES_REFERENCE.read_text(encoding="utf-8")
    readme_handoff = _markdown_section(
        readme, "Explicit Stage-12 research handoff and registration"
    )
    reference_handoff = _markdown_section(
        reference, "Explicit research handoff and registration"
    )
    skill_workflow = _markdown_section(skill, "Workflow")
    agent_workflow = _markdown_section(agent_guide, "Workflow")

    for section in (readme_handoff, reference_handoff, skill_workflow):
        assert "execution prepare-run ROOT --json" in section
        assert (
            "execution register-result ROOT --result experiment/results.json "
            "--confirm-research-result --json"
        ) in section

    readme_handoff_normalized = " ".join(readme_handoff.split())
    reference_handoff_normalized = " ".join(reference_handoff.split())
    skill_workflow_normalized = " ".join(skill_workflow.split())
    for section in (
        readme_handoff_normalized,
        reference_handoff_normalized,
        skill_workflow_normalized,
    ):
        assert "authoritative argv" in section.lower()
        assert "absolute interpreter" in section.lower()
        assert "does not execute" in section.lower()
        assert "experiment/results.json" in section
    assert (
        "Only after the user-run argv writes that contract-bound "
        "`experiment/results.json`"
        in skill_workflow_normalized
    )
    agent_normalized = " ".join(agent_workflow.split())
    assert "authoritative argv" in agent_normalized
    assert "without changing `PATH`" in agent_normalized
    for section in (
        readme_handoff_normalized,
        reference_handoff_normalized,
        skill_workflow_normalized,
    ):
        assert "successful registration" in section.lower()
        assert "Stage 13" in section

    assert "approval-only unsupported execution boundary" not in readme
    assert "approval-only unsupported execution boundary" not in stages
    assert "Stage 13 refinement uses the explicit council protocol" in stages


def test_stage_twelve_public_contract_is_explicit_immutable_and_legacy_safe():
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in STAGE_TWELVE_PUBLIC_FILES
    )
    normalized = " ".join(combined.split()).lower()

    for required in (
        "absolute interpreter",
        "authoritative argv",
        "register-self-test",
        "immutable manifest",
        "--confirm-research-result",
        "--confirm",
        "evidence audit",
        "legacy_untrusted",
        "audit-only",
        "disk preflight",
        "deduplication",
    ):
        assert required in normalized

    assert "python experiment/code/main.py" not in combined
    assert "stage 12 computes metrics" not in normalized
    assert "delete evidence objects manually" not in normalized


def test_each_public_operator_file_states_verified_partial_temp_contract():
    for path in STAGE_TWELVE_PUBLIC_FILES:
        normalized = " ".join(path.read_text(encoding="utf-8").split()).lower()
        assert "experiment prepare-self-test" in normalized, path
        assert "published partial quarantine temp" in normalized, path
        assert "adversarial release gate" in normalized, path
        assert "verifies this guarantee" in normalized, path
        assert "not a current guarantee" not in normalized, path


def test_stage_twelve_public_contract_documents_order_and_recovery_routes():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(
        _markdown_section(
            readme, "Explicit Stage-12 research handoff and registration"
        ).split()
    )

    ordered_commands = (
        "experiment register-self-test ROOT",
        "researchclaw-codex approve ROOT",
        "researchclaw-codex execution prepare-run",
        "researchclaw-codex execution register-result",
        "researchclaw-codex evidence audit",
    )
    offsets = [normalized.index(command) for command in ordered_commands]
    assert offsets == sorted(offsets)

    for recovery_case in (
        "Environment drift",
        "Existing result",
        "Stale contract",
        "Insufficient disk",
        "Interrupted registration",
        "Legacy Stage 13 evidence",
        "Published partial quarantine temp",
    ):
        assert recovery_case in readme

    assert "fresh inode" in readme
    assert "complete read-only candidate" in readme
    assert "manual/operator action" in readme
    assert (
        "`register-result --json` preserves the public keys `readiness`, "
        "`approval_eligible`, `result_path`, `result_sha256`, `current_stage`, "
        "and `next_action`" in normalized
    )
    assert "Errors keep their existing category string" in normalized
