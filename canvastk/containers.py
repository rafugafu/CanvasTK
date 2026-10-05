"""Containers: Frame, ScrolledFrame, Notebook, Panedwindow, and GridPanedwindow.

They are tk.Frame subclasses (not canvases): they hold other widgets. Frames
follow the theme's background; the notebook draws its tabs, the panedwindows
their sashes, and the scrolled frame its scroll bars, on canvases.
"""

import tkinter as tk

from ._core import (
    pop_color_parts,
    cross_image,
    expand_theme,
    window_theme,
    CANVAS_WIDGET_THEME,
    CanvasWidget,
    _CANVAS_CHROME_TAG,
    _CANVAS_THEMED_WIDGETS,
    _ChromeCanvas,
    _WHEEL_SEQUENCES,
    _WidgetPlumbing,
    child_background_role,
    make_font,
    measure_content,
    parent_background,
    resolve_color,
    wheel_direction,
)
from .sliders import (
    Scrollbar,
)

# =============================================================================
# Containers: Frame, ScrolledFrame, Notebook, Panedwindow
# =============================================================================


def requested_size_of(widget):
    """(width, height) a container child asks for. A ScrolledFrame's content
    frame can be arbitrarily large, so its scrolling container is measured."""
    if isinstance(widget, ScrolledFrame):
        widget = widget.outer
    return widget.winfo_reqwidth(), widget.winfo_reqheight()


class _ThemedBackground:
    """Gives a tk.Frame-like container a theme-driven background: the role
    comes from its master (a Notebook page is 'surface', a Window is
    'window'); containers inside foreign widgets keep a fixed measured color."""

    def child_background_color(self):
        """A fixed color this container gives its children (or None)."""
        return self._explicit_background

    def _init_background(self, master, background, role, theme=None):
        """Work out this container's background role/color from its master (or an
        explicit bg), and keep its own theme overrides.
        """
        self._theme_overrides = dict(expand_theme(theme or {}))
        if background is None:
            provider = getattr(master, "child_background_color", None)
            background = provider() if provider else None
        self._explicit_background = background
        self.background_role = (
            None if background else (role or child_background_role(master))
        )
        self.child_background_role = self.background_role

    def themed_color(self, widget, key):
        """Theme color for key: global theme, then the window's, then this
        container's own overrides."""
        colors = {
            **CANVAS_WIDGET_THEME,
            **window_theme(widget),
            **self._theme_overrides,
        }
        return resolve_color(widget, colors[key])

    def initial_background(self, master, background):
        """The background to create the Tk widget with (explicit, themed role, or
        measured from the master).
        """
        if background:
            return background
        if self.background_role:
            return self.themed_color(master, self.background_role)
        return parent_background(master)

    def apply_background(self):
        """Set the Tk background from the current theme (when it follows a role)."""
        if self.background_role:
            self.configure(bg=self.themed_color(self, self.background_role))

    def set_theme(self, theme):
        """Change theme keys for this container (its background follows
        them), dynamically; None removes a change. Children keep their own
        themes; use Window.set_theme to recolor a whole window."""
        for key, value in expand_theme(theme).items():
            if value is None:
                self._theme_overrides.pop(key, None)
            else:
                self._theme_overrides[key] = value
        self.refresh_theme()

    def get_theme(self):
        """This container's effective theme (theme key -> color)."""
        return {
            **CANVAS_WIDGET_THEME,
            **window_theme(self),
            **self._theme_overrides,
        }

    def reset_theme(self):
        """Remove every theme change made on this container."""
        self._theme_overrides.clear()
        self.refresh_theme()


class Frame(_ThemedBackground, tk.Frame):
    """A tk.Frame that follows its parent's themed background."""

    def __init__(self, master, background_role=None, theme=None, **kwargs):
        """Create the frame; bg= fixes the color, background_role= picks a theme role,
        theme= overrides theme keys for it.
        """
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self._init_background(master, background, background_role, theme)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(
            self, master, bg=self.initial_background(master, background), **kwargs
        )
        _CANVAS_THEMED_WIDGETS.add(self)

    def refresh_theme(self):
        """The theme changed: re-apply the background."""
        self.apply_background()


# The geometry methods that a ScrolledFrame redirects to its outer container.
_GEOMETRY_METHOD_NAMES = (
    "pack",
    "pack_configure",
    "pack_forget",
    "pack_info",
    "grid",
    "grid_configure",
    "grid_forget",
    "grid_remove",
    "grid_info",
    "place",
    "place_configure",
    "place_forget",
    "place_info",
)


class ScrolledFrame(_ThemedBackground, tk.Frame):
    """A scrolling frame: add children to the ScrolledFrame itself; pack/grid/
    place act on the whole scrolling container.

    orient: 'vertical' (default), 'horizontal' or 'both'. The mouse wheel
    scrolls vertically (horizontally for orient='horizontal'); Shift+wheel
    always scrolls horizontally."""

    _SCROLLBAR_COLOR_OPTIONS = {
        "scrollbar_track_color": "track_color",
        "scrollbar_thumb_color": "thumb_color",
        "scrollbar_thumb_hover_color": "thumb_hover_color",
    }

    def __init__(self, master, orient="vertical", autohide=True, theme=None, **kwargs):
        """Create the scrolled frame.

        orient: which directions scroll. autohide: scroll bars hide when not needed.
        theme / bg / scrollbar_*_color: styling. The returned object is the *content*
        frame; its geometry methods are redirected to the outer container.
        """
        if orient not in ("vertical", "horizontal", "both"):
            raise ValueError("orient must be 'vertical', 'horizontal' or 'both'")
        self.orient = orient
        self._scrolls_vertically = orient in ("vertical", "both")
        self._scrolls_horizontally = orient in ("horizontal", "both")
        scrollbar_theme = {
            own_name: kwargs.pop(name)
            for name, own_name in self._SCROLLBAR_COLOR_OPTIONS.items()
            if name in kwargs
        }
        scrollbar_theme = {**(theme or {}), **scrollbar_theme}
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self._init_background(
            master, background, kwargs.pop("background_role", None), theme
        )
        # Structure: outer frame > viewport canvas (+ scroll bars) > this content frame,
        # shown through a canvas window.
        self.outer = Frame(
            master, background_role=self.background_role, bg=background, theme=theme
        )
        self.viewport = tk.Canvas(
            self.outer,
            bd=0,
            highlightthickness=0,
            bg=self.initial_background(master, background),
        )
        self.outer.grid_rowconfigure(0, weight=1)
        self.outer.grid_columnconfigure(0, weight=1)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar = self.horizontal_scrollbar = None
        if self._scrolls_vertically:
            self.vertical_scrollbar = Scrollbar(
                self.outer,
                orient="vertical",
                command=self.viewport.yview,
                autohide=autohide,
                theme=scrollbar_theme,
            )
            self.vertical_scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
            self.viewport.configure(yscrollcommand=self.vertical_scrollbar.set)
        if self._scrolls_horizontally:
            self.horizontal_scrollbar = Scrollbar(
                self.outer,
                orient="horizontal",
                command=self.viewport.xview,
                autohide=autohide,
                theme=scrollbar_theme,
            )
            self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            self.viewport.configure(xscrollcommand=self.horizontal_scrollbar.set)
        self.scrollbar = self.vertical_scrollbar or self.horizontal_scrollbar
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(
            self,
            self.viewport,
            bg=self.initial_background(master, background),
            **kwargs,
        )
        _CANVAS_THEMED_WIDGETS.add(self)
        self._window = self.viewport.create_window(0, 0, window=self, anchor="nw")
        self._destroying = False
        for name in _GEOMETRY_METHOD_NAMES:
            setattr(self, name, getattr(self.outer, name))
        tk.Frame.bind(self, "<Configure>", lambda _: self._fit_content(), add="+")
        self.viewport.bind("<Configure>", lambda _: self._fit_content(), add="+")
        top = self.winfo_toplevel()
        # The wheel is bound on the whole window (not just this frame) so scrolling
        # works over any child; _on_wheel checks where the pointer is.
        self._wheel_bindings = [
            (sequence, top.bind(sequence, self._on_wheel, add="+"))
            for sequence in _WHEEL_SEQUENCES
        ]
        self._top = top

    def refresh_theme(self):
        """The theme changed: recolor the content frame and the viewport."""
        self.apply_background()
        if self.background_role:
            self.viewport.configure(bg=self.themed_color(self, self.background_role))

    def _fit_content(self):
        """Size the content window: it fills the viewport along axes that do
        not scroll and is at least its natural size along axes that do."""
        view_width = self.viewport.winfo_width()
        view_height = self.viewport.winfo_height()
        width = view_width
        height = view_height
        if self._scrolls_horizontally:
            width = max(self.winfo_reqwidth(), view_width)
        if self._scrolls_vertically:
            height = max(self.winfo_reqheight(), view_height)
        self.viewport.itemconfigure(self._window, width=width, height=height)
        self.viewport.configure(scrollregion=(0, 0, width, height))

    def _on_wheel(self, event):
        """Mouse wheel anywhere in the window: scroll if the pointer is over this frame.

        Widgets that scroll themselves (Text, Listbox, anything with handles_wheel)
        keep their own wheel behavior.
        """
        try:
            target = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        widget = target
        while widget is not None and widget is not self.outer:
            if getattr(widget, "handles_wheel", False) or widget.winfo_class() in (
                "Text",
                "Listbox",
            ):
                return
            widget = widget.master
        if widget is None:
            return
        direction = wheel_direction(event) * 3
        shift_held = bool(event.state & 0x1)
        horizontal = self._scrolls_horizontally and (
            shift_held or not self._scrolls_vertically
        )
        if horizontal:
            if self.winfo_reqwidth() > self.viewport.winfo_width():
                self.viewport.xview_scroll(direction, "units")
        elif self._scrolls_vertically:
            if self.winfo_reqheight() > self.viewport.winfo_height():
                self.viewport.yview_scroll(direction, "units")

    def destroy(self):
        """Remove the wheel bindings and destroy the whole container (the content frame
        is destroyed with it).
        """
        if self._destroying:
            # Re-entered while the outer container is being torn down:
            # destroy normally so this frame's children are destroyed too
            # (and cancel their pending redraws).
            tk.Frame.destroy(self)
            return
        self._destroying = True
        for sequence, funcid in self._wheel_bindings:
            try:
                self._top.unbind(sequence, funcid)
            except tk.TclError:
                pass
        self.outer.destroy()


