"""The version policy shared by the authored-prose skills' structural guards.

Each skill declares `metadata.version` in its SKILL.md frontmatter. The structural
tests used to pin the exact literal — `version: "0.1.0"` — which meant every
routine bump broke a test that had nothing to say about the bump. The ddd skill
went to 0.1.1 and its guard kept demanding 0.1.0; clean-architecture and
clean-code carry the same trap, unfired only because nobody has bumped them yet.

test_clean_architecture_skill_structure already reached this conclusion for the
plugin manifests ("Pinning the exact literal made this break on every subsequent
bump, so assert lockstep + floor instead"). This module is that same rule for
skill frontmatter, in one place so the three guards cannot drift apart.

What a floor actually protects: the version stays well-formed semver, and never
regresses below the release the skill shipped in. An equality assertion catches
nothing beyond that — it only reports that a human bumped a number on purpose.
"""

import re

# metadata.version is nested under `metadata:`, so the line is indented. Anchored
# per-line to avoid matching a `version:` that belongs to some other key.
_VERSION_LINE = re.compile(r'^\s*version:\s*"(\d+)\.(\d+)\.(\d+)"\s*$', re.MULTILINE)


def parse_metadata_version(frontmatter_text):
    """Return metadata.version as a (major, minor, patch) tuple of ints.

    Fails the calling test if the frontmatter declares no well-formed semver.
    """
    match = _VERSION_LINE.search(frontmatter_text)
    assert match, 'frontmatter declares no well-formed metadata.version: "X.Y.Z"'
    return tuple(int(part) for part in match.groups())


def assert_version_at_least(frontmatter_text, minimum):
    """Assert metadata.version is well-formed and has not regressed below `minimum`.

    `minimum` is a (major, minor, patch) tuple — the release the skill shipped in.
    Returns the parsed version so a caller can make further assertions on it.
    """
    version = parse_metadata_version(frontmatter_text)
    assert version >= minimum, (
        f"metadata.version {_format(version)} regressed below "
        f"the {_format(minimum)} floor"
    )
    return version


def _format(version):
    """Render a (major, minor, patch) tuple back as a dotted string."""
    return ".".join(str(part) for part in version)
