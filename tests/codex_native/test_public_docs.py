from pathlib import Path
import re

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
RESOURCE_PROHIBITIONS_CONTRACT = """`prohibitions` has exactly these boolean fields, all `false`:

```text
network_access, downloads, package_installation, external_llm_calls,
nested_agent_processes, generated_code_execution
```"""


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
    assert "Stage 13 refinement remains unsupported" in stages


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


def test_each_public_operator_file_marks_partial_temp_contract_pending_task_eight():
    for path in STAGE_TWELVE_PUBLIC_FILES:
        normalized = " ".join(path.read_text(encoding="utf-8").split()).lower()
        assert "experiment prepare-self-test" in normalized, path
        assert "published partial quarantine temp" in normalized, path
        assert "mandatory pending task 8 release gate" in normalized, path
        assert "not a current guarantee" in normalized, path


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
