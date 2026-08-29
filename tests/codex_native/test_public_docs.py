from pathlib import Path
import re

from researchclaw.core.contracts import SUPPORTED_STAGE_MAX
from researchclaw.core.computational_package import canonical_computational_scaffold


ROOT = Path(__file__).parents[2]
SKILL_ROOT = ROOT / "skills" / "researchclaw"
SUPPORTED_BOUNDARY = re.compile(
    r"Codex-native supported execution boundary:\s*stages?\s*1\s*[\N{EN DASH}-]\s*(\d+)",
    re.IGNORECASE,
)
PUBLIC_STAGE_ELEVEN_BOUNDARIES = (
    r"stage[-\s]?9(?:\s+validation-design)?(?:\s+is\s+an)?\s+approval\s+gate",
    r"(?:after|for)\s+an\s+approved\s+computational\s+design,?\s+stage\s+10",
    r"stage\s+10\s+authors?\s+and\s+statically\s+validat",
    r"does not execute (?:it|the package)",
    r"policy-evidence and laboratory stage 10 packages are unsupported",
    r"stage\s+11\s+(?:observes|uses)\s+only\s+passive\s+local\s+hardware\s+facts",
    r"stops before (?:unsupported )?stage 12",
)


def test_public_docs_match_the_stage_eleven_execution_boundary():
    for document in ("README.md", "RESEARCHCLAW_AGENTS.md"):
        text = (ROOT / document).read_text(encoding="utf-8")
        match = SUPPORTED_BOUNDARY.search(text)

        assert match is not None, f"{document} must state the supported boundary"
        assert int(match.group(1)) == SUPPORTED_STAGE_MAX == 11


def test_public_docs_keep_stage_ten_static_and_stop_before_stage_twelve():
    for document in ("README.md", "RESEARCHCLAW_AGENTS.md"):
        text = (ROOT / document).read_text(encoding="utf-8")

        for boundary in PUBLIC_STAGE_ELEVEN_BOUNDARIES:
            assert re.search(boundary, text, re.IGNORECASE), (
                f"{document} must retain the Stage-10 author/static/no-execution "
                f"and Stage-11 passive-observation/Stage-12-stop boundary: {boundary}"
            )


def test_stage_ten_and_eleven_docs_keep_execution_deferred():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (SKILL_ROOT / "references" / "computational-package.md").read_text(
        encoding="utf-8"
    )
    stages = (SKILL_ROOT / "references" / "stages.md").read_text(encoding="utf-8")

    assert "[references/computational-package.md](references/computational-package.md)" in skill
    assert "authors but does not execute" in reference.lower()
    assert "statically validate" in reference.lower()
    assert "stop before unsupported stage 12" in skill.lower()
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
