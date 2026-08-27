import json
from pathlib import Path
import re
import tomllib

import yaml


ROOT = Path(__file__).parents[2]
FORK_URL = "https://github.com/ParkJaeSeong/AutoResearchClaw-Codex"
SKILL_ROOT = ROOT / "skills" / "researchclaw"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def _local_markdown_links(path: Path) -> tuple[Path, ...]:
    links: list[Path] = []
    for target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        links.append((path.parent / target.split("#", 1)[0]).resolve())
    return tuple(links)


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
        "researchclaw-codex" in block
        for block in editable_install_blocks
    )
    assert plugin_invocation_blocks
    assert all(
        "$researchclaw" not in block for block in editable_install_blocks
    )


def test_distribution_and_plugin_share_codex_native_identity_and_version():
    import researchclaw

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert project["name"] == "researchclaw-codex"
    assert project["version"] == manifest["version"].split("+", 1)[0] == "0.1.0"
    assert researchclaw.__version__ == project["version"]
    assert "Codex-native" in project["description"]
    assert project["urls"]["Repository"] == FORK_URL
    assert project["urls"]["Upstream"] == "https://github.com/aiming-lab/AutoResearchClaw"


def test_skill_reference_links_resolve_including_stage_six_guidance():
    expected_stage_six_references = (
        SKILL_ROOT / "references" / "knowledge-extraction.md",
    )
    markdown_files = tuple(SKILL_ROOT.rglob("*.md"))
    linked_files = {
        linked_file
        for markdown_file in markdown_files
        for linked_file in _local_markdown_links(markdown_file)
    }

    assert set(reference.resolve() for reference in expected_stage_six_references) <= linked_files
    assert all(reference.exists() for reference in expected_stage_six_references)
    assert all(linked_file.exists() for linked_file in linked_files)
