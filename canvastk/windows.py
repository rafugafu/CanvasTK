"""Window and Toplevel: tk.Tk / tk.Toplevel whose background and theme follow canvastk.

Both can carry their own theme (theme= / set_theme()), which applies to the
window and to every canvastk widget inside it.
"""

import tkinter as tk

from ._core import (
    _CANVAS_THEMED_WIDGETS,
    check_appearance_mode,
    starting_theme,
)
from .containers import (
    _ThemedBackground,
)

# =============================================================================
# Windows
# =============================================================================


class _ThemedWindow(_ThemedBackground):
    """Mixin for Window and Toplevel: a themed background plus a window-wide theme (see
    _ThemedBackground).
    """

    def _init_window(self, background, theme, appearance_mode=None):
        """background: a fixed color (bg=), or None to follow the theme.
        theme: theme-key overrides for this window and every widget in it.
        appearance_mode: 'light' or 'dark' for this window alone (None follows the
        global mode)."""
        self._appearance_mode = check_appearance_mode(appearance_mode)
        self._explicit_background = background
        # The window's own theme: widgets inside look it up through window_theme(),
        # between the global theme and their own overrides.
        self._theme_overrides = starting_theme(theme)
        self.background_role = None if background else "window"
        self.child_background_role = self.background_role
        self.configure(bg=background or self.themed_color(self, "window"))
        _CANVAS_THEMED_WIDGETS.add(self)

    def refresh_theme(self):
        """The theme changed: re-apply the window's background."""
        self.apply_background()

    def _appearance_changed(self):
        """The window's appearance mode changed: recolor it and everything in it."""
        self.refresh_theme()
        self._refresh_window_widgets()

    def _refresh_window_widgets(self):
        """Make every themed widget that lives in this window re-read the theme (after
        the window's theme changed).
        """
        for widget in list(_CANVAS_THEMED_WIDGETS):
            try:
                if widget is not self and widget.winfo_toplevel() is self:
                    widget.refresh_theme()
            except tk.TclError:
                pass

    def set_theme(self, theme):
        """Change theme keys for this window and every widget inside it,
        dynamically (all colors, not just the accent); None removes a change.
        A widget's own colors still win. Giving an 'accent' also derives
        accent_hover, accent_text, focus_ring, selection, and row_current."""
        for key, value in theme.items():
            if value is None:
                self._theme_overrides.pop(key, None)
            else:
                self._theme_overrides[key] = value
        self.refresh_theme()
        self._refresh_window_widgets()

    def reset_theme(self):
        """Remove every change made with set_theme() or theme=."""
        self._theme_overrides.clear()
        self.refresh_theme()
        self._refresh_window_widgets()


class Window(_ThemedWindow, tk.Tk):
    """The application window; its background follows the appearance mode
    (unless a fixed bg= color is given). theme={...} overrides theme keys for
    the window and everything in it; change them later with set_theme()."""

    def __init__(self, *arguments, theme=None, **kwargs):
        """Create the main window (arguments as tk.Tk); bg= fixes the background color,
        theme= gives the window its own theme keys.
        """
        background = kwargs.pop("bg", kwargs.pop("background", None))
        appearance_mode = kwargs.pop("appearance_mode", None)
        tk.Tk.__init__(self, *arguments, **kwargs)
        self._init_window(background, theme, appearance_mode)


class Toplevel(_ThemedWindow, tk.Toplevel):
    """A secondary window; its background follows the appearance mode
    (unless a fixed bg= color is given). It takes theme= and set_theme()
    like Window, independently of the main window.

    transient (default True) makes it a transient window of its master and
    puts it in the master's window group, so the window manager keeps the
    two together (one taskbar entry, minimized and raised with the main
    window, always shown above it). Pass transient=False for a fully
    independent window."""

    def __init__(self, *arguments, theme=None, transient=True, **kwargs):
        """Create the subwindow (arguments as tk.Toplevel); bg= / theme= as for Window;
        transient=False makes it fully independent.
        """
        background = kwargs.pop("bg", kwargs.pop("background", None))
        appearance_mode = kwargs.pop("appearance_mode", None)
        tk.Toplevel.__init__(self, *arguments, **kwargs)
        self._init_window(background, theme, appearance_mode)
        # Make it a real subwindow for the window manager: transient (kept above,
        # minimized with the master) and in the master's window group.
        if transient and self.master is not None:
            owner = self.master.winfo_toplevel()
            try:
                self.transient(owner)
                self.group(owner)
            except tk.TclError:
                pass
