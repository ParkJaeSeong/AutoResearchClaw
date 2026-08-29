import pytest

from researchclaw.core.profiles import load_profile


def test_materials_ai_profile_has_domain_specific_quality_checks():
    profile = load_profile("materials_ai")
    assert profile.id == "materials_ai"
    assert "data_leakage" in profile.quality_checks
    assert "composition_split" in profile.quality_checks
    assert "matbench" in profile.preferred_sources


def test_profile_id_cannot_traverse_to_an_existing_bundled_profile():
    with pytest.raises(ValueError, match="profile"):
        load_profile("../profiles/materials_ai")


@pytest.mark.parametrize("profile_id", ["Materials_AI", "materials-ai", "materials.ai", ""])
def test_profile_id_must_be_a_strict_lowercase_identifier(profile_id):
    with pytest.raises(ValueError, match="profile"):
        load_profile(profile_id)
