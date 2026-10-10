"""Message boxes with the same API as tkinter.messagebox, drawn with canvastk widgets.

    from canvastk import messagebox

    messagebox.showinfo("Saved", "The file was saved.")
    messagebox.showerror("Error", "Could not open the file.", detail="Permission denied.")
    if messagebox.askyesno("Quit", "Quit without saving?"):
        ...
    answer = messagebox.askyesnocancel("Save", "Save the changes?")   # True, False, or None

The functions, the constants (OK, YESNO, ERROR...), and the options (parent, default,
detail, icon, type) behave like tkinter's. A message box is modal, follows the
theme of the window it belongs to, and is shown above that window.
"""

import tkinter as tk

from ._core import CanvasWidget, window_theme
from .buttons import Button, Label
from .containers import Frame
from .windows import Toplevel, Window

# Icons.
ERROR = "error"
INFO = "info"
QUESTION = "question"
WARNING = "warning"

# Types (which buttons are shown).
ABORTRETRYIGNORE = "abortretryignore"
OK = "ok"
OKCANCEL = "okcancel"
RETRYCANCEL = "retrycancel"
YESNO = "yesno"
YESNOCANCEL = "yesnocancel"

# Button results.
ABORT = "abort"
RETRY = "retry"
IGNORE = "ignore"
CANCEL = "cancel"
YES = "yes"
NO = "no"

# The buttons of each type, left to right, as the strings the functions return.
_MESSAGE_BOX_BUTTONS = {
    OK: (OK,),
    OKCANCEL: (OK, CANCEL),
    YESNO: (YES, NO),
    YESNOCANCEL: (YES, NO, CANCEL),
    RETRYCANCEL: (RETRY, CANCEL),
    ABORTRETRYIGNORE: (ABORT, RETRY, IGNORE),
}

# What closing the window (or pressing Escape) answers: the first of these shown.
_MESSAGE_BOX_CLOSE_ANSWERS = (CANCEL, NO, OK, IGNORE)

# The icon of each kind: its symbol, and its color (None is the accent color).
_MESSAGE_BOX_ICONS = {
    INFO: ("i", None),
    QUESTION: ("?", None),
    WARNING: ("!", "#F5A623"),
    ERROR: ("×", "danger"),
}

# The options besides icon and type, which the functions can also replace.
_MESSAGE_BOX_OPTIONS = ("parent", "default", "detail", "buttons")


# =============================================================================
# Small helpers for the dialog windows (also used by the file dialog)
# =============================================================================


def _parent_toplevel(parent):
    """The window a dialog belongs to: `parent`'s window, or the default root."""
    if parent is None:
        parent = tk._default_root
    return parent.winfo_toplevel() if parent is not None else None


def _center_on(window, parent, size=None):
    """Place `window` in the middle of `parent` (kept inside the screen).

    `size` is the (width, height) the window will have; by default the size it
    asks for (the window is not on screen yet, so it has no real size).
    """
    window.update_idletasks()
    window_width, window_height = size or (
        window.winfo_reqwidth(),
        window.winfo_reqheight(),
    )
    x = parent.winfo_rootx() + (parent.winfo_width() - window_width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window_height) // 2
    x = max(0, min(x, window.winfo_screenwidth() - window_width))
    y = max(0, min(y, window.winfo_screenheight() - window_height))
    window.geometry(f"+{x}+{y}")


def _make_modal(window, parent, size=None):
    """Show `window` above `parent` and block input to the rest of the application
    until it is destroyed (returns when it is). `size` is as for _center_on().
    """
    _center_on(window, parent, size)
    try:
        previous_grab = (
            window.grab_current()
        )  # another modal window this one opens over
    except (KeyError, tk.TclError):
        previous_grab = None
    try:
        window.wait_visibility()
        window.grab_set()
    except tk.TclError:  # for example, a window manager that refuses grabs
        pass
    window.focus_force()
    window.wait_window()
    # Closing this window released the grab it took; give it back to the modal window it
    # was opened over, if there was one (never grab a window that was not grabbed before,
    # or the other windows of the application stop receiving mouse clicks).
    if previous_grab is not None:
        try:
            previous_grab.grab_set()
        except tk.TclError:
            pass


# =============================================================================
# The message box
# =============================================================================


