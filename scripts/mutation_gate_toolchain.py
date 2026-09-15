"""How the audited repo's own build tool gets invoked.

Extracted because two callers now need the same answer for different reasons:
the pitest backend launches PIT through Maven or Gradle, and the baseline
launches the *suite* through the same pair. One rule about which binary to
prefer, in one place, so a fix to it cannot reach one caller and miss the other.

Deliberately narrow: this module answers "what do I exec", nothing about what
arguments follow it. Each caller owns its own invocation, because a PIT run and
a test run share a launcher and share nothing else.
"""

import shutil
from pathlib import Path


def wrapper_or_bare(repo_root, wrapper, bare):
    """Prefer the repo's build-tool wrapper, exactly as a developer would.

    The wrapper pins the build tool version the way a lockfile pins
    dependencies; running the ambient `mvn`/`gradle` can resolve a different
    version than the project's own CI does, which is how a mutation run comes
    back disagreeing with the suite for reasons that have nothing to do with
    mutants.

    `None` when neither exists, which is a fact the caller has to represent --
    not a launcher to guess at.
    """
    wrapper_path = Path(repo_root) / wrapper
    if wrapper_path.is_file():
        return [str(wrapper_path)]
    if shutil.which(bare):
        return [bare]
    return None