class _FrameColorParts:
    """configure()/cget() support for a tk.Frame-based widget's _COLOR_PARTS
    and _SETTABLE_OPTIONS (plain attributes applied by apply_settable_options)."""

    _SETTABLE_OPTIONS = ()

    def apply_settable_options(self, options):
        """Store changed plain options (subclasses extend this to re-layout)."""
        for name, value in options.items():
            setattr(self, name, value)

    def configure(self, cnf=None, **kw):
        """configure(): color parts and settable options are ours; everything else goes
        to tk.Frame.
        """
        if cnf is None and not kw:
            return tk.Frame.configure(self)
        if isinstance(cnf, str):
            return tk.Frame.configure(self, cnf)
        if cnf:
            kw = {**cnf, **kw}
        changed = False
        for name in list(kw):
            if name in self._COLOR_PARTS:
                self.set_color_part(name, kw.pop(name))
                changed = True
        settable = {k: kw.pop(k) for k in list(kw) if k in self._SETTABLE_OPTIONS}
        if settable:
            self.apply_settable_options(settable)
            changed = True
        if kw:
            tk.Frame.configure(self, **kw)
        if changed:
            self.on_theme_changed()

    config = configure

    def cget(self, key):
        """cget(): color parts and settable options come from us; the rest from
        tk.Frame.
        """
        if key in self._COLOR_PARTS:
            return self._theme_overrides.get(key)
        if key in self._SETTABLE_OPTIONS:
            return getattr(self, key)
        return tk.Frame.cget(self, key)


