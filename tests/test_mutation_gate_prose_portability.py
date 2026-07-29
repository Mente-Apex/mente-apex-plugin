"""The prose backend outside this repo.

Two live reproductions from the whole-branch review, pinned as tests:

1. `collect_declarations` shells `pytest --covers-manifest=...`, an option this
   repo's own `tests/conftest.py` used to register. Against a foreign repo
   pytest exited 4 ("usage error"), the uncaught `RuntimeError` propagated out
   of `run_gate`, and the ENTIRE run died -- discarding every survivor the
   mutmut and Stryker backends had already produced.
2. The option therefore had to travel with the gate rather than be borrowed
   from the audited repo, or the prose backend could never work anywhere else.
"""

import json
import subprocess
import sys
from pathlib import Path

import mutation_gate_prose
from mutation_gate import Survivor, run_gate
from mutation_gate_prose import COVERS_PLUGIN, ProseBackend

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"


class TestABrokenCollectionDegradesRatherThanKillingTheRun:
    def test_a_collection_failure_yields_no_survivors_instead_of_raising(
        self, tmp_path
    ):
        def exploding_collect(repo_root):
            raise RuntimeError("pytest collection failed (exit 4)")

        backend = ProseBackend(collect=exploding_collect)

        assert backend.survivors(tmp_path, ("doc.md",)) == ()

    def test_the_failure_is_named_in_run_errors_never_swallowed(self, tmp_path):
        def exploding_collect(repo_root):
            raise RuntimeError("pytest collection failed (exit 4)")

        backend = ProseBackend(collect=exploding_collect)
        backend.survivors(tmp_path, ("doc.md",))

        (message,) = backend.run_errors(tmp_path)
        assert "prose" in message
        assert "exit 4" in message

    def test_run_errors_is_cleared_by_a_later_successful_collection(self, tmp_path):
        calls = []

        def flaky_collect(repo_root):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return ()

        backend = ProseBackend(collect=flaky_collect)
        backend.survivors(tmp_path, ("doc.md",))
        backend.survivors(tmp_path, ("doc.md",))

        assert backend.run_errors(tmp_path) == ()

    def test_another_backends_survivors_are_not_discarded_by_a_prose_crash(
        self, tmp_path
    ):
        """The whole point: a broken prose backend used to abort the gate and
        throw away everything mutmut had already found.
        """

        def exploding_collect(repo_root):
            raise RuntimeError("pytest collection failed (exit 4)")

        python_survivor = Survivor(
            artifact="src/money.py",
            location="money.discount",
            mutant="and -> or",
            associated_tests=(),
            backend="mutmut",
            granularity="function",
        )

        class FakePython:
            stack = "python"
            tool = "mutmut"

            def available(self, repo_root):
                return True

            def install_hint(self, repo_root):
                return "uv add --dev mutmut"

            def survivors(self, repo_root, paths):
                return (python_survivor,)

        result = run_gate(
            tmp_path,
            ["src/money.py", "doc.md"],
            [FakePython(), ProseBackend(collect=exploding_collect)],
        )

        assert result.survivors == (python_survivor,)
        assert any("prose" in message for message in result.run_errors)


class TestTheCoversOptionTravelsWithTheGate:
    def test_the_option_works_in_a_repo_that_never_heard_of_it(self, tmp_path):
        """A foreign repo: no conftest, no marker registration, nothing. The
        gate supplies the option itself via `-p`, so the prose backend is not
        limited to the one repo whose conftest happened to define the hook.
        """
        (tmp_path / "test_foreign.py").write_text(
            "import pytest\n\n\n"
            '@pytest.mark.covers("README.md", section="Usage")\n'
            "def test_readme_documents_usage():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        manifest = tmp_path / "manifest.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                COVERS_PLUGIN,
                f"--covers-manifest={manifest}",
                str(tmp_path),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(SCRIPTS), "PATH": "/usr/bin:/bin"},
        )

        assert result.returncode == 0, result.stdout + result.stderr
        declarations = json.loads(manifest.read_text(encoding="utf-8"))
        assert [d[1:] for d in declarations] == [["README.md", "Usage"]]

    def test_the_gate_passes_the_plugin_and_its_import_path_to_pytest(self):
        argv, env = mutation_gate_prose._collect_command(Path("/tmp/x.json"))

        assert "-p" in argv and COVERS_PLUGIN in argv
        assert str(SCRIPTS) in env["PYTHONPATH"].split(":")

    def test_collect_declarations_still_works_against_this_very_repo(self):
        declarations = mutation_gate_prose.collect_declarations(REPO_ROOT)

        assert any(
            artifact == "skills/test-quality/SKILL.md"
            for _, artifact, _ in declarations
        )
