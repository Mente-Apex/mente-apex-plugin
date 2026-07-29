"""Selection partitioning: which backend owns which file.

The gate invokes each backend once over its partition — never once per test —
so partitioning is the whole of dispatch and deserves its own tests.
"""

from mutation_gate import Survivor, partition


def test_partitions_a_mixed_selection_by_stack():
    partitions = partition(
        [
            "src/api/money.py",
            "web/src/cart.ts",
            "web/src/cart.js",
            "skills/test-quality/SKILL.md",
            "assets/logo.png",
        ]
    )

    assert partitions["python"] == ("src/api/money.py",)
    assert partitions["js"] == ("web/src/cart.ts", "web/src/cart.js")
    assert partitions["prose"] == ("skills/test-quality/SKILL.md",)
    assert partitions["unresolved"] == ("assets/logo.png",)


def test_absent_stacks_partition_to_empty_not_missing():
    partitions = partition(["only/thing.py"])

    assert partitions["js"] == ()
    assert partitions["prose"] == ()


def test_survivor_is_frozen_so_a_reporter_cannot_rewrite_a_finding():
    import dataclasses

    import pytest

    survivor = Survivor(
        artifact="src/money.py",
        location="discount",
        mutant="and -> or",
        associated_tests=("tests/test_money.py::test_member_discount",),
        backend="mutmut",
        granularity="function",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        survivor.artifact = "elsewhere.py"
