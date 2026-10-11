"""Containers: Frame, ScrolledFrame, Foldable, Notebook, Panedwindow, and GridPanedwindow.

They are tk.Frame subclasses (not canvases): they hold other widgets. Frames
follow the theme's background; the notebook draws its tabs, the panedwindows
their sashes, and the scrolled frame its scroll bars, on canvases.
"""

import tkinter as tk

from ._core import (
    pop_color_parts,
    check_appearance_mode,
    cross_image,
    expand_theme,
    get_appearance_mode,
    layered_theme,
    starting_theme,
    window_appearance_mode,
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
from .popups import Tooltip
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

    _appearance_mode = None  # 'light' / 'dark' for this container alone, else follows

    def child_background_color(self):
        """A fixed color this container gives its children (or None)."""
        return self._explicit_background

    def _init_background(self, master, background, role, theme=None):
        """Work out this container's background role/color from its master (or an
        explicit bg), and keep its own theme overrides.
        """
        self._theme_overrides = starting_theme(theme)
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
        colors = layered_theme(widget, self._appearance_mode, self._theme_overrides)
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
        return layered_theme(self, self._appearance_mode, self._theme_overrides)

    def set_appearance_mode(self, mode):
        """'light' or 'dark' for this container's own background; None follows its
        window (or the global mode).
        """
        self._appearance_mode = check_appearance_mode(mode)
        self._appearance_changed()

    def get_appearance_mode(self):
        """The appearance mode this container uses, 'light' or 'dark'."""
        return (
            self._appearance_mode
            or window_appearance_mode(self)
            or get_appearance_mode()
        )

    def _appearance_changed(self):
        """The appearance mode of this container changed: recolor it."""
        self.refresh_theme()

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


# The scrolled areas of each window (the scrolled frames, foldables, and labeled frames
# in it), and the one wheel binding per window that serves all of them.
_WHEEL_SCROLLERS = {}
_WHEEL_BINDINGS = {}


def _add_wheel_scroller(top, scroller):
    """Let the mouse wheel scroll `scroller` (in the window `top`)."""
    _WHEEL_SCROLLERS.setdefault(top, []).append(scroller)
    if top not in _WHEEL_BINDINGS:
        # Bound on the whole window (not on the scrolled frame) so scrolling works over
        # any child; _dispatch_wheel checks where the pointer is.
        _WHEEL_BINDINGS[top] = [
            (
                sequence,
                top.bind(sequence, lambda e, t=top: _dispatch_wheel(t, e), add="+"),
            )
            for sequence in _WHEEL_SEQUENCES
        ]


def _remove_wheel_scroller(top, scroller):
    """Stop the wheel scrolling `scroller`; the last one of a window takes the window's
    binding away.
    """
    scrollers = _WHEEL_SCROLLERS.get(top, [])
    if scroller in scrollers:
        scrollers.remove(scroller)
    if scrollers:
        return
    _WHEEL_SCROLLERS.pop(top, None)
    for sequence, funcid in _WHEEL_BINDINGS.pop(top, []):
        try:
            top.unbind(sequence, funcid)
        except tk.TclError:
            pass


def _dispatch_wheel(top, event):
    """A wheel turn anywhere in the window `top`: scroll the innermost scrolled area
    under the pointer; if that one is already at its end (or does not scroll that
    way), the one around it, and so on.

    Widgets that scroll themselves (Text, Listbox, anything with handles_wheel) keep
    their own wheel behavior.
    """
    try:
        widget = top.winfo_containing(event.x_root, event.y_root)
    except (KeyError, tk.TclError):
        return None
    areas = {id(s._scroll_area): s for s in _WHEEL_SCROLLERS.get(top, [])}
    direction = wheel_direction(event) * 3
    shift_held = bool(event.state & 0x1)
    while widget is not None:
        scroller = areas.get(id(widget))
        if scroller is not None and scroller._scroll_by_wheel(direction, shift_held):
            return "break"
        if getattr(widget, "handles_wheel", False) or widget.winfo_class() in (
            "Text",
            "Listbox",
        ):
            return None
        widget = widget.master
    return None


class _ScrolledContent:
    """The scrolling shared by ScrolledFrame and a scrolled Foldable: a viewport canvas
    (with scroll bars) inside a container, showing the content frame through a canvas
    window. The class using it is the content frame.
    """

    _SCROLLBAR_COLOR_OPTIONS = {
        "scrollbar_track_color": "track_color",
        "scrollbar_thumb_color": "thumb_color",
        "scrollbar_thumb_hover_color": "thumb_hover_color",
    }

    @classmethod
    def _pop_scrollbar_theme(cls, kwargs, theme):
        """Take the scrollbar_*_color options out of kwargs; with `theme`, the theme the
        scroll bars get.
        """
        scrollbar_theme = {
            own_name: kwargs.pop(name)
            for name, own_name in cls._SCROLLBAR_COLOR_OPTIONS.items()
            if name in kwargs
        }
        return {**(theme or {}), **scrollbar_theme}

    @staticmethod
    def _check_orient(orient):
        """Raise ValueError unless `orient` is a direction a frame can scroll in."""
        if orient not in ("vertical", "horizontal", "both"):
            raise ValueError("orient must be 'vertical', 'horizontal' or 'both'")

    def _build_viewport(
        self,
        area,
        orient,
        autohide,
        scrollbar_theme,
        background,
        max_size=None,
        scrollbar_width=None,
    ):
        """Create the viewport and the scroll bars in the container `area`. With
        `max_size` (width, height), the viewport asks for the size of the contents up
        to that many px along the axes that scroll (more scrolls); without it, it
        keeps the canvas's own size. scrollbar_width: the width of the scroll bars in
        px (None = the Scrollbar's default).
        """
        width_option = {} if scrollbar_width is None else {"thickness": scrollbar_width}
        self._scroll_area = area
        self._max_viewport_size = max_size
        self._scrolls_vertically = orient in ("vertical", "both")
        self._scrolls_horizontally = orient in ("horizontal", "both")
        self.viewport = tk.Canvas(area, bd=0, highlightthickness=0, bg=background)
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar = self.horizontal_scrollbar = None
        if self._scrolls_vertically:
            self.vertical_scrollbar = Scrollbar(
                area,
                orient="vertical",
                command=self.viewport.yview,
                autohide=autohide,
                theme=scrollbar_theme,
                **width_option,
            )
            self.vertical_scrollbar.grid(row=0, column=1, sticky="ns", padx=(2, 0))
            self.viewport.configure(yscrollcommand=self.vertical_scrollbar.set)
        if self._scrolls_horizontally:
            self.horizontal_scrollbar = Scrollbar(
                area,
                orient="horizontal",
                command=self.viewport.xview,
                autohide=autohide,
                theme=scrollbar_theme,
                **width_option,
            )
            self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            self.viewport.configure(xscrollcommand=self.horizontal_scrollbar.set)
        self.scrollbar = self.vertical_scrollbar or self.horizontal_scrollbar

    def _attach_content(self):
        """Show this frame in the viewport and start following sizes and the wheel
        (call after the frame is created, as a child of the viewport).
        """
        self._window = self.viewport.create_window(0, 0, window=self, anchor="nw")
        tk.Frame.bind(self, "<Configure>", lambda _: self._fit_content(), add="+")
        self.viewport.bind("<Configure>", lambda _: self._fit_content(), add="+")
        self._top = self.winfo_toplevel()
        _add_wheel_scroller(self._top, self)

    def _refresh_viewport(self):
        """The theme changed: recolor the viewport like the content frame."""
        if self.background_role:
            self.viewport.configure(bg=self.themed_color(self, self.background_role))

    def _fit_content(self):
        """Size the content window: it fills the viewport along axes that do
        not scroll and is at least its natural size along axes that do.
        """
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
        if self._max_viewport_size is not None:
            max_width, max_height = self._max_viewport_size
            self.viewport.configure(
                width=(
                    min(self.winfo_reqwidth(), max_width)
                    if self._scrolls_horizontally
                    else self.winfo_reqwidth()
                ),
                height=(
                    min(self.winfo_reqheight(), max_height)
                    if self._scrolls_vertically
                    else self.winfo_reqheight()
                ),
            )

    def _scroll_by_wheel(self, direction, shift_held):
        """Scroll `direction` units (positive is down or right) for a wheel turn, if
        that is possible: False when the contents do not scroll that way or are
        already at that end.
        """
        horizontal = self._scrolls_horizontally and (
            shift_held or not self._scrolls_vertically
        )
        if horizontal:
            view, scroll = self.viewport.xview, self.viewport.xview_scroll
        elif self._scrolls_vertically:
            view, scroll = self.viewport.yview, self.viewport.yview_scroll
        else:
            return False
        first, last = view()
        if (direction > 0 and last >= 1.0 - 1e-9) or (direction < 0 and first <= 1e-9):
            return False
        scroll(direction, "units")
        return True

    def _remove_wheel_bindings(self):
        """Stop listening to the wheel of the window."""
        _remove_wheel_scroller(self._top, self)


class _FrameOptions:
    """configure() / cget() for a frame-like container that has options of its own
    (listed in _FRAME_OPTIONS, each an attribute or property); the rest are tk.Frame's.
    """

    _FRAME_OPTIONS = ()

    def configure(self, cnf=None, **kw):
        """tkinter configure(): sets the container's own options, passes the rest on."""
        if isinstance(cnf, dict):
            kw, cnf = {**cnf, **kw}, None
        own = {name: kw.pop(name) for name in list(kw) if name in self._FRAME_OPTIONS}
        for name, value in own.items():
            setattr(self, name, value)
        if own and not kw and cnf is None:
            return None
        return tk.Frame.configure(self, cnf, **kw)

    config = configure

    def cget(self, key):
        """tkinter cget(): the container's own options come from the attributes."""
        if key in self._FRAME_OPTIONS:
            return getattr(self, key)
        return tk.Frame.cget(self, key)


class ScrolledFrame(_ScrolledContent, _ThemedBackground, tk.Frame):
    """A scrolling frame: add children to the ScrolledFrame itself; pack/grid/
    place act on the whole scrolling container.

    orient: 'vertical' (default), 'horizontal' or 'both'. The mouse wheel
    scrolls vertically (horizontally for orient='horizontal'); Shift+wheel
    always scrolls horizontally."""

    def __init__(
        self,
        master,
        orient="vertical",
        autohide=True,
        scrollbar_width=None,
        theme=None,
        **kwargs,
    ):
        """Create the scrolled frame.

        orient: which directions scroll. autohide: scroll bars hide when not needed.
        scrollbar_width: the width of the scroll bars in px.
        theme / bg / scrollbar_*_color: styling. The returned object is the *content*
        frame; its geometry methods are redirected to the outer container.
        """
        self._check_orient(orient)
        self.orient = orient
        scrollbar_theme = self._pop_scrollbar_theme(kwargs, theme)
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self._init_background(
            master, background, kwargs.pop("background_role", None), theme
        )
        # Structure: outer frame > viewport canvas (+ scroll bars) > this content frame,
        # shown through a canvas window.
        self.outer = Frame(
            master, background_role=self.background_role, bg=background, theme=theme
        )
        self._build_viewport(
            self.outer,
            orient,
            autohide,
            scrollbar_theme,
            self.initial_background(master, background),
            scrollbar_width=scrollbar_width,
        )
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(
            self,
            self.viewport,
            bg=self.initial_background(master, background),
            **kwargs,
        )
        _CANVAS_THEMED_WIDGETS.add(self)
        self._destroying = False
        for name in _GEOMETRY_METHOD_NAMES:
            setattr(self, name, getattr(self.outer, name))
        self._attach_content()

    def refresh_theme(self):
        """The theme changed: recolor the content frame and the viewport."""
        self.apply_background()
        self._refresh_viewport()

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
        self._remove_wheel_bindings()
        self.outer.destroy()


class _FoldableHeader(CanvasWidget):
    """The clickable header bar of a Foldable: an arrow and the title."""

    _COLOR_PARTS = (
        "fill_color",
        "hover_color",
        "text_color",
        "arrow_color",
        "focus_color",
        "disabled_text_color",
    )
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + ("text",)
    DEFAULT_FONT_WEIGHT = "bold"
    VERTICAL_PADDING = 8

    def __init__(self, master, foldable, text, theme=None, **kwargs):
        """`foldable` is the Foldable the bar belongs to (it says whether it is open and
        is told when the bar is clicked).
        """
        takefocus = kwargs.get("state", "normal") != "disabled"
        super().__init__(master, theme=theme, takefocus=takefocus, **kwargs)
        self.foldable = foldable
        self.text = text
        self._pressed = False
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<space>", lambda _: self._toggle_foldable(), add="+")
        self.bind("<Return>", lambda _: self._toggle_foldable(), add="+")
        self.refit()
        self.schedule_redraw()

    def requested_size(self):
        """Tall enough for the title, as wide as the title and the arrow."""
        width, height = measure_content(self.text, None, self.font)
        return width + 44, height + 2 * self.VERTICAL_PADDING

    def _toggle_foldable(self):
        """Fold or unfold, unless the bar is disabled."""
        if not self.is_disabled():
            self.foldable.toggle()

    def _on_press(self, _):
        """Mouse down: a release inside the bar will fold or unfold."""
        if self.is_disabled():
            return
        self._pressed = True
        self.focus_set()

    def _on_release(self, event):
        """Mouse up inside the bar: fold or unfold the contents."""
        was_pressed, self._pressed = self._pressed, False
        if (
            was_pressed
            and 0 <= event.x < self.winfo_width()
            and 0 <= event.y < self.winfo_height()
        ):
            self._toggle_foldable()

    def redraw(self, width, height):
        """Draw the bar, the arrow (down while open, right while folded), and the title
        (in the disabled color while disabled).
        """
        disabled = self.is_disabled()
        fill = (
            self.part("hover_color", "neutral_hover")
            if self._hovered and not disabled
            else None
        )
        fill = fill or self.part("fill_color", "neutral")
        outline = (
            self.part("focus_color", "focus_ring")
            if self._focused and not disabled
            else None
        )
        disabled_color = self.part("disabled_text_color", "text_disabled")
        self.draw_box(
            0,
            0,
            width,
            height,
            fill,
            outline,
            2 if outline else 0,
            self.colors["radius"],
        )
        direction = "down" if self.foldable.is_expanded() else "right"
        self.draw_chevron(
            19,
            height / 2,
            direction,
            disabled_color if disabled else self.part("arrow_color", "text_muted"),
            4,
            2,
        )
        self.create_text(
            34,
            height / 2,
            text=self.text,
            font=self.font,
            fill=disabled_color if disabled else self.part("text_color", "text"),
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )


class Foldable(_ScrolledContent, _FrameOptions, _ThemedBackground, tk.Frame):
    """A frame that can be folded away: a header bar with an arrow and a title, and the
    contents under it.

    Add the children to the Foldable itself, exactly as to a Frame; pack / grid / place
    act on the whole thing (header and contents together), and it takes one place in
    its parent whether it is open or folded. The header and the contents live in a
    container of their own, so folding only changes the size of the Foldable and never
    puts anything into the parent or moves the parent's other widgets around except
    for the space the Foldable itself takes. Click the header, or press Space or Return
    on it, to fold or unfold; expand(), collapse(), and toggle() do it from code.

    With scrolled=True the contents scroll (in the direction orient: "vertical",
    "horizontal", or "both") when they are bigger than max_height / max_width; the
    children are still added to the Foldable itself. state="disabled" greys out the
    header and stops clicks and keys from folding it (expand() and collapse() from code
    still work); the children are not affected.
    """

    _HEADER_COLOR_PARTS = _FoldableHeader._COLOR_PARTS
    _FRAME_OPTIONS = ("text", "state")

    def __init__(
        self,
        master,
        text="",
        expanded=True,
        command=None,
        padding=8,
        scrolled=False,
        orient="vertical",
        max_height=300,
        max_width=300,
        scrollbar_width=None,
        state="normal",
        theme=None,
        **kwargs,
    ):
        """Create the foldable.

        text: the title. expanded: whether the contents start open. command(expanded):
        called after every fold or unfold. padding: the space in px around the
        contents. scrolled: scroll the contents (with a scroll bar that shows when
        needed) instead of growing with them; orient: which directions scroll;
        max_height / max_width: the size in px the open contents take at most along
        the directions that scroll; scrollbar_width: the scroll bars' width in px.
        state: "normal" or "disabled" (the header).
        The header takes the color options fill_color, hover_color, text_color,
        arrow_color, focus_color, and disabled_text_color; theme / bg /
        scrollbar_*_color style the contents.
        """
        header_theme = {
            **(theme or {}),
            **pop_color_parts(self._HEADER_COLOR_PARTS, kwargs),
        }
        scrollbar_theme = self._pop_scrollbar_theme(kwargs, theme)
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self._init_background(
            master, background, kwargs.pop("background_role", None), theme
        )
        # Structure: outer frame > header bar + this content frame (or, when scrolled,
        # a body holding a viewport that shows it). The outer frame is the one thing
        # the parent sees.
        self.outer = Frame(
            master, background_role=self.background_role, bg=background, theme=theme
        )
        self.outer.grid_columnconfigure(0, weight=1)
        self.outer.grid_rowconfigure(1, weight=1)
        self._check_orient(orient)
        if state not in ("normal", "disabled"):
            raise ValueError("state must be 'normal' or 'disabled'")
        self.header = _FoldableHeader(
            self.outer, self, text, theme=header_theme, state=state
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.scrolled = scrolled
        self._holder = self  # what is shown or hidden when folding
        content_master = self.outer
        if scrolled:
            self._holder = Frame(
                self.outer,
                background_role=self.background_role,
                bg=background,
                theme=theme,
            )
            self._build_viewport(
                self._holder,
                orient,
                True,
                scrollbar_theme,
                self.initial_background(master, background),
                (max_width, max_height),
                scrollbar_width,
            )
            content_master = self.viewport
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(
            self,
            content_master,
            bg=self.initial_background(master, background),
            **kwargs,
        )
        _CANVAS_THEMED_WIDGETS.add(self)
        if scrolled:
            self._attach_content()
        self.padding = padding
        self.command = command
        self._expanded = False
        self._destroying = False
        for name in _GEOMETRY_METHOD_NAMES:
            setattr(self, name, getattr(self.outer, name))
        if expanded:
            self.expand(notify=False)

    def refresh_theme(self):
        """The theme changed: re-apply the background."""
        self.apply_background()
        if self.scrolled:
            self._refresh_viewport()

    @property
    def state(self):
        """'normal' or 'disabled' (the header)."""
        return self.header.state

    @state.setter
    def state(self, new_state):
        """Enable or disable the header."""
        if new_state not in ("normal", "disabled"):
            raise ValueError("state must be 'normal' or 'disabled'")
        self.header.configure(state=new_state, takefocus=new_state != "disabled")

    @property
    def text(self):
        """The title in the header."""
        return self.header.text

    @text.setter
    def text(self, new_text):
        """Change the title."""
        self.header.text = new_text
        self.header.refit()
        self.header.schedule_redraw()

    def is_expanded(self):
        """Whether the contents are showing."""
        return self._expanded

    def expand(self, notify=True):
        """Show the contents."""
        self._set_expanded(True, notify)

    def collapse(self, notify=True):
        """Fold the contents away."""
        self._set_expanded(False, notify)

    def toggle(self):
        """Fold if open, unfold if folded."""
        self._set_expanded(not self._expanded, True)

    def _set_expanded(self, expanded, notify):
        """Show or hide the contents inside the container (nothing outside it changes),
        redraw the header, and tell the command and the <<FoldableToggled>> event.
        """
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if expanded:
            pad = self.padding
            tk.Frame.grid(
                self._holder,
                row=1,
                column=0,
                sticky="nsew",
                padx=pad,
                pady=(pad, pad),
            )
        else:
            tk.Frame.grid_remove(self._holder)
        self.header.schedule_redraw()
        if notify:
            self.event_generate("<<FoldableToggled>>")
            if self.command is not None:
                self.command(expanded)

    def destroy(self):
        """Destroy the whole container (the header and the contents with it)."""
        if self._destroying:
            # Re-entered while the outer container is being torn down: destroy
            # normally so this frame's children are destroyed too.
            tk.Frame.destroy(self)
            return
        self._destroying = True
        if self.scrolled:
            self._remove_wheel_bindings()
        self.outer.destroy()


class _LabelFrameBorder(CanvasWidget):
    """The outline of a LabelFrame, with the title set into its top edge."""

    _COLOR_PARTS = ("border_color", "text_color")
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "text",
        "radius",
        "border_width",
    )
    TITLE_INDENT = 12  # px from the left edge to the title
    TITLE_GAP = 5  # px of room around the title where the line is cut

    def __init__(self, master, text, radius, border_width, theme=None, **kwargs):
        super().__init__(master, theme=theme, **kwargs)
        self.text = text
        self.radius = radius
        self.border_width = border_width
        self.refit()
        self.schedule_redraw()

    def title_height(self):
        """The height of the title's line in px."""
        return self.font.metrics("linespace")

    def requested_size(self):
        """Wide enough for the title."""
        width, _ = measure_content(self.text, None, self.font)
        return (
            (width + 2 * (self.TITLE_INDENT + self.TITLE_GAP) if self.text else 1),
            1,
        )

    def redraw(self, width, height):
        """Draw the outline (starting at the middle of the title's line), cut the line
        where the title is, and write the title.
        """
        top = self.title_height() / 2
        self.draw_box(
            0,
            top,
            width,
            height,
            None,
            self.part("border_color", "border"),
            self.border_width,
            self.corner(self.radius, "radius"),
        )
        if not self.text:
            return
        text_width, _ = measure_content(self.text, None, self.font)
        left = self.TITLE_INDENT
        self.create_rectangle(
            left - self.TITLE_GAP,
            0,
            left + text_width + self.TITLE_GAP,
            self.title_height(),
            fill=self._applied_background,
            width=0,
            tags=_CANVAS_CHROME_TAG,
        )
        self.create_text(
            left,
            top,
            text=self.text,
            font=self.font,
            fill=self.part("text_color", "text"),
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )


class LabelFrame(_ScrolledContent, _FrameOptions, _ThemedBackground, tk.Frame):
    """A frame with an outline and a title set into the outline's top edge.

    Add the children to the LabelFrame itself, exactly as to a Frame; pack / grid /
    place act on the whole thing (outline and contents together). With scrolled=True
    the contents scroll (in the direction orient: "vertical", "horizontal", or
    "both") when they are bigger than max_height / max_width.
    """

    _BORDER_COLOR_PARTS = _LabelFrameBorder._COLOR_PARTS
    _FRAME_OPTIONS = ("text",)

    def __init__(
        self,
        master,
        text="",
        padding=8,
        radius=None,
        border_width=1,
        scrolled=False,
        orient="vertical",
        max_height=300,
        max_width=300,
        scrollbar_width=None,
        theme=None,
        **kwargs,
    ):
        """Create the labeled frame.

        text: the title. padding: the space in px between the outline and the contents.
        radius / border_width: the shape of the outline. scrolled: scroll the contents
        (with scroll bars that show when needed) instead of growing with them; orient:
        which directions scroll; max_height / max_width: the size in px the contents
        take at most along the directions that scroll; scrollbar_width: the scroll
        bars' width in px. border_color and text_color
        style the outline and the title; theme / bg / scrollbar_*_color style the
        contents.
        """
        self._check_orient(orient)
        scrollbar_theme = self._pop_scrollbar_theme(kwargs, theme)
        border_theme = {
            **(theme or {}),
            **pop_color_parts(self._BORDER_COLOR_PARTS, kwargs),
        }
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self._init_background(
            master, background, kwargs.pop("background_role", None), theme
        )
        # Structure: outer frame > outline canvas, with this content frame on top of it
        # in the same cell. The outer frame is the one thing the parent sees.
        self.outer = Frame(
            master, background_role=self.background_role, bg=background, theme=theme
        )
        self.outer.grid_columnconfigure(0, weight=1)
        self.outer.grid_rowconfigure(0, weight=1)
        self.border = _LabelFrameBorder(
            self.outer, text, radius, border_width, theme=border_theme
        )
        self.border.grid(row=0, column=0, sticky="nsew")
        self.scrolled = scrolled
        self._holder = self  # what is placed inside the outline
        content_master = self.outer
        if scrolled:
            self._holder = Frame(
                self.outer,
                background_role=self.background_role,
                bg=background,
                theme=theme,
            )
            self._build_viewport(
                self._holder,
                orient,
                True,
                scrollbar_theme,
                self.initial_background(master, background),
                (max_width, max_height),
                scrollbar_width,
            )
            content_master = self.viewport
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        tk.Frame.__init__(
            self,
            content_master,
            bg=self.initial_background(master, background),
            **kwargs,
        )
        _CANVAS_THEMED_WIDGETS.add(self)
        if scrolled:
            self._attach_content()
        self.padding = padding
        self._destroying = False
        for name in _GEOMETRY_METHOD_NAMES:
            setattr(self, name, getattr(self.outer, name))
        self._place_contents()

    def _place_contents(self):
        """Put the contents inside the outline, below the title."""
        inset = self.padding + self.border.border_width
        top = self.border.title_height() + self.padding // 2 if self.text else inset
        tk.Frame.grid(
            self._holder, row=0, column=0, sticky="nsew", padx=inset, pady=(top, inset)
        )

    def refresh_theme(self):
        """The theme changed: re-apply the background."""
        self.apply_background()
        if self.scrolled:
            self._refresh_viewport()

    @property
    def text(self):
        """The title."""
        return self.border.text

    @text.setter
    def text(self, new_text):
        """Change the title."""
        self.border.configure(text=new_text)
        self._place_contents()

    def destroy(self):
        """Destroy the whole container (the outline and the contents with it)."""
        if self._destroying:
            # Re-entered while the outer container is being torn down: destroy
            # normally so this frame's children are destroyed too.
            tk.Frame.destroy(self)
            return
        self._destroying = True
        if self.scrolled:
            self._remove_wheel_bindings()
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


class _TabTooltip(Tooltip):
    """The tooltip of the tabs of a Notebook: the notebook decides when to show it (for
    the tab under the pointer), not the pointer entering the strip.
    """

    def __init__(self, widget):
        """Attach it to the notebook's strip."""
        super().__init__(widget, "")

    def _schedule(self, event):
        """The pointer entered the strip: wait for the notebook to say which tab."""

    def show_for(self, text, event):
        """Show `text` after the delay, next to the pointer."""
        self.text = text
        Tooltip._schedule(self, event)


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
        radius=None,
        padding=8,
        tab_padx=16,
        closable=False,
        on_close=None,
        destroy_on_close=True,
        style="segmented",
        segment_radius=None,
        draggable=False,
        **kwargs,
    ):
        """closable: whether tabs show a close button by default (each tab
        can override with its own closable=True/False). on_close(child) is
        called before a tab closes and can return False to keep it;
        destroy_on_close destroys the page widget when its tab is closed.
        style: 'segmented' (the default: a rounded segmented control above a
        rounded page, like macOS / customtkinter) or 'classic' (folder-like tabs).
        radius / segment_radius: the corner radius of the page and of the segmented
        style's tabs (None = the theme's radius and tab_radius; a big number such as
        99 makes the tabs fully rounded pills; the pill behind them follows it).
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
        self._tab_tooltip = _TabTooltip(self.chrome)
        self._tooltip_tab = None  # the page of the tab the tooltip is for
        self.chrome.bind("<ButtonPress-1>", self._on_press, add="+")
        self.chrome.bind("<ButtonPress-2>", self._on_middle_press, add="+")
        self.chrome.bind("<B1-Motion>", self._on_tab_drag, add="+")
        self.chrome.bind("<ButtonRelease-1>", self._on_tab_drop, add="+")
        self.chrome.bind("<Motion>", self._on_motion, add="+")
        self.chrome.bind("<Leave>", self._on_leave, add="+")
        for sequence in _WHEEL_SEQUENCES:
            self.chrome.bind(
                sequence, lambda e: self._scroll_tabs(wheel_direction(e) * 60), add="+"
            )
        tk.Frame.bind(self, "<Left>", lambda _: self._select_neighbor(-1), add="+")
        tk.Frame.bind(self, "<Right>", lambda _: self._select_neighbor(1), add="+")
        tk.Frame.bind(self, "<Configure>", lambda _: self._place_selected(), add="+")
        # Measure the pages again once the notebook is shown (they may have been filled
        # after the first measurement).
        tk.Frame.bind(self, "<Map>", lambda _: self._tab_changed(), add="+")

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
        """Append a page as a new tab (options: text, state, image, closable, tooltip)."""
        self.insert("end", child, **options)

    def insert(
        self,
        where,
        child,
        text="",
        state="normal",
        image=None,
        closable=None,
        tooltip=None,
    ):
        """Insert a page as a tab before `where` ('end' appends); the first tab added is
        selected. tooltip: a text shown while the pointer rests on the tab.
        """
        record = {
            "child": child,
            "text": text,
            "state": state,
            "image": image,
            "closable": closable,
            "tooltip": tooltip,
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
        """Read (option) or change (options) a tab's text, state, image, closable, or
        tooltip.
        """
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
        # Let Tk lay out the pages' own widgets first: this runs as soon as the program
        # is idle, which can be before the pages ask for their real size.
        self.update_idletasks()
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

    def _on_leave(self, _):
        """Pointer left the strip: nothing is hovered any more."""
        self._set_hover(None, None)
        self._tooltip_tab = None

    def _on_motion(self, event):
        """Pointer moved over the strip: update the hover state and the tab's tooltip."""
        tab = self._tab_at(event.x, event.y)
        close = self._close_at(event.x, event.y)
        arrow = self._arrow_at(event.x, event.y)
        self._set_hover(tab, close, arrow)
        self._update_tab_tooltip(
            tab if close is None and arrow is None else None, event
        )

    def _update_tab_tooltip(self, index, event):
        """The pointer is over tab `index` (None = no tab): when that is another tab than
        before, hide the tooltip and, if the new tab has one, show it after a delay.
        """
        child = None if index is None else self._tab_records[index]["child"]
        if child is self._tooltip_tab:
            return
        self._tooltip_tab = child
        self._tab_tooltip.hide()
        text = None if index is None else self._tab_records[index].get("tooltip")
        if text:
            self._tab_tooltip.show_for(text, event)

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
                    radius=self.colors["small_radius"],
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
            self.corner(self.radius, "radius"),
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
            radius=self.corner(self.segment_radius, "tab_radius") + 3,
        )
        # Segments are 3 px inside the pill on every side.
        segment_height = tab_height - 6
        segment_radius = self.corner(self.segment_radius, "tab_radius")
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
        radius = self.corner(self.radius, "radius")
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
    """The draggable divider between two panes of a Panedwindow/GridPanedwindow: a line
    with a three-dot grip.
    """

    # Sash thickness in px.
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


