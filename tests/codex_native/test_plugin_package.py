import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]
FORK_URL = "https://github.com/ParkJaeSeong/AutoResearchClaw"


def test_plugin_manifest_and_skill_are_explicit_and_api_free():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    skill = (ROOT / "skills" / "researchclaw" / "SKILL.md").read_text()
    skill_ui = yaml.safe_load(
        (ROOT / "skills" / "researchclaw" / "agents" / "openai.yaml").read_text()
    )

    assert manifest["name"] == "autoresearchclaw-codex"
    assert manifest["skills"] == "./skills/"
    assert manifest["homepage"] == FORK_URL
    assert manifest["repository"] == FORK_URL
    assert manifest["interface"]["websiteURL"] == FORK_URL
    assert skill_ui["policy"]["allow_implicit_invocation"] is False
    assert "explicit" in skill.lower()
    forbidden = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "acpx", "--auto-approve")
    assert not any(token in skill for token in forbidden)


def test_readme_separates_cli_installation_from_plugin_invocation():
    readme = (ROOT / "README.md").read_text()
    fenced_blocks = readme.split("```")[1::2]
    editable_install_blocks = [
        block for block in fenced_blocks if "pip install -e ." in block
    ]
    plugin_invocation_blocks = [
        block for block in fenced_blocks if "$researchclaw" in block
    ]

    assert any(
        "python -m researchclaw.codex.cli" in block
        for block in editable_install_blocks
    )
    assert plugin_invocation_blocks
    assert all(
        "$researchclaw" not in block for block in editable_install_blocks
    )
