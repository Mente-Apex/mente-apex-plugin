"""Where a new stack's backend gets registered.

Adding support for a stack means writing its backend module and adding it to
`default_backends()` here — plus one entry in `mutation_gate.STACK_SUFFIXES`,
which owns the stack/suffix taxonomy independently of which backends a given
run registers. Those two edits are the whole job. Registration is not otherwise
additive, and pretending it is would send the next reader hunting for a seam
that is not there.

Kept separate from the reporter so that "we support a new stack" and "we render
survivors differently" are not the same file's two reasons to change.
"""

from mutation_gate_mutmut import MutmutBackend
from mutation_gate_prose import ProseBackend
from mutation_gate_stryker import StrykerBackend


def default_backends():
    """The backends a normal run dispatches over."""
    return (MutmutBackend(), StrykerBackend(), ProseBackend())
