import config_sync


def test_section_union_unions_list_bullets_without_conflict():
    version_a = "# Prefs\n- Prefers light mode\n"
    version_b = "# Prefs\n- Prefers dark mode\n- Enable telemetry\n"
    merged = config_sync._section_union(version_a, version_b)
    assert "<<<<<<<" not in merged
    assert "- Prefers light mode" in merged
    assert "- Prefers dark mode" in merged
    assert "- Enable telemetry" in merged


def test_section_union_flags_real_keyvalue_contradiction():
    merged = config_sync._section_union("# S\nmodel: opus\n", "# S\nmodel: sonnet\n")
    assert "<<<<<<<" in merged


def test_section_union_unions_new_keyvalue_line_without_conflict():
    # Different keys are not a contradiction — both should be kept.
    merged = config_sync._section_union("# S\nmodel: opus\n", "# S\ntheme: dark\n")
    assert "<<<<<<<" not in merged
    assert "model: opus" in merged
    assert "theme: dark" in merged