class Notebook(_FrameColorParts, _WidgetPlumbing, tk.Frame):
    """Tabs above switchable pages, drawn on a canvas.

    Create each page with the Notebook as its master and add it with add().
    Two styles: 'segmented' (a rounded segmented control above a rounded page;
    the default) and 'classic' (folder-like tabs joined to the page). Tabs can
    be closable and draggable, and scroll with arrows when there are too many
    for the width. Generates <<NotebookTabChanged>>, <<NotebookTabClosed>> and
    <<NotebookTabMoved>>.

    Color options (keyword arguments or configure()): tab_color,
    tab_hover_color, tab_text_color, disabled_tab_text_color,
    selected_tab_color, selected_tab_text_color, border_color, page_color
    (also the background of the pages' Frames), track_color (the segmented
    pill), close_color, close_hover_color, arrow_color, arrow_hover_color,
    arrow_hover_text_color.
    """

    _SETTABLE_OPTIONS = (
        "font",
        "radius",
        "padding",
        "tab_padx",
        "closable",
        "on_close",
        "destroy_on_close",
        "segment_radius",
        "draggable",
    )
    _COLOR_PARTS = (
        "tab_color",
        "tab_hover_color",
        "tab_text_color",
        "disabled_tab_text_color",
        "selected_tab_color",
        "selected_tab_text_color",
        "border_color",
        "page_color",
        "track_color",
        "close_color",
        "close_hover_color",
        "arrow_color",
        "arrow_hover_color",
        "arrow_hover_text_color",
    )

    ARROW_WIDTH = 22
    CLOSE_SIZE = 16
    CLOSE_GAP = 6
    CLOSE_RIGHT_PADDING = 10
    SEGMENT_GAP = 10

    def __init__(
        self,
        master,
        font=None,
        theme=None,
        radius=8,
        padding=8,
        tab_padx=16,
        closable=False,
        on_close=None,
        destroy_on_close=True,
        style="segmented",
        segment_radius=10,
        draggable=False,
        **kwargs,
    ):
        """closable: whether tabs show a close button by default (each tab
        can override with its own closable=True/False). on_close(child) is
        called before a tab closes and can return False to keep it;
        destroy_on_close destroys the page widget when its tab is closed.
        style: 'segmented' (the default: a rounded segmented control above a
        rounded page, like macOS / customtkinter) or 'classic' (folder-like tabs).
        segment_radius: the corner radius of the segmented style's tabs
        (default 10, round corners; None = fully rounded pills; the pill
        behind them follows it).
        draggable: tabs can be reordered by dragging them along the strip."""
        if style not in ("classic", "segmented"):
            raise ValueError("style must be 'classic' or 'segmented'")
        theme = {**(theme or {}), **pop_color_parts(self._COLOR_PARTS, kwargs)}
        self._fixed_size = "width" in kwargs or "height" in kwargs
        self.background_role = child_background_role(master)
        self.child_background_role = "surface"
        self._explicit_background = None
        tk.Frame.__init__(
            self,
            master,
            bd=0,
            highlightthickness=0,
            takefocus=False,
            bg=parent_background(master),
            **kwargs,
        )
        self._init_plumbing(theme)
        self.font = make_font(font)
        self.radius = radius
        self.padding = padding
        self.tab_padx = tab_padx
        self.closable = closable
        self.style = style
        self.segment_radius = segment_radius
        self.draggable = draggable
        self._tab_drag = None
        self.on_close = on_close
        self.destroy_on_close = destroy_on_close
        self.tab_height = self.font.metrics("linespace") + 16
        self._tab_records = []
        self._selected = None
        self._hover_tab = None
        self._tab_offset = 0
        self._reveal_selected = True
        self._tab_boxes = []
        self._arrow_boxes = []
        self._max_tab_offset = 0
        self._visible_spans = []
        self._strip_available = 0
        self._strip_limit = float("inf")
        self._strip_left = 0
        self._tab_shift = 0
        self._close_boxes = []
        self._hover_close = None
        self._hover_arrow = None
        self._size_update_id = None
        self.chrome = _ChromeCanvas(
            self, self._paint, background_from=master, theme=theme
        )
        # The chrome canvas (tabs and page border) fills the notebook and sits behind
        # the pages.
        self.chrome.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(self.chrome)
        # Mouse handling on the chrome: clicks, middle-click close, dragging, hover, and
        # the wheel.
        self.chrome.bind("<ButtonPress-1>", self._on_press, add="+")
        self.chrome.bind("<ButtonPress-2>", self._on_middle_press, add="+")
        self.chrome.bind("<B1-Motion>", self._on_tab_drag, add="+")
        self.chrome.bind("<ButtonRelease-1>", self._on_tab_drop, add="+")
        self.chrome.bind("<Motion>", self._on_motion, add="+")
        self.chrome.bind("<Leave>", lambda _: self._set_hover(None, None), add="+")
        for sequence in _WHEEL_SEQUENCES:
            self.chrome.bind(
                sequence, lambda e: self._scroll_tabs(wheel_direction(e) * 60), add="+"
            )
        tk.Frame.bind(self, "<Left>", lambda _: self._select_neighbor(-1), add="+")
        tk.Frame.bind(self, "<Right>", lambda _: self._select_neighbor(1), add="+")
        tk.Frame.bind(self, "<Configure>", lambda _: self._place_selected(), add="+")

    def schedule_redraw(self):
        """Redraws of the notebook are redraws of its chrome canvas."""
        self.chrome.schedule_redraw()

    def apply_settable_options(self, options):
        """Store changed options; a new font recomputes the tab height; then re-place
        the page and re-layout.
        """
        for name, value in options.items():
            if name == "font":
                value = make_font(value)
            setattr(self, name, value)
        if "font" in options:
            self.tab_height = self.font.metrics("linespace") + 16
        self._place_selected()
        self._tab_changed()

    def child_background_color(self):
        """The page_color override, which the pages' Frames inherit."""
        return self._theme_overrides.get("page_color")

    def on_theme_changed(self):
        """The theme changed: recolor the notebook's own background and its chrome
        (tabs, page border).
        """
        if self.background_role:
            tk.Frame.configure(self, bg=self.color(self.background_role))
        self.chrome.refresh_theme()

    # ---- tab API -------------------------------------------------------------
    def _record_index(self, tab_id):
        """A tab id ('current', 'end', a number, or a page widget) as an index into the
        tab list.
        """
        if tab_id == "current":
            tab_id = self._selected
        if tab_id == "end":
            return len(self._tab_records)
        if isinstance(tab_id, int):
            return tab_id
        for index, record in enumerate(self._tab_records):
            if record["child"] is tab_id or str(record["child"]) == str(tab_id):
                return index
        raise tk.TclError(f"tab {tab_id!r} not found")

    def add(self, child, **options):
        """Append a page as a new tab (options: text, state, image, closable)."""
        self.insert("end", child, **options)

    def insert(self, where, child, text="", state="normal", image=None, closable=None):
        """Insert a page as a tab before `where` ('end' appends); the first tab added is
        selected.
        """
        record = {
            "child": child,
            "text": text,
            "state": state,
            "image": image,
            "closable": closable,
        }
        position = (
            len(self._tab_records) if where == "end" else self._record_index(where)
        )
        self._tab_records.insert(position, record)
        child.place_forget()
        if self._selected is None:
            self.select(child)
        self._tab_changed()

    def forget(self, tab_id):
        """Remove a tab (the page is kept, not destroyed); another tab is selected if it
        was the selected one.
        """
        index = self._record_index(tab_id)
        record = self._tab_records.pop(index)
        record["child"].place_forget()
        if self._selected is record["child"]:
            self._selected = None
            visible = [r for r in self._tab_records if r["state"] == "normal"]
            if visible:
                self.select(visible[min(index, len(visible) - 1)]["child"])
        self._tab_changed()

    def is_closable(self, tab_id):
        """Whether a tab has a close button."""
        return self._record_closable(self._tab_records[self._record_index(tab_id)])

    def _record_closable(self, record):
        """Whether a tab record shows a close button (its own setting, else the
        notebook's; never when disabled).
        """
        closable = self.closable if record["closable"] is None else record["closable"]
        return bool(closable) and record["state"] != "disabled"

    def close_tab(self, tab_id):
        """Close a tab as its close button would: on_close(child) may veto,
        then the tab is removed (and its page destroyed if destroy_on_close)
        and <<NotebookTabClosed>> is generated."""
        child = self._tab_records[self._record_index(tab_id)]["child"]
        if self.on_close is not None and self.on_close(child) is False:
            return
        self.forget(child)
        if self.destroy_on_close:
            child.destroy()
        self.event_generate("<<NotebookTabClosed>>")

    def hide(self, tab_id):
        """Hide a tab (state 'hidden')."""
        self.tab(tab_id, state="hidden")

    def tabs(self):
        """The pages in tab order."""
        return [record["child"] for record in self._tab_records]

    def index(self, tab_id):
        """The position of a tab."""
        return self._record_index(tab_id)

    def select(self, tab_id=None):
        """With no argument: the selected page. With a tab id: select that tab (unless
        it is not 'normal'), showing its page.
        """
        if tab_id is None:
            return self._selected
        index = self._record_index(tab_id)
        record = self._tab_records[index]
        if record["state"] != "normal":
            return None
        previous = self._selected
        self._selected = record["child"]
        self._reveal_selected = True
        self._place_selected()
        self._tab_changed(redraw_only=True)
        if previous is not self._selected:
            self.event_generate("<<NotebookTabChanged>>")
        return None

    def tab(self, tab_id, option=None, **options):
        """Read (option) or change (options) a tab's text, state, image, or closable."""
        record = self._tab_records[self._record_index(tab_id)]
        if options:
            record.update(options)
            if record["state"] != "normal" and self._selected is record["child"]:
                self._select_neighbor(1) or self._select_neighbor(-1)
            self._tab_changed()
            return None
        return dict(record) if option is None else record[option]

    def enable_traversal(self):
        """Make Control-Tab / Control-Shift-Tab (in the window) select the next /
        previous tab.
        """
        self.winfo_toplevel().bind(
            "<Control-Tab>", lambda _: self._select_neighbor(1), add="+"
        )
        self.winfo_toplevel().bind(
            "<Control-Shift-Tab>", lambda _: self._select_neighbor(-1), add="+"
        )

    def _select_neighbor(self, step):
        """Select the next (+1) or previous (-1) usable tab, wrapping around; False if
        there is none.
        """
        usable = [r["child"] for r in self._tab_records if r["state"] == "normal"]
        if not usable or self._selected not in usable:
            return False
        target = usable[(usable.index(self._selected) + step) % len(usable)]
        if target is self._selected:
            return False
        self.select(target)
        return True

    # ---- layout ----------------------------------------------------------------
    def _tab_changed(self, redraw_only=False):
        """The tabs changed: redraw, and (unless only the look changed) recompute the
        requested size.
        """
        self.chrome.schedule_redraw()
        if not redraw_only and self._size_update_id is None:
            self._size_update_id = self.call_later(None, self.update_size)

    def update_size(self):
        """Recompute the requested size from the tabs' children."""
        self._size_update_id = None
        if self._fixed_size or not self._tab_records:
            return
        pad = self.padding
        sizes = [requested_size_of(r["child"]) for r in self._tab_records]
        width = max(w for w, _ in sizes) + 2 * pad
        height = max(h for _, h in sizes)
        tk.Frame.configure(
            self, width=width, height=height + self._content_top() + 2 * pad
        )

    def _place_selected(self):
        """Show the selected page in the page area and hide the others."""
        pad = self.padding
        for record in self._tab_records:
            if record["child"] is self._selected:
                record["child"].place(
                    x=pad,
                    y=self._content_top() + pad,
                    relwidth=1,
                    relheight=1,
                    width=-2 * pad,
                    height=-(self._content_top() + 2 * pad),
                )
            else:
                record["child"].place_forget()

    def _content_top(self):
        """Where the page area starts, below the tab strip."""
        return self.tab_height + (self.SEGMENT_GAP if self.style == "segmented" else 0)

    def _tab_width(self, record):
        """The pixel width of one tab: its label plus padding (and the close button)."""
        width, _ = measure_content(record["text"], record["image"], self.font)
        if self._record_closable(record):
            return (
                self.tab_padx
                + width
                + self.CLOSE_GAP
                + self.CLOSE_SIZE
                + self.CLOSE_RIGHT_PADDING
            )
        return width + 2 * self.tab_padx

    def _scroll_one_tab(self, direction):
        """Scroll so the next hidden tab in that direction comes into view."""
        offset = self._tab_offset
        if direction > 0:
            for left, right in self._visible_spans:
                if right - offset > self._strip_available:
                    target = right - self._strip_available + 4
                    break
            else:
                target = self._max_tab_offset
        else:
            for left, right in reversed(self._visible_spans):
                if left - offset < 0:
                    target = left - 4
                    break
            else:
                target = 0
        self._scroll_tabs(target - offset)

    def _scroll_tabs(self, amount):
        """Scroll the tab strip by some pixels (clamped)."""
        offset = min(max(0, self._tab_offset + amount), self._max_tab_offset)
        if offset != self._tab_offset:
            self._tab_offset = offset
            self.chrome.schedule_redraw()

    # ---- interaction -------------------------------------------------------------
    def _tab_at(self, x, y):
        """The tab under a point of the strip (not under the scroll arrows), or None."""
        if y > self.tab_height or not self._strip_left <= x < self._strip_limit:
            return None
        for left, right, index in self._tab_boxes:
            if left <= x < right:
                return index
        return None

    def _close_at(self, x, y):
        """The tab whose close button is under a point, or None."""
        if y > self.tab_height or not self._strip_left <= x < self._strip_limit:
            return None
        for left, right, index in self._close_boxes:
            if left <= x < right:
                return index
        return None

    def _arrow_under_pointer(self):
        """The arrow the mouse pointer is over right now (read at paint time,
        so the highlight survives redraws without any new motion event)."""
        chrome = self.chrome
        x = chrome.winfo_pointerx() - chrome.winfo_rootx()
        y = chrome.winfo_pointery() - chrome.winfo_rooty()
        if 0 <= x < chrome.winfo_width() and 0 <= y < chrome.winfo_height():
            return self._arrow_at(x, y)
        return None

    def _arrow_at(self, x, y):
        """-1 / +1 when over the left / right scroll arrow, else None."""
        if y <= self.tab_height:
            for left, right, direction in self._arrow_boxes:
                if left <= x < right:
                    return direction
        return None

    def _set_hover(self, index, close_index, arrow=None):
        """Remember which tab / close button / arrow is hovered (redraws only on
        change).
        """
        state = (index, close_index, arrow)
        if state != (self._hover_tab, self._hover_close, self._hover_arrow):
            self._hover_tab, self._hover_close, self._hover_arrow = state
            self.chrome.schedule_redraw()

    def _on_motion(self, event):
        """Pointer moved over the strip: update the hover state."""
        self._set_hover(
            self._tab_at(event.x, event.y),
            self._close_at(event.x, event.y),
            self._arrow_at(event.x, event.y),
        )

    def _on_middle_press(self, event):
        """Middle click on a closable tab closes it."""
        index = self._tab_at(event.x, event.y)
        if index is not None and self._record_closable(self._tab_records[index]):
            self.close_tab(index)

    def _on_press(self, event):
        """Mouse down: a scroll arrow scrolls, a close button closes, a tab is selected
        (and may start a drag).
        """
        for left, right, direction in self._arrow_boxes:
            if left <= event.x < right and event.y <= self.tab_height:
                self._scroll_one_tab(direction)
                return
        close_index = self._close_at(event.x, event.y)
        if close_index is not None:
            self.close_tab(close_index)
            return
        index = self._tab_at(event.x, event.y)
        if index is not None:
            tk.Frame.focus_set(self)
            self.select(index)
            if self.draggable:
                self._tab_drag = {"index": index, "x": event.x, "active": False}

    # ---- dragging tabs ---------------------------------------------------------
    def move(self, tab_id, position):
        """Move a tab to a new position (a number or 'end'); the selected tab
        stays selected."""
        records = self._tab_records
        record = records.pop(self._record_index(tab_id))
        target = len(records) if position == "end" else self._record_index(position)
        records.insert(min(max(target, 0), len(records)), record)
        self._tab_changed(redraw_only=True)

    def _on_tab_drag(self, event):
        """Dragging a tab: after a few pixels of movement, swap it with a neighbor whenever the
        pointer passes the neighbor's middle (live reordering), scrolling at the strip's ends.
        """
        drag = self._tab_drag
        if drag is None:
            return
        if not drag["active"]:
            if abs(event.x - drag["x"]) < 6:
                return
            drag["active"] = True
            self.chrome.configure(cursor="fleur")
        # Near the ends of an overflowing strip, scroll to reach more tabs.
        if self._max_tab_offset:
            if event.x < self._strip_left + 16:
                self._scroll_tabs(-12)
            elif event.x > self._strip_limit - 16:
                self._scroll_tabs(12)
        current = drag["index"]
        for left, right, index in self._tab_boxes:
            if index == current or not left <= event.x < right:
                continue
            # Swap only after the pointer passes the middle of the neighbor,
            # so a tab does not flicker back and forth at the border.
            middle = (left + right) / 2
            if (index > current and event.x >= middle) or (
                index < current and event.x <= middle
            ):
                self.move(current, index)
                drag["index"] = index
                self._hover_tab = index
                # Redraw now: the tab boxes used above must match the new order.
                self.chrome.update_idletasks()
            break

    def _on_tab_drop(self, _):
        """Mouse up: end the drag (and announce <<NotebookTabMoved>> if a tab was
        moved).
        """
        drag, self._tab_drag = self._tab_drag, None
        if drag is not None and drag["active"]:
            self.chrome.configure(cursor="")
            self.event_generate("<<NotebookTabMoved>>")

    # ---- painting -------------------------------------------------------------------
    def _layout_tabs(self, width):
        """Tab spans for the current width: (visible, spans, selected_index,
        overflow, available, total) with spans mapping index -> (left, right)
        before scrolling; also keeps the scroll offset valid."""
        visible = [
            (i, r) for i, r in enumerate(self._tab_records) if r["state"] != "hidden"
        ]
        selected_index = next(
            (i for i, r in visible if r["child"] is self._selected), None
        )
        # Do the tabs fit? If not, reserve room for an arrow at each end and scroll.
        total = sum(self._tab_width(r) + 2 for _, r in visible) + 4
        overflow = total > width
        available = width - (2 * self.ARROW_WIDTH if overflow else 0)
        x = 4
        # Segmented tabs are centered when they fit.
        if self.style == "segmented" and not overflow:
            x += (width - total) / 2
        spans = {}
        for i, record in visible:
            tab_width = self._tab_width(record)
            spans[i] = (x, x + tab_width)
            x += tab_width + 2
        if overflow and selected_index is not None and self._reveal_selected:
            # Only when the selection changed: otherwise the scroll arrows
            # could never move the selected tab out of view.
            left, right = spans[selected_index]
            if left - self._tab_offset < 0:
                self._tab_offset = left - 4
            elif right - self._tab_offset > available:
                self._tab_offset = right - available + 4
        self._reveal_selected = False
        self._tab_offset = (
            max(0, min(self._tab_offset, total - available)) if overflow else 0
        )
        self._max_tab_offset = max(0, total - available)
        self._visible_spans = [spans[i] for i, _ in visible]
        self._strip_available = available
        self._strip_left = self.ARROW_WIDTH if overflow else 0
        self._strip_limit = self._strip_left + available
        # Screen x of a tab = its layout x minus this shift (scrolling, plus the left
        # arrow's width).
        self._tab_shift = self._tab_offset - self._strip_left
        return visible, spans, selected_index, overflow, available, total

    def _paint(self, chrome, width, height):
        """Paint the chrome: the layout, the style's tabs and page border, then the
        scroll arrows if the tabs overflow.
        """
        layout = self._layout_tabs(width)
        self._tab_boxes = []
        self._close_boxes = []
        if self.style == "segmented":
            self._paint_segmented(chrome, width, height, *layout)
        else:
            self._paint_classic(chrome, width, height, *layout)
        self._paint_scroll_arrows(chrome, width, layout[3])

    def _paint_scroll_arrows(self, chrome, width, overflow):
        """Cover the tabs scrolled under the ends and draw the left/right arrows (dimmed
        at the limits, highlighted when hovered).
        """
        tab_height = self.tab_height
        self._arrow_boxes = []
        if not overflow:
            return
        bottom_edge = tab_height - (1 if self.style == "classic" else 0)
        # Hide the parts of tabs scrolled under the arrows.
        for cover_left in (0, width - self.ARROW_WIDTH):
            chrome.create_rectangle(
                cover_left,
                0,
                cover_left + self.ARROW_WIDTH,
                bottom_edge,
                fill=chrome.cget("bg"),
                width=0,
                tags=_CANVAS_CHROME_TAG,
            )
        # The left arrow sits at the left end of the strip, the right arrow
        # at the right end.
        for box_left, direction in (
            (0, -1),
            (width - self.ARROW_WIDTH, 1),
        ):
            self._arrow_boxes.append((box_left, box_left + self.ARROW_WIDTH, direction))
            at_limit = (
                self._tab_offset <= 0
                if direction < 0
                else self._tab_offset >= self._max_tab_offset
            )
            if at_limit:
                color = self.color("text_disabled")
            elif direction == self._arrow_under_pointer():
                bottom = tab_height - (4 if self.style == "classic" else 3)
                chrome.draw_box(
                    box_left + 2,
                    3,
                    box_left + self.ARROW_WIDTH - 2,
                    bottom,
                    self.part("arrow_hover_color", "accent_hover"),
                    radius=6,
                )
                color = self.part("arrow_hover_text_color", "accent_text")
            else:
                color = self.part("arrow_color", "text_muted")
            chrome.draw_chevron(
                box_left + self.ARROW_WIDTH / 2,
                tab_height / 2,
                "left" if direction < 0 else "right",
                color,
                size=4,
            )

    def _paint_segmented(
        self,
        chrome,
        width,
        height,
        visible,
        spans,
        selected_index,
        overflow,
        available,
        total,
    ):
        """Paint the segmented style: rounded page box, the pill behind the tabs, and
        the tab segments with their labels.
        """
        tab_height = self.tab_height
        border = self.part("border_color", "border")
        chrome.draw_box(
            0,
            self._content_top(),
            width,
            height,
            self.part("page_color", "surface"),
            border,
            1,
            self.radius,
        )
        if not visible:
            return
        offset = self._tab_shift
        first_left = spans[visible[0][0]][0] - offset
        last_right = spans[visible[-1][0]][1] - offset
        if overflow:
            track_left, track_right = self._strip_left, self._strip_limit
        else:
            track_left = max(first_left - 3, 0)
            track_right = min(last_right + 3, width)
        chrome.draw_box(
            track_left,
            0,
            track_right,
            tab_height,
            self.part("track_color", "neutral"),
            radius=(
                tab_height / 2
                if self.segment_radius is None
                else self.segment_radius + 3
            ),
        )
        # Segments are 3 px inside the pill on every side.
        segment_height = tab_height - 6
        segment_radius = (
            segment_height / 2 if self.segment_radius is None else self.segment_radius
        )
        for i, record in visible:
            left, right = (v - offset for v in spans[i])
            disabled = record["state"] == "disabled"
            selected = i == selected_index
            if selected:
                fill = self.part("selected_tab_color", "accent")
            elif i == self._hover_tab and not disabled:
                fill = self.part("tab_hover_color", "neutral_hover")
            else:
                fill = None
            if fill is not None:
                chrome.draw_box(
                    left, 3, right, 3 + segment_height, fill, radius=segment_radius
                )
            if selected:
                color = self.part("selected_tab_text_color", "accent_text")
            elif disabled:
                color = self.part("disabled_tab_text_color", "text_disabled")
            else:
                color = self.part("tab_text_color", "text")
            self._draw_tab_label(
                chrome, left, right, tab_height - 1, record, disabled, False, color
            )
            self._draw_close_button(
                chrome,
                left,
                tab_height - 1,
                record,
                i,
                color if selected else None,
            )
            self._tab_boxes.append((left, right, i))

    def _paint_classic(
        self,
        chrome,
        width,
        height,
        visible,
        spans,
        selected_index,
        overflow,
        available,
        total,
    ):
        """Paint the classic style: the page border, the unselected tabs, then the selected tab
        drawn over the page's top border so it joins the page.
        """
        tab_height = self.tab_height
        surface = self.part("page_color", "surface")
        selected_fill = (
            self.rc(self._theme_overrides["selected_tab_color"])
            if self._theme_overrides.get("selected_tab_color")
            else surface
        )
        border = self.part("border_color", "border")
        radius = self.radius
        # The page's top-left corner is square when the first tab is selected (the tab
        # continues it).
        first_selected = bool(visible) and visible[0][0] == selected_index
        chrome.draw_box(
            0,
            tab_height - 1,
            width,
            height,
            surface,
            border,
            1,
            radius,
            corners=(not first_selected, True, True, True),
        )
        selected_box = None
        for i, record in visible:
            left, right = (v - self._tab_shift for v in spans[i])
            disabled = record["state"] == "disabled"
            if i == selected_index:
                selected_box = (left, right, record, i)
                self._tab_boxes.append((left, right, i))
                continue
            if i == self._hover_tab and not disabled:
                fill = self.part("tab_hover_color", "neutral_hover")
            else:
                fill = self.part("tab_color", "neutral")
            chrome.draw_box(
                left,
                3,
                right,
                tab_height,
                fill,
                border,
                1,
                radius,
                corners=(True, True, False, False),
            )
            self._draw_tab_label(
                chrome, left, right, tab_height, record, disabled, False
            )
            self._draw_close_button(chrome, left, tab_height, record, i)
            self._tab_boxes.append((left, right, i))
        # The selected tab is drawn last, over the page border, and its bottom edge is
        # covered so it joins the page.
        if selected_box is not None:
            left, right, record, selected_tab_index = selected_box
            chrome.draw_box(
                left - 2,
                0,
                right + 2,
                tab_height + 1,
                selected_fill,
                border,
                1,
                radius,
                corners=(True, True, False, False),
            )
            chrome.create_rectangle(
                left - 1,
                tab_height - 1,
                right + 1,
                tab_height + 1,
                fill=selected_fill,
                width=0,
                tags=_CANVAS_CHROME_TAG,
            )
            self._draw_tab_label(chrome, left, right, tab_height, record, False, True)
            self._draw_close_button(
                chrome, left, tab_height, record, selected_tab_index
            )

    def _draw_tab_label(
        self, chrome, left, right, tab_height, record, disabled, selected, color=None
    ):
        """Draw a tab's image and text, vertically centered in the strip (color by state
        unless given).
        """
        if color is None:
            if disabled:
                color = self.part("disabled_tab_text_color", "text_disabled")
            elif selected:
                color = self.part("selected_tab_text_color", "text")
            else:
                color = self.part("tab_text_color", "text")
        chrome.font = self.font
        label_width, _ = measure_content(record["text"], record["image"], self.font)
        label_left = left + self.tab_padx
        chrome.draw_content(
            (
                label_left,
                0,
                label_left + label_width,
                tab_height + (1 if selected else 0),
            ),
            color,
            record["text"],
            record["image"],
            anchor="w",
        )

    def _draw_close_button(
        self, chrome, left, tab_height, record, index, base_color=None
    ):
        """Draw a tab's close × (red when hovered) and remember where it is for hit
        testing.
        """
        if not self._record_closable(record):
            return
        label_width, _ = measure_content(record["text"], record["image"], self.font)
        size = self.CLOSE_SIZE
        center_x = left + self.tab_padx + label_width + self.CLOSE_GAP + size / 2
        center_y = tab_height / 2 + 1
        hovered = index == self._hover_close
        self._close_boxes.append((center_x - size / 2, center_x + size / 2, index))
        image = cross_image(
            size,
            (
                self.part("close_hover_color", "danger")
                if hovered
                else (base_color or self.part("close_color", "text_muted"))
            ),
        )
        chrome._images.append(image)
        chrome.create_image(
            round(center_x - size / 2),
            round(center_y - size / 2),
            anchor="nw",
            image=image,
            tags=_CANVAS_CHROME_TAG,
        )


