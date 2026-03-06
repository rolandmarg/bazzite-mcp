from .accessibility import interact, set_text
from .capture import screenshot
from .input import send_input
from .windows import manage_windows

__all__ = [
    "interact",
    "manage_windows",
    "screenshot",
    "send_input",
    "set_text",
]
