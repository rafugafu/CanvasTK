"""A canvas-drawn widget toolkit for tkinter (customtkinter-style):
light/dark appearance modes, color themes, rounded anti-aliased widgets.

    import canvastk as ctk
    ctk.set_appearance_mode("dark")
    root = ctk.Window()
    ctk.Button(root, "Hello").pack(padx=20, pady=20)
    root.mainloop()
"""

__version__ = "1.0"

from ._core import (
    CANVAS_COLOR_THEMES,
    CANVAS_DARK_PALETTE,
    CANVAS_LIGHT_PALETTE,
    CANVAS_WIDGET_THEME,
    CanvasWidget,
    get_appearance_mode,
    load_canvas_image,
    make_font,
    parent_background,
    resolve_color,
    rounded_box_image,
    set_appearance_mode,
    set_theme,
    get_theme,
    reset_theme,
    expand_theme,
    hover_variant,
    window_theme,
)
from .buttons import (
    Button,
    Checkbutton,
    Label,
    Radiobutton,
)
from .sliders import (
    Progressbar,
    Scale,
    Scrollbar,
    Separator,
)
from .popups import (
    Menu,
    MenuBar,
    OptionMenu,
    Tooltip,
)
from .entries import (
    Combobox,
    Entry,
    Spinbox,
    Textbox,
)
from .listbox import (
    Listbox,
)
from .containers import (
    Frame,
    GridPanedwindow,
    Notebook,
    Panedwindow,
    ScrolledFrame,
)
from .windows import (
    Toplevel,
    Window,
)

# The file dialogs and message boxes, used as canvastk.filedialog.askopenfilename(...) like tkinter's.
from . import filedialog, messagebox

__all__ = [
    "filedialog",
    "messagebox",
    "GridPanedwindow",
    "hover_variant",
    "set_theme",
    "get_theme",
    "reset_theme",
    "expand_theme",
    "Button",
    "CANVAS_COLOR_THEMES",
    "CANVAS_DARK_PALETTE",
    "CANVAS_LIGHT_PALETTE",
    "CANVAS_WIDGET_THEME",
    "CanvasWidget",
    "Checkbutton",
    "Combobox",
    "Entry",
    "Frame",
    "Label",
    "Listbox",
    "Menu",
    "MenuBar",
    "Notebook",
    "OptionMenu",
    "Panedwindow",
    "Progressbar",
    "Radiobutton",
    "Scale",
    "Scrollbar",
    "ScrolledFrame",
    "Separator",
    "Spinbox",
    "Textbox",
    "Tooltip",
    "Toplevel",
    "Window",
    "get_appearance_mode",
    "load_canvas_image",
    "make_font",
    "parent_background",
    "resolve_color",
    "rounded_box_image",
    "set_appearance_mode",
]
