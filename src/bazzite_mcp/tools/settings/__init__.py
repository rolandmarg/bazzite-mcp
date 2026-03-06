from .display import display_config
from .quick import _set_theme, quick_setting
from .schema import _get_settings, gsettings

__all__ = [
    "_get_settings",
    "_set_theme",
    "display_config",
    "gsettings",
    "quick_setting",
]