class _Sash(CanvasWidget):
    # Sash thickness in px.
    """The draggable divider between two panes of a Panedwindow/GridPanedwindow: a line
    with a three-dot grip.
    """

    THICKNESS = 6
    # How close (px) to a point where sashes meet the pointer must be to grab
    # the meeting point (a "junction") instead of just this one sash.
    JUNCTION_REACH = 9

    def __init__(self, master, owner, index, theme=None):
        """Create the sash for `owner` (anything with orient, drag_sash, and part);
        `index` is the pane boundary it belongs to.

        If the owner also has junction_at / drag_junction / set_hot / sash_is_hot
        (a GridPanedwindow split does), pressing near a point where this sash
        meets a perpendicular one drags both together.
        """
        orient = owner.orient
        super().__init__(
            master,
            theme=theme,
            width=self.THICKNESS if orient == "horizontal" else 10,
            height=10 if orient == "horizontal" else self.THICKNESS,
            cursor=(
                "sb_h_double_arrow" if orient == "horizontal" else "sb_v_double_arrow"
            ),
        )
        self.owner = owner
        self.index = index
        self._resize_cursor = (
            "sb_h_double_arrow" if orient == "horizontal" else "sb_v_double_arrow"
        )
        # The junction being dragged (set on a press near one), else None.
        self._junction = None
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.schedule_redraw()

    def _junction_at(self, event):
        """The junction the pointer is near on this sash, or None (also None when
        the owner has no junctions, as for a plain Panedwindow).
        """
        finder = getattr(self.owner, "junction_at", None)
        return finder(self.index, event) if finder else None

    def _on_motion(self, event):
        """Pointer moved over the sash: near a junction, show the move cursor and
        light up every sash that meets there; otherwise the normal resize cursor.
        """
        if self._junction is not None:
            return
        junction = self._junction_at(event)
        cursor = "fleur" if junction else self._resize_cursor
        if cursor != self.cget("cursor"):
            self.configure(cursor=cursor)
        setter = getattr(self.owner, "set_hot", None)
        if setter:
            setter(junction)

    def _on_leave(self, _):
        """Pointer left the sash: stop highlighting a junction (unless dragging it)."""
        setter = getattr(self.owner, "set_hot", None)
        if setter and self._junction is None:
            setter(None)

    def _on_press(self, event):
        """Mouse down: start dragging, as a junction if the pointer is near one."""
        self._junction = self._junction_at(event)
        self._set_pressed(True)
        setter = getattr(self.owner, "set_hot", None)
        if setter:
            setter(self._junction)

    def _on_release(self, _):
        """Mouse up: end the drag (and any junction highlight)."""
        self._junction = None
        self._set_pressed(False)
        setter = getattr(self.owner, "set_hot", None)
        if setter:
            setter(None)

    def _set_pressed(self, value):
        """Remember whether the sash is being dragged (it is drawn in the active color)."""
        self._pressed = value
        self.schedule_redraw()

    def _on_drag(self, event):
        """Dragging: move this sash (or, from a junction, every sash that meets
        there) to the pointer, in screen coordinates.
        """
        if self._junction is not None:
            self.owner.drag_junction(self._junction, event.x_root, event.y_root)
            return
        position = event.x_root if self.owner.orient == "horizontal" else event.y_root
        self.owner.drag_sash(self.index, position)

    def redraw(self, width, height):
        """Draw the line and the grip dots (active colors while hovered, dragged, or
        taking part in the junction under the pointer).
        """
        horizontal = self.owner.orient == "horizontal"
        hot = getattr(self.owner, "sash_is_hot", None)
        active = self._hovered or self._pressed or bool(hot and hot(self.index))
        owner = self.owner
        color = (
            owner.part("sash_active_color", "accent")
            if active
            else owner.part("sash_color", "separator")
        )
        if horizontal:
            self.create_rectangle(
                width / 2 - 1,
                0,
                width / 2 + 1,
                height,
                fill=color,
                width=0,
                tags=_CANVAS_CHROME_TAG,
            )
        else:
            self.create_rectangle(
                0,
                height / 2 - 1,
                width,
                height / 2 + 1,
                fill=color,
                width=0,
                tags=_CANVAS_CHROME_TAG,
            )
        dot = (
            owner.part("grip_active_color", "accent")
            if active
            else owner.part("grip_color", "thumb")
        )
        for offset in (-8, 0, 8):
            cx, cy = (
                (width / 2, height / 2 + offset)
                if horizontal
                else (width / 2 + offset, height / 2)
            )
            self.draw_box(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, dot, radius=1.5)


