"""Retain Frogify's Python tracebacks and terminal styling, not every lexer."""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    "pygments.lexers.python",
    "pygments.lexers.special",
    "pygments.formatters.terminal",
    "pygments.formatters.terminal256",
    *collect_submodules("pygments.styles"),
]