class _PaneMeasuring:
    """The sizing shared by Panedwindow and GridPanedwindow. The panes are placed, so
    Tk does not count them in the widget's own requested size, and the size a pane asks
    for is only right once Tk has laid its widgets out (which happens when the program
    is idle, after the pane was added). So the panes are measured again when idle and
    when the widget is first shown, and the widget asks for the size its panes need
    (unless it was given a width or height).
    """

    def _init_measuring(self, options):
        """Set up the measuring; `options` are the options the frame was created with."""
        self._fixed_size = "width" in options or "height" in options
        self._measure_id = None
        self._measured_on_map = False
        tk.Frame.bind(self, "<Map>", lambda _: self._on_map(), add="+")

    def _schedule_measure(self):
        """Measure the panes once the program is idle."""
        if self._measure_id is None:
            self._measure_id = self.call_later(None, self._measure)

    def _on_map(self):
        """The first time the widget is shown: measure the panes again."""
        if not self._measured_on_map:
            self._measured_on_map = True
            self._schedule_measure()

    def _measure(self):
        """Measure the panes, ask for the size they need, and place them."""
        self._measure_id = None
        # Let Tk lay out the panes' own widgets first: this runs as soon as the program
        # is idle, which can be before the panes ask for their real size.
        self.update_idletasks()
        self._measure_panes()
        size = self._natural_size()
        if size is not None and not self._fixed_size:
            tk.Frame.configure(self, width=size[0], height=size[1])
        self._layout()