class _MessageBoxIcon(CanvasWidget):
    """The round icon of a message box: a colored disc with a white symbol."""

    SIZE = 44

    def __init__(self, master, icon, **kwargs):
        """`icon` is one of ERROR, INFO, QUESTION, and WARNING."""
        kwargs.setdefault("width", self.SIZE)
        kwargs.setdefault("height", self.SIZE)
        super().__init__(master, **kwargs)
        self.symbol, self.icon_color = _MESSAGE_BOX_ICONS[icon]

    def redraw(self, width, height):
        """Draw the disc and the symbol."""
        color = self.icon_color or "accent"
        if not color.startswith("#"):
            color = self.color(color)
        self.draw_box(0, 0, width, height, color, radius=min(width, height) // 2)
        self.create_text(
            width / 2,
            height / 2,
            text=self.symbol,
            font=("TkDefaultFont", 20, "bold"),
            fill="#FFFFFF",
        )


def _show(title, message, icon, type, **options):
    """Show a message box and return the pressed button as a string (see the
    constants, or the label of a custom button). Used by all the functions below; `icon` and `type` can be
    replaced by the caller's options of the same names.
    """
    icon = options.pop("icon", icon)
    type = options.pop("type", type)
    unknown = [name for name in options if name not in _MESSAGE_BOX_OPTIONS]
    if unknown:
        raise TypeError(f"unexpected option {unknown[0]!r}")
    if type not in _MESSAGE_BOX_BUTTONS:
        raise TypeError(
            f"bad type {type!r}: must be one of {sorted(_MESSAGE_BOX_BUTTONS)}"
        )
    if icon not in _MESSAGE_BOX_ICONS:
        raise TypeError(
            f"bad icon {icon!r}: must be one of {sorted(_MESSAGE_BOX_ICONS)}"
        )
    custom = options.get("buttons")
    if custom is not None:
        buttons = tuple(str(label) for label in custom)
        if not buttons:
            raise TypeError("buttons must not be empty")
        close_answer = None  # closing the window or Escape answers None
        labels = {label: label for label in buttons}
    else:
        buttons = _MESSAGE_BOX_BUTTONS[type]
        close_answer = next(
            name for name in _MESSAGE_BOX_CLOSE_ANSWERS if name in buttons
        )
        labels = {name: name.capitalize() for name in buttons}
    default = options.get("default")
    if default is not None and default not in buttons:
        raise TypeError(f"bad default {default!r}: must be one of {list(buttons)}")
    default = default or buttons[0]

    temporary_root = None
    owner = _parent_toplevel(options.get("parent"))
    if owner is None:  # like tkinter: make a root if the program has none
        temporary_root = owner = Window()
        owner.withdraw()
    try:
        window = Toplevel(owner, theme=dict(window_theme(owner)))
        window.title(title or "")
        window.resizable(False, False)
        answer = [close_answer]

        def finish(name):
            """Remember the answer and close."""
            answer[0] = name
            window.destroy()

        body = Frame(window)
        body.pack(fill="both", expand=True, padx=18, pady=(16, 10))
        _MessageBoxIcon(body, icon).pack(side="left", anchor="n", padx=(0, 14))
        text = Frame(body)
        text.pack(side="left", fill="both", expand=True)
        Label(text, str(message or ""), wraplength=380, justify="left").pack(anchor="w")
        if options.get("detail"):
            Label(
                text,
                str(options["detail"]),
                wraplength=380,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))

        row = Frame(window)
        row.pack(fill="x", padx=18, pady=(0, 16))
        for name in reversed(buttons):
            Button(row, labels[name], command=lambda name=name: finish(name)).pack(
                side="right", padx=(8, 0)
            )
        window.bind("<Return>", lambda _: finish(default))
        window.bind("<Escape>", lambda _: finish(close_answer))
        window.protocol("WM_DELETE_WINDOW", lambda: finish(close_answer))
        _make_modal(window, owner)
    finally:
        if temporary_root is not None:
            temporary_root.destroy()
    return answer[0]


def _answer(answer, options, true_answer):
    """The True / False the ask functions return; with custom `buttons` the label of
    the pressed button instead (the labels have no yes / no meaning).
    """
    return answer if "buttons" in options else answer == true_answer


def showinfo(title=None, message=None, **options):
    """Show an information box; returns "ok"."""
    return _show(title, message, INFO, OK, **options)


def showwarning(title=None, message=None, **options):
    """Show a warning box; returns "ok"."""
    return _show(title, message, WARNING, OK, **options)


def showerror(title=None, message=None, **options):
    """Show an error box; returns "ok"."""
    return _show(title, message, ERROR, OK, **options)


def askquestion(title=None, message=None, **options):
    """Ask a question with Yes and No buttons; returns "yes" or "no"."""
    return _show(title, message, QUESTION, YESNO, **options)


def askokcancel(title=None, message=None, **options):
    """Ask with OK and Cancel buttons; returns True for OK, False otherwise."""
    return _answer(_show(title, message, QUESTION, OKCANCEL, **options), options, OK)


def askyesno(title=None, message=None, **options):
    """Ask with Yes and No buttons; returns True for Yes, False for No."""
    return _answer(_show(title, message, QUESTION, YESNO, **options), options, YES)


def askyesnocancel(title=None, message=None, **options):
    """Ask with Yes, No, and Cancel buttons; returns True, False, or None for Cancel."""
    answer = _show(title, message, QUESTION, YESNOCANCEL, **options)
    if "buttons" in options:
        return answer
    return None if answer == CANCEL else answer == YES


def askretrycancel(title=None, message=None, **options):
    """Ask with Retry and Cancel buttons; returns True for Retry, False otherwise."""
    return _answer(
        _show(title, message, WARNING, RETRYCANCEL, **options), options, RETRY
    )
