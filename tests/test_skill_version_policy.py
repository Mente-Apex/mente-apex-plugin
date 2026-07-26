"""Guards for the shared skill-version policy itself.

A floor assertion is easy to write in a way that passes on anything — the point of
these is to prove assert_version_at_least still fails when it should, so the three
skill guards that depend on it cannot quietly become no-ops.
"""

import pytest

from skill_version_policy import assert_version_at_least, parse_metadata_version

FRONTMATTER = '\nname: example\nmetadata:\n  version: "1.4.2"\n'


def test_parses_the_indented_metadata_version():
    assert parse_metadata_version(FRONTMATTER) == (1, 4, 2)


def test_accepts_a_version_above_the_floor():
    assert assert_version_at_least(FRONTMATTER, (1, 0, 0)) == (1, 4, 2)


def test_accepts_a_version_exactly_on_the_floor():
    assert assert_version_at_least(FRONTMATTER, (1, 4, 2)) == (1, 4, 2)


def test_rejects_a_version_below_the_floor():
    with pytest.raises(AssertionError, match="regressed below"):
        assert_version_at_least(FRONTMATTER, (2, 0, 0))


def test_compares_numerically_not_lexically():
    """Version 0.10.0 is above 0.9.0 — a string compare gets this backwards."""
    frontmatter = 'metadata:\n  version: "0.10.0"\n'
    assert assert_version_at_least(frontmatter, (0, 9, 0)) == (0, 10, 0)


def test_rejects_frontmatter_with_no_version():
    with pytest.raises(AssertionError, match="no well-formed metadata.version"):
        parse_metadata_version("\nname: example\nuser-invocable: true\n")


def test_rejects_a_malformed_version():
    with pytest.raises(AssertionError, match="no well-formed metadata.version"):
        parse_metadata_version('metadata:\n  version: "1.2"\n')


def test_ignores_an_unquoted_version():
    """The convention is a quoted semver; an unquoted one is not silently accepted."""
    with pytest.raises(AssertionError, match="no well-formed metadata.version"):
        parse_metadata_version("metadata:\n  version: 1.2.3\n")
