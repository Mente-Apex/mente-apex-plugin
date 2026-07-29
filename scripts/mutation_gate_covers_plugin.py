"""The `--covers-manifest` pytest plugin, shipped WITH the gate.

The prose backend has to ask an audited repo's suite which artifact slices its
tests declare via `@pytest.mark.covers`. That question is asked by running
pytest with `--covers-manifest=<path>`, and until this module existed the
option was registered by *this repo's* `tests/conftest.py` -- so against any
other repo pytest exited 4 ("unrecognized arguments") and the prose backend
could not work at all. A gate that only functions inside its own repository is
not a gate.

The option therefore travels with the gate: `mutation_gate_prose` passes
`-p mutation_gate_covers_plugin` and puts this directory on the subprocess's
`PYTHONPATH`, so the audited repo needs no conftest, no plugin install, and no
configuration whatsoever. It also means only ONE registration exists -- a
conftest that re-registered the same option would collide with this one and
fail the very run it meant to support.

The manifest travels through a real file rather than stdout, because
`--collect-only -q` prints pytest's own node-id list before any hook payload
and a "N tests collected" summary after it. `-` is still accepted for
interactive debugging.
"""

import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption(
        "--covers-manifest",
        default=None,
        help="Write collected @pytest.mark.covers declarations as JSON.",
    )


def pytest_collection_finish(session):
    """Emit (node_id, artifact, section) for every guard that declared one."""
    destination = session.config.getoption("--covers-manifest")
    if destination is None:
        return
    declarations = []
    for item in session.items:
        marker = item.get_closest_marker("covers")
        if marker is None:
            continue
        declarations.append([item.nodeid, marker.args[0], marker.kwargs.get("section")])
    payload = json.dumps(declarations)
    if destination == "-":
        print(payload)
    else:
        Path(destination).write_text(payload, encoding="utf-8")