class Panedwindow(_PaneMeasuring, _FrameColorParts, _WidgetPlumbing, tk.Frame):
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
        self._user_sized = False  # a sash was moved: the sizes are no longer natural
        self._init_measuring(kwargs)
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
        self._schedule_measure()

    def forget(self, pane):
        """Remove a pane (the widget is kept, not destroyed)."""
        record = self._panes.pop(self._pane_index(pane))
        record["child"].place_forget()
        if self._sashes:
            self._sashes.pop().destroy()
        self._layout()
        self._schedule_measure()

    def _measure_panes(self):
        """Give every pane the size it asks for, unless the sashes were moved."""
        if self._user_sized:
            return
        axis = 0 if self.orient == "horizontal" else 1
        for record in self._panes:
            record["size"] = max(requested_size_of(record["child"])[axis], 1)

    def _natural_size(self):
        """The (width, height) the panes need together, or None without panes."""
        if not self._panes:
            return None
        horizontal = self.orient == "horizontal"
        sashes = _Sash.THICKNESS * (len(self._panes) - 1)
        along = sum(r["size"] for r in self._panes) + sashes
        across = max(
            requested_size_of(r["child"])[1 if horizontal else 0] for r in self._panes
        )
        return (round(along), across) if horizontal else (across, round(along))

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
        self._user_sized = True
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


class GridPanedwindow(_PaneMeasuring, _FrameColorParts, _WidgetPlumbing, tk.Frame):
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
        self._init_measuring(kwargs)
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
        self._schedule_measure()

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
        self._schedule_measure()

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
        self._schedule_measure()

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

    def _measure_panes(self):
        """Nothing to measure: the panes share the space by fractions."""

    def _natural_size(self):
        """The (width, height) the whole layout needs so that every pane gets at least
        the size it asks for, or None without panes.
        """
        if self._pane_tree is None:
            return None
        return self._node_size(self._pane_tree)

    def _node_size(self, node):
        """The (width, height) a node needs: a leaf what its widget asks for, a split
        enough for its biggest child at that child's share of the space.
        """
        if isinstance(node, _PaneLeaf):
            return requested_size_of(node.child)
        horizontal = node.orient == "horizontal"
        sizes = [self._node_size(child) for child in node.children]
        axis, cross = (0, 1) if horizontal else (1, 0)
        along = max(
            size[axis] / max(fraction, 0.01)
            for size, fraction in zip(sizes, node.fractions)
        )
        along += _Sash.THICKNESS * (len(node.children) - 1)
        across = max(size[cross] for size in sizes)
        return (round(along), across) if horizontal else (across, round(along))

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