class Panedwindow(_FrameColorParts, _WidgetPlumbing, tk.Frame):
    """Resizable panes separated by draggable canvas-drawn sashes.

    Color options: sash_color, sash_active_color (hovered/dragged),
    grip_color, grip_active_color."""

    _COLOR_PARTS = (
        "sash_color",
        "sash_active_color",
        "grip_color",
        "grip_active_color",
    )

    # No pane can be dragged smaller than this many px.
    MINIMUM_PANE_SIZE = 24

    def __init__(self, master, orient="horizontal", theme=None, **kwargs):
        """Create the panedwindow; orient is 'horizontal' (panes side by side) or
        'vertical' (stacked).
        """
        theme = {**(theme or {}), **pop_color_parts(self._COLOR_PARTS, kwargs)}
        self.background_role = child_background_role(master)
        self.child_background_role = self.background_role
        kwargs.setdefault("bg", parent_background(master))
        tk.Frame.__init__(self, master, bd=0, highlightthickness=0, **kwargs)
        self._init_plumbing(theme)
        self.orient = orient
        # Each pane is a dict: child widget, weight, and current size in px.
        self._panes = []
        self._sashes = []
        tk.Frame.bind(self, "<Configure>", lambda _: self._layout(), add="+")

    def on_theme_changed(self):
        """The theme changed: recolor the background and redraw the sashes."""
        if self.background_role:
            tk.Frame.configure(self, bg=self.color(self.background_role))
        for sash in self._sashes:
            sash.schedule_redraw()

    def _pane_index(self, pane):
        """A pane (widget or number) as an index into the pane list."""
        if isinstance(pane, int):
            return pane
        for index, record in enumerate(self._panes):
            if record["child"] is pane or str(record["child"]) == str(pane):
                return index
        raise tk.TclError(f"pane {pane!r} not found")

    def add(self, child, weight=0, **_ignored):
        """Append a pane; weight says how it shares extra space when the window is
        resized (0 = keeps its size).
        """
        self.insert("end", child, weight)

    def insert(self, where, child, weight=0, **_ignored):
        """Insert a pane before `where`; it starts at the size it asks for."""
        position = len(self._panes) if where == "end" else self._pane_index(where)
        horizontal = self.orient == "horizontal"
        requested = requested_size_of(child)
        size = requested[0] if horizontal else requested[1]
        self._panes.insert(
            position, {"child": child, "weight": weight, "size": max(size, 1)}
        )
        if len(self._panes) > 1:
            self._sashes.append(
                _Sash(self, self, len(self._sashes), theme=self._theme_overrides)
            )
        self._layout()

    def forget(self, pane):
        """Remove a pane (the widget is kept, not destroyed)."""
        record = self._panes.pop(self._pane_index(pane))
        record["child"].place_forget()
        if self._sashes:
            self._sashes.pop().destroy()
        self._layout()

    remove = forget

    def panes(self):
        """The panes in order."""
        return [record["child"] for record in self._panes]

    def paneconfigure(self, pane, weight=None, **_ignored):
        """Change a pane's weight."""
        if weight is not None:
            self._panes[self._pane_index(pane)]["weight"] = weight

    pane = paneconfigure

    def sashpos(self, index, newpos=None):
        """The position of sash `index` in px; with newpos, move it there first."""
        start = (
            sum(r["size"] for r in self._panes[: index + 1]) + index * _Sash.THICKNESS
        )
        if newpos is not None:
            self._move_sash(index, newpos)
        return int(start)

    def drag_sash(self, index, root_position):
        """A sash is being dragged: move it to the pointer's screen position."""
        origin = (
            self.winfo_rootx() if self.orient == "horizontal" else self.winfo_rooty()
        )
        self._move_sash(index, root_position - origin - _Sash.THICKNESS / 2)

    def _move_sash(self, index, boundary):
        """Move the boundary between two panes to a position, keeping both at least the
        minimum size.
        """
        before = self._panes[index]
        after = self._panes[index + 1]
        start = sum(r["size"] for r in self._panes[:index]) + index * _Sash.THICKNESS
        total = before["size"] + after["size"]
        new_size = min(
            max(boundary - start, self.MINIMUM_PANE_SIZE),
            total - self.MINIMUM_PANE_SIZE,
        )
        before["size"], after["size"] = new_size, total - new_size
        self._place_all()

    def _fit_sizes(self, available):
        """Make the pane sizes add up to `available` px: the difference is spread over the
        panes by weight (the last pane if all weights are 0), never below the minimum size.
        """
        panes = self._panes
        delta = available - sum(r["size"] for r in panes)
        if abs(delta) < 0.5:
            return
        weights = [r["weight"] for r in panes]
        if not any(weights):
            weights = [0] * (len(panes) - 1) + [1]
        total_weight = sum(weights)
        for record, weight in zip(panes, weights):
            record["size"] += delta * weight / total_weight
        for _ in range(len(panes)):
            for record in panes:
                record["size"] = max(record["size"], self.MINIMUM_PANE_SIZE)
            excess = sum(r["size"] for r in panes) - available
            if abs(excess) < 0.5:
                break
            shrinkable = [
                r
                for r in panes
                if r["size"] - excess / len(panes) >= self.MINIMUM_PANE_SIZE
            ] or panes
            for record in shrinkable:
                record["size"] -= excess / len(shrinkable)

    def _layout(self):
        """The window changed size: fit the pane sizes to it and place everything."""
        if not self._panes:
            return
        horizontal = self.orient == "horizontal"
        length = self.winfo_width() if horizontal else self.winfo_height()
        if length <= 1:
            return
        self._fit_sizes(length - _Sash.THICKNESS * (len(self._panes) - 1))
        self._place_all()

    def _place_all(self):
        """Place every pane and sash from the stored sizes."""
        horizontal = self.orient == "horizontal"
        position = 0
        for index, record in enumerate(self._panes):
            size = round(record["size"])
            if horizontal:
                record["child"].place(x=position, y=0, width=size, relheight=1)
            else:
                record["child"].place(x=0, y=position, height=size, relwidth=1)
            position += size
            if index < len(self._sashes):
                sash = self._sashes[index]
                sash.index = index
                if horizontal:
                    sash.place(x=position, y=0, width=_Sash.THICKNESS, relheight=1)
                else:
                    sash.place(x=0, y=position, height=_Sash.THICKNESS, relwidth=1)
                position += _Sash.THICKNESS


