from .itertoolz import *

from .functoolz import *

from .dicttoolz import *

from .recipes import *

from functools import partial, reduce

sorted = sorted

map = map

filter = filter

# Aliases
comp = compose

# NOTE (effic_real vendoring): the optional `curried` and `sandbox` alternate-namespace
# subpackages are not vendored — they re-bind every core symbol as a module-level alias
# (e.g. `get = curry(toolz.get)`), which would shadow the real definitions for go-to-def.
# Dropping them keeps go-to-definition resolving to the genuine itertoolz/dicttoolz source.

functoolz._sigs.create_signature_registry()


def __getattr__(name):
    if name == "__version__":
        from importlib.metadata import version

        rv = version("toolz")
        globals()[name] = rv
        return rv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
