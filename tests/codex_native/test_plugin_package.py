import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_plugin_manifest_and_skill_are_explicit_and_api_free():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
    skill = (ROOT / "skills" / "researchclaw" / "SKILL.md").read_text()
    skill_ui = yaml.safe_load(
        (ROOT / "skills" / "researchclaw" / "agents" / "openai.yaml").read_text()
    )

    assert manifest["name"] == "autoresearchclaw-codex"
    assert manifest["skills"] == "./skills/"
    assert skill_ui["policy"]["allow_implicit_invocation"] is False
    assert "explicit" in skill.lower()
    forbidden = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "acpx", "--auto-approve")
    assert not any(token in skill for token in forbidden)