class _PaneLeaf:
    """A pane of a GridPanedwindow: one child widget."""

    def __init__(self, child):
        """Wrap the child widget; `parent` is set when it is put into the tree."""
        self.child = child
        self.parent = None


class _PaneSplit:
    """A row or column of panes inside a GridPanedwindow. Its children are
    leaves or further splits, with the share of the space each one takes."""

    def __init__(self, grid, orient):
        """Create an empty split in the given orientation."""
        self.grid = grid
        self.orient = orient
        self.children = []
        self.fractions = []
        self.sashes = []
        self.parent = None
        self.rect = (0, 0, 1, 1)

    # The sashes of this split talk to it as their "owner".
    def part(self, name, default_key):
        """Colors for the sashes come from the GridPanedwindow's options."""
        return self.grid.part(name, default_key)

    def drag_sash(self, index, root_position):
        """A sash of this split is dragged: let the GridPanedwindow resize the two
        neighbors.
        """
        self.grid._drag_sash(self, index, root_position)

    def junction_at(self, index, event):
        """The junction of sash `index` near the pointer (see GridPanedwindow), or None."""
        return self.grid.junction_at(self, index, event)

    def drag_junction(self, junction, root_x, root_y):
        """A junction is dragged: move every sash that meets there."""
        self.grid.drag_junction(junction, root_x, root_y)

    def set_hot(self, junction):
        """Highlight (or, with None, stop highlighting) a junction's sashes."""
        self.grid.set_hot(junction)

    def sash_is_hot(self, index):
        """Whether sash `index` of this split is part of the highlighted junction."""
        return self.grid.is_hot(self, index)


