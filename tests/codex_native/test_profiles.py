from researchclaw.core.profiles import load_profile


def test_materials_ai_profile_has_domain_specific_quality_checks():
    profile = load_profile("materials_ai")
    assert profile.id == "materials_ai"
    assert "data_leakage" in profile.quality_checks
    assert "composition_split" in profile.quality_checks
    assert "matbench" in profile.preferred_sources
