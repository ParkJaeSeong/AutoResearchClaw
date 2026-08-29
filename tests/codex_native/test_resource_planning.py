from researchclaw.core.resource_planning import observe_local_hardware


def test_observe_local_hardware_reports_passive_non_negative_facts(tmp_path):
    observed = observe_local_hardware(tmp_path)

    assert observed.logical_cpu_count >= 1
    assert observed.total_memory_bytes >= 0
    assert observed.free_disk_bytes >= 0
    assert observed.platform
    assert observed.architecture
    assert observed.method == "python_stdlib_passive"