class GridPanedwindow(_FrameColorParts, _WidgetPlumbing, tk.Frame):
    """Resizable panes in one widget that can be split in both directions, as
    often as you like: split any pane horizontally or vertically, and split
    the new panes again. Every split has its own draggable sashes, and where
    a sash meets a perpendicular one (a "junction") dragging near the meeting
    point moves all the sashes that meet there at once.

    Make the panes with the GridPanedwindow as their master. The first pane
    is added with add(); further panes with split(existing_pane, new_pane,
    orient) or add(new_pane, orient) (appended to the whole layout).

    Color options: sash_color, sash_active_color (hovered/dragged),
    grip_color, grip_active_color."""

    _COLOR_PARTS = (
        "sash_color",
        "sash_active_color",
        "grip_color",
        "grip_active_color",
    )

    MINIMUM_PANE_SIZE = 24

    def __init__(self, master, theme=None, **kwargs):
        """Create an empty grid panedwindow."""
        theme = {**(theme or {}), **pop_color_parts(self._COLOR_PARTS, kwargs)}
        self.background_role = child_background_role(master)
        self.child_background_role = self.background_role
        kwargs.setdefault("bg", parent_background(master))
        tk.Frame.__init__(self, master, bd=0, highlightthickness=0, **kwargs)
        self._init_plumbing(theme)
        self._pane_tree = None
        # Junctions: the points where a sash meets a perpendicular sash, found
        # again after every layout, and the one currently highlighted.
        self._junctions = []
        self._hot_junction = None
        tk.Frame.bind(self, "<Configure>", lambda _: self._layout(), add="+")

    def on_theme_changed(self):
        """The theme changed: recolor the background and redraw all the sashes."""
        if self.background_role:
            tk.Frame.configure(self, bg=self.color(self.background_role))
        for split in self._splits():
            for sash in split.sashes:
                sash.schedule_redraw()

    # ---- the tree of panes -----------------------------------------------------
    def _walk(self, node=None):
        """Every node, parents before children."""
        node = self._pane_tree if node is None else node
        if node is None:
            return
        yield node
        if isinstance(node, _PaneSplit):
            for child in node.children:
                yield from self._walk(child)

    def _splits(self):
        """All the splits (inner nodes) of the layout tree."""
        return [node for node in self._walk() if isinstance(node, _PaneSplit)]

    def _leaf_of(self, pane):
        """The tree leaf holding a pane widget."""
        for node in self._walk():
            if isinstance(node, _PaneLeaf) and (
                node.child is pane or str(node.child) == str(pane)
            ):
                return node
        raise tk.TclError(f"pane {pane!r} not found")

    def _replace(self, old, new):
        """Put node `new` where node `old` is in the tree."""
        parent = old.parent
        new.parent = parent
        if parent is None:
            self._pane_tree = new
        else:
            parent.children[parent.children.index(old)] = new

    def _ensure_sashes(self, split):
        """Make a split have exactly one sash between each pair of its children."""
        wanted = len(split.children) - 1
        while len(split.sashes) < wanted:
            split.sashes.append(
                _Sash(self, split, len(split.sashes), theme=self._theme_overrides)
            )
        while len(split.sashes) > wanted:
            split.sashes.pop().destroy()

    # ---- public API ------------------------------------------------------------
    def panes(self):
        """The panes (child widgets) in layout order."""
        return [node.child for node in self._walk() if isinstance(node, _PaneLeaf)]

    def add(self, child, orient="horizontal"):
        """Add the first pane, or append `child` to the whole layout: after
        everything along orient ('horizontal' = to the right, 'vertical' =
        below), sharing the space equally with the existing top-level panes."""
        leaf = _PaneLeaf(child)
        if self._pane_tree is None:
            self._pane_tree = leaf
        else:
            root = self._pane_tree
            if isinstance(root, _PaneSplit) and root.orient == orient:
                count = len(root.children)
                share = 1 / (count + 1)
                root.fractions = [f * (1 - share) for f in root.fractions] + [share]
                root.children.append(leaf)
                leaf.parent = root
                self._ensure_sashes(root)
            else:
                split = _PaneSplit(self, orient)
                split.children = [root, leaf]
                split.fractions = [0.5, 0.5]
                root.parent = split
                leaf.parent = split
                self._pane_tree = split
                self._ensure_sashes(split)
        self._layout()

    def split(self, target, child, orient="horizontal", before=False, ratio=0.5):
        """Split the pane `target` in two: `child` goes beside it, to its
        right ('horizontal') or below it ('vertical'), or to its left / above
        it with before=True. `ratio` is the share of the target's space that
        the new pane takes. The target may already be inside a split of the
        other direction; only the target's own space is divided."""
        target_leaf = self._leaf_of(target)
        leaf = _PaneLeaf(child)
        parent = target_leaf.parent
        if parent is not None and parent.orient == orient:
            index = parent.children.index(target_leaf)
            share = parent.fractions[index]
            parent.fractions[index] = share * (1 - ratio)
            position = index if before else index + 1
            parent.children.insert(position, leaf)
            parent.fractions.insert(position, share * ratio)
            leaf.parent = parent
            self._ensure_sashes(parent)
        else:
            node = _PaneSplit(self, orient)
            self._replace(target_leaf, node)
            target_leaf.parent = node
            leaf.parent = node
            if before:
                node.children = [leaf, target_leaf]
                node.fractions = [ratio, 1 - ratio]
            else:
                node.children = [target_leaf, leaf]
                node.fractions = [1 - ratio, ratio]
            self._ensure_sashes(node)
        self._layout()

    def remove(self, pane):
        """Remove a pane (its widget is kept, just no longer shown); the
        space goes to its neighbors, and a split left with one pane
        disappears."""
        leaf = self._leaf_of(pane)
        leaf.child.place_forget()
        parent = leaf.parent
        if parent is None:
            self._pane_tree = None
        else:
            index = parent.children.index(leaf)
            parent.children.pop(index)
            parent.fractions.pop(index)
            total = sum(parent.fractions) or 1
            parent.fractions = [f / total for f in parent.fractions]
            self._ensure_sashes(parent)
            if len(parent.children) == 1:
                only = parent.children[0]
                self._replace(parent, only)
                for sash in parent.sashes:
                    sash.destroy()
        self._layout()

    forget = remove

    # ---- layout ----------------------------------------------------------------
    def _layout(self):
        """Place the whole tree to fill the widget (called on resize and after every
        change).
        """
        if self._pane_tree is None:
            self._junctions = []
            return
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1 or height <= 1:
            return
        self._layout_node(self._pane_tree, 0, 0, width, height)
        self._junctions = self._find_junctions()

    def _split_sizes(self, split, length):
        """Pixel sizes of the children of split along a length."""
        count = len(split.children)
        available = max(length - _Sash.THICKNESS * (count - 1), count)
        sizes = [round(f * available) for f in split.fractions]
        # Give the rounding remainder to the last child so the sizes add up exactly.
        sizes[-1] = available - sum(sizes[:-1])
        return sizes

    def _layout_node(self, node, x, y, width, height):
        """Place a node in the given rectangle: a leaf is placed, a split divides the
        rectangle among its children and puts sashes between them.
        """
        if isinstance(node, _PaneLeaf):
            node.child.place(x=x, y=y, width=width, height=height)
            return
        node.rect = (x, y, width, height)
        horizontal = node.orient == "horizontal"
        sizes = self._split_sizes(node, width if horizontal else height)
        position = 0
        for index, (child, size) in enumerate(zip(node.children, sizes)):
            if horizontal:
                self._layout_node(child, x + position, y, size, height)
            else:
                self._layout_node(child, x, y + position, width, size)
            position += size
            if index < len(node.sashes):
                sash = node.sashes[index]
                sash.index = index
                if horizontal:
                    sash.place(
                        x=x + position, y=y, width=_Sash.THICKNESS, height=height
                    )
                else:
                    sash.place(x=x, y=y + position, width=width, height=_Sash.THICKNESS)
                position += _Sash.THICKNESS

    def _drag_sash(self, split, index, root_position, relayout=True):
        """Move a split's sash to the pointer, keeping both neighbors at least the
        minimum size, and relayout (unless the caller moves more sashes first).
        """
        horizontal = split.orient == "horizontal"
        x, y, width, height = split.rect
        origin = (self.winfo_rootx() + x) if horizontal else (self.winfo_rooty() + y)
        length = width if horizontal else height
        sizes = self._split_sizes(split, length)
        available = sum(sizes)
        start = sum(sizes[:index]) + index * _Sash.THICKNESS
        boundary = root_position - origin - _Sash.THICKNESS / 2
        pair = sizes[index] + sizes[index + 1]
        minimum = self.MINIMUM_PANE_SIZE
        new_size = min(max(boundary - start, minimum), max(pair - minimum, minimum))
        split.fractions[index] = new_size / available
        split.fractions[index + 1] = (pair - new_size) / available
        if relayout:
            self._layout()

    # ---- junctions: where a sash meets a perpendicular sash ----------------------
    def _sash_centers(self, split):
        """The position of each sash's center line of a split, along the split's
        axis, in this widget's coordinates.
        """
        horizontal = split.orient == "horizontal"
        x, y, width, height = split.rect
        sizes = self._split_sizes(split, width if horizontal else height)
        position = x if horizontal else y
        centers = []
        for size in sizes[:-1]:
            position += size
            centers.append(position + _Sash.THICKNESS / 2)
            position += _Sash.THICKNESS
        return centers

    def _find_junctions(self):
        """All the places where a sash of one split meets sashes of a split of
        the other direction that is next to it (a T-junction).

        Each junction is a dict: `split` and `index` (the sash that the others
        end on), `partners` (the (split, index) pairs of the perpendicular
        sashes ending there on either side, merged if they line up), and
        `point` (x, y) where they meet.
        """
        junctions = []
        for split in self._splits():
            horizontal = split.orient == "horizontal"
            for index, along in enumerate(self._sash_centers(split)):
                # Perpendicular sashes ending on this one, grouped by where.
                groups = []
                for neighbor in (split.children[index], split.children[index + 1]):
                    if (
                        not isinstance(neighbor, _PaneSplit)
                        or neighbor.orient == split.orient
                    ):
                        continue
                    for partner_index, across in enumerate(
                        self._sash_centers(neighbor)
                    ):
                        for group in groups:
                            if abs(group["across"] - across) <= 2:
                                group["partners"].append((neighbor, partner_index))
                                break
                        else:
                            groups.append(
                                {
                                    "across": across,
                                    "partners": [(neighbor, partner_index)],
                                }
                            )
                for group in groups:
                    point = (
                        (along, group["across"])
                        if horizontal
                        else (group["across"], along)
                    )
                    junctions.append(
                        {
                            "split": split,
                            "index": index,
                            "partners": group["partners"],
                            "point": point,
                        }
                    )
        return junctions

    def junction_at(self, split, index, event):
        """The junction that sash `index` of `split` takes part in and the pointer
        is close to (within _Sash.JUNCTION_REACH px), or None.
        """
        pointer_x = event.x_root - self.winfo_rootx()
        pointer_y = event.y_root - self.winfo_rooty()
        for junction in self._junctions:
            takes_part = (
                junction["split"] is split and junction["index"] == index
            ) or any(
                partner is split and partner_index == index
                for partner, partner_index in junction["partners"]
            )
            if not takes_part:
                continue
            point_x, point_y = junction["point"]
            if (
                abs(pointer_x - point_x) <= _Sash.JUNCTION_REACH
                and abs(pointer_y - point_y) <= _Sash.JUNCTION_REACH
            ):
                return junction
        return None

    def drag_junction(self, junction, root_x, root_y):
        """Move the sash a junction is on and every sash that ends there, at once:
        the first along its axis and the others along theirs, to the pointer.
        """
        split = junction["split"]
        along, across = (
            (root_x, root_y) if split.orient == "horizontal" else (root_y, root_x)
        )
        self._drag_sash(split, junction["index"], along, relayout=False)
        for partner, partner_index in junction["partners"]:
            self._drag_sash(partner, partner_index, across, relayout=False)
        self._layout()

    def _junction_sashes(self, junction):
        """The sash widgets that make up a junction."""
        if junction is None:
            return []
        wanted = [(junction["split"], junction["index"])] + junction["partners"]
        # A junction kept from before panes were removed may point at a sash
        # that no longer exists; skip those.
        return [
            split.sashes[index] for split, index in wanted if index < len(split.sashes)
        ]

    def set_hot(self, junction):
        """Highlight the sashes of a junction (the pointer is near it); None
        removes the highlight.
        """

        def key(value):
            """What identifies a junction: its main sash (junction dicts are rebuilt
            on every layout, so they cannot be compared directly).
            """
            return None if value is None else (id(value["split"]), value["index"])

        if key(junction) == key(self._hot_junction):
            return
        previous, self._hot_junction = self._hot_junction, junction
        for sash in self._junction_sashes(previous) + self._junction_sashes(junction):
            sash.schedule_redraw()

    def is_hot(self, split, index):
        """Whether sash `index` of `split` is part of the highlighted junction."""
        hot = self._hot_junction
        if hot is None:
            return False
        if hot["split"] is split and hot["index"] == index:
            return True
        return any(
            partner is split and partner_index == index
            for partner, partner_index in hot["partners"]
        )
