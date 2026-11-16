"""Compatibility import; one limiter/state shared by TV2 and TV3 paths."""
import sys
from .security import lockout as _implementation
sys.modules[__name__] = _implementation
