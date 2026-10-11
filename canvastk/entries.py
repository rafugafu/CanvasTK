"""Entry, Textbox, Spinbox, and Combobox: canvas chrome around a native editing widget.

Text editing (cursor, selection, clipboard, undo, tags) is far too much to
redraw on a canvas, so each of these is a tk.Frame holding a real tk.Entry or
tk.Text (the "inner" widget) on top of a canvas that draws the rounded border,
the background, and the arrows. The frame forwards everything it does not define
itself to the inner widget, so they work as drop-in replacements.
"""

import re
import tkinter as tk

from ._core import (
    _ChromeCanvas,
    _WidgetPlumbing,
    make_font,
    pop_color_parts,
)
from .sliders import (
    Scrollbar,
)
from .popups import (
    _DropdownOwner,
)

# =============================================================================
# Composite widgets: canvas chrome + an embedded native editing widget
# =============================================================================

# Events bound on the frame itself; every other event is bound on the inner widget.
_FRAME_LEVEL_SEQUENCES = frozenset(
    (
        "<Configure>",
        "<Map>",
        "<Unmap>",
        "<Destroy>",
        "<Enter>",
        "<Leave>",
        "<Visibility>",
    )
)


class _FramedWidget(_WidgetPlumbing, tk.Frame):
    """A tk.Frame whose canvas chrome (rounded border + fill) sits behind an
    embedded native widget (self.inner). Methods the frame does not have are
    forwarded to the inner widget, so get/insert/delete/yview/tag_* etc. work
    on the composite directly."""

    _OWN_OPTIONS = ("radius", "border_width", "focus_border_width", "placeholder")
    _COLOR_PARTS = (
        "placeholder_color",
        "placeholder_fill_color",
        "fill_color",
        "disabled_fill_color",
        "border_color",
        "focus_color",
        "disabled_border_color",
        "text_color",
        "disabled_text_color",
        "cursor_color",
        "selection_color",
        "selection_text_color",
        "arrow_color",
        "disabled_arrow_color",
    )
    # Native tk option names that map onto the color parts above.
    _NATIVE_COLOR_ALIASES = {
        "bg": "fill_color",
        "background": "fill_color",
        "fg": "text_color",
        "foreground": "text_color",
        "insertbackground": "cursor_color",
        "selectbackground": "selection_color",
        "selectforeground": "selection_text_color",
        "disabledbackground": "disabled_fill_color",
        "disabledforeground": "disabled_text_color",
    }

    @classmethod
    def extract_color_options(cls, kwargs):
        """Pop every color option (parts and native tk aliases) from kwargs."""
        for alias, part in cls._NATIVE_COLOR_ALIASES.items():
            if alias in kwargs:
                kwargs[part] = kwargs.pop(alias)
        return pop_color_parts(cls._COLOR_PARTS, kwargs)

    def __init__(
        self,
        master,
        theme=None,
        radius=None,
        border_width=1,
        focus_border_width=2,
        placeholder="",
    ):
        """Create the frame and its chrome canvas (the inner widget is added later by
        install_inner).

        radius / border_width / focus_border_width: shape of the border; placeholder:
        the hint shown while the field is empty; theme: color overrides.
        """
        tk.Frame.__init__(self, master, bd=0, highlightthickness=0)
        self._init_plumbing(theme)
        self.placeholder = placeholder
        self._placeholder_label = None
        self.radius = radius
        self.border_width = border_width
        self.focus_border_width = focus_border_width
        self.inner = None
        self._focused = False
        self.chrome = _ChromeCanvas(
            self, self._paint_chrome, background_from=master, theme=theme
        )
        # The chrome canvas fills the frame and sits behind the inner widget (created
        # first, so it is lowest).
        self.chrome.place(x=0, y=0, relwidth=1, relheight=1)

    def install_inner(self, inner, **pack_options):
        """Pack the native widget inside the frame and make focus changes redraw the
        border.
        """
        self.inner = inner
        inner.pack(**pack_options)
        inner.bind("<FocusIn>", lambda _: self._set_focused(True), add="+")
        inner.bind("<FocusOut>", lambda _: self._set_focused(False), add="+")

    def _set_focused(self, value):
        """The inner widget gained or lost the keyboard focus: redraw the border
        (thicker, focus color).
        """
        self._focused = value
        self.chrome.schedule_redraw()

    def schedule_redraw(self):
        """Redraws of a composite are redraws of its chrome canvas."""
        self.chrome.schedule_redraw()

    # ---- forwarding ------------------------------------------------------
    def __getattr__(self, name):
        """Forward any attribute the frame does not have to the inner widget (get,
        insert, tag_configure, yview...).
        """
        inner = self.__dict__.get("inner")
        if inner is None or name.startswith("__"):
            raise AttributeError(name)
        return getattr(inner, name)

    def bbox(self, *arguments):
        """Forwarded explicitly: tk.Frame has its own bbox (grid) that would hide the
        inner one's.
        """
        return self.inner.bbox(*arguments)

    def selection_clear(self, *arguments):
        """Forwarded explicitly: tk.Misc has its own selection_clear that would hide the
        inner one's.
        """
        return self.inner.selection_clear(*arguments)

    def image_names(self):
        """Forwarded explicitly: tk.Misc has its own image_names that would hide a
        Text's.
        """
        return self.inner.image_names()

    def focus_set(self):
        """Focus the inner widget (the frame itself is not an editing widget)."""
        self.inner.focus_set()

    focus = focus_set

    def focus_force(self):
        """Force the focus onto the inner widget."""
        self.inner.focus_force()

    def bind(self, sequence=None, func=None, add=None):
        """Bind on the inner widget (where key and mouse events happen), except frame-level
        events such as <Configure>/<Map>/<Enter>, which bind on the frame.
        """
        if sequence is not None and sequence in _FRAME_LEVEL_SEQUENCES:
            return tk.Frame.bind(self, sequence, func, add)
        return self.inner.bind(sequence, func, add)

    def unbind(self, sequence, funcid=None):
        """Counterpart of bind(): remove the binding from the same widget it was made
        on.
        """
        if sequence in _FRAME_LEVEL_SEQUENCES:
            return tk.Frame.unbind(self, sequence, funcid)
        return self.inner.unbind(sequence, funcid)

    # ---- options ---------------------------------------------------------
    def configure(self, cnf=None, **kw):
        """configure(): our own options (shape, colors, placeholder) are handled here, color
        aliases like bg/fg become color parts, and everything else goes to the inner widget.
        """
        if cnf is None and not kw:
            return self.inner.configure()
        if isinstance(cnf, str):
            return self.inner.configure(cnf)
        if cnf:
            kw = {**cnf, **kw}
        for alias, part in self._NATIVE_COLOR_ALIASES.items():
            if alias in kw:
                kw[part] = kw.pop(alias)
        # Our own options (shape, colors, placeholder) stay here; the rest is for the
        # inner widget.
        own = {
            k: kw.pop(k)
            for k in list(kw)
            if k in self._OWN_OPTIONS or k in self._COLOR_PARTS
        }
        if own:
            self.apply_own_options(own)
        if kw:
            self.inner.configure(**kw)
            if "textvariable" in kw:
                self.watch_variable(kw["textvariable"])
        self._update_placeholder()
        self.restyle_inner()
        self.chrome.schedule_redraw()

    config = configure

    def cget(self, key):
        """cget(): color parts and our own options come from us; native options from the
        inner widget.
        """
        # Native color names (bg, fg...) report the inner widget's real,
        # current color (children such as the Textbox's scroll bar read the
        # background through this); only our own color parts report overrides.
        if key in self._COLOR_PARTS:
            return self._theme_overrides.get(key)
        if key in self._OWN_OPTIONS:
            return getattr(self, key)
        if self.inner is None:
            return tk.Frame.cget(self, key)
        return self.inner.cget(key)

    def apply_own_options(self, options):
        """Store changed own options (color parts go through set_color_part)."""
        for key, value in options.items():
            if key in self._COLOR_PARTS:
                self.set_color_part(key, value)
            else:
                setattr(self, key, value)

    # ---- placeholder ------------------------------------------------------
    # A hint shown (in its own colors) while the field is empty. It is a label
    # laid over the inner widget, so the field's real contents are untouched.
    def inner_is_empty(self):
        """Whether the field has no text (implemented by Entry and Textbox)."""
        raise NotImplementedError

    def placeholder_visible(self):
        """Whether the placeholder hint is showing: one was given and the field is
        empty.
        """
        return bool(self.placeholder) and self.inner_is_empty()

    def install_placeholder(self):
        """Create the placeholder label and keep it in step with the field."""
        label = tk.Label(
            self,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            anchor="w",
            justify="left",
            cursor="xterm",
        )
        label.bind("<Button-1>", lambda _: self.inner.focus_set())
        self._placeholder_label = label
        for sequence in (
            "<KeyRelease>",
            "<<Paste>>",
            "<<Cut>>",
            "<<Undo>>",
            "<<Redo>>",
            "<ButtonRelease-2>",
        ):
            self.inner.bind(
                sequence,
                lambda _: self.call_later(None, self._update_placeholder),
                add="+",
            )
        # The position depends on the widget's real size and geometry.
        for sequence in ("<Map>", "<Configure>"):
            self.inner.bind(
                sequence,
                lambda _: self.call_later(None, self._update_placeholder),
                add="+",
            )
        self._update_placeholder()

    def _placeholder_position(self):
        """Where the hint goes: where the first character would be drawn,
        just right of the text cursor (which sits there in an empty field).
        Everything is measured from the live widget."""
        inner = self.inner
        # The cursor is centered on the start of the text, insertwidth wide.
        after_cursor = (
            int(inner.cget("insertwidth")) - int(inner.cget("insertwidth")) // 2
        )
        inset = int(inner.cget("bd")) + int(inner.cget("highlightthickness"))
        if isinstance(inner, tk.Text):
            # bbox / dlineinfo give the exact cell and baseline of the first
            # line (None until the widget is on screen; then its padding).
            box = inner.bbox("1.0")
            line = inner.dlineinfo("1.0")
            if box and line:
                # Match the text baseline of the first line: the hint's label
                # draws its text with the baseline `ascent` below its top.
                ascent = make_font(inner.cget("font")).metrics("ascent")
                return dict(
                    x=box[0] + after_cursor, y=line[1] + line[4] - ascent, anchor="nw"
                )
            return dict(
                x=inset + int(inner.cget("padx")) + after_cursor,
                y=inset + int(inner.cget("pady")),
                anchor="nw",
            )
        # An Entry draws its text 1 px inside its border, centered vertically.
        line = make_font(inner.cget("font")).metrics("linespace")
        return dict(
            x=inset + 1 + after_cursor,
            y=max((inner.winfo_height() - line) // 2, 0),
            anchor="nw",
        )

    def _update_placeholder(self):
        """Show, move, or hide the hint label to match the field's contents, then restyle
        (the fill may depend on it).
        """
        label = self._placeholder_label
        if label is None or self.inner is None:
            return
        if self.placeholder_visible():
            position = self._placeholder_position()
            label.configure(text=self.placeholder)
            # bordermode "outside": coordinates are measured from the inner
            # widget's outer edge, the origin bbox/dlineinfo (and the font
            # metrics above) use. The default, "inside", measures from the
            # widget's internal border, which for a Text includes its padding.
            label.place(in_=self.inner, bordermode="outside", **position)
        else:
            label.place_forget()
        self.restyle_inner()
        self.chrome.schedule_redraw()

    def on_variable_changed(self):
        """A watched textvariable changed: the field may have become empty or non-empty."""
        self._update_placeholder()

    def field_fill(self, disabled):
        """The field's background: the placeholder fill color while the
        placeholder is shown (if one was given), else the normal fill."""
        if disabled:
            return self.part("disabled_fill_color", "surface_disabled")
        override = self._theme_overrides.get("placeholder_fill_color")
        if override and self.placeholder_visible():
            return self.rc(override)
        return self.part("fill_color", "surface")

    def restyle_placeholder(self, fill, disabled):
        """Give the hint label the field's background and the placeholder color/font
        (only touches Tk when something changed).
        """
        if self._placeholder_label is not None:
            style = dict(
                bg=fill,
                fg=self.part(
                    "placeholder_color", "text_disabled" if disabled else "text_muted"
                ),
                font=self.inner.cget("font"),
            )
            if style != getattr(self, "_applied_placeholder_style", None):
                self._applied_placeholder_style = style
                self._placeholder_label.configure(**style)

    def apply_inner_style(self, **options):
        """inner.configure(**options), but only when they differ from what
        was applied last: reconfiguring a Text/Entry on every keystroke makes
        Tk redraw it (and restart the cursor) for nothing."""
        if options != getattr(self, "_applied_inner_style", None):
            self._applied_inner_style = options
            self.inner.configure(**options)

    def insert(self, *arguments, **options):
        """Forwarded insert that also refreshes the placeholder."""
        result = self.inner.insert(*arguments, **options)
        self._update_placeholder()
        return result

    def delete(self, *arguments, **options):
        """Forwarded delete that also refreshes the placeholder."""
        result = self.inner.delete(*arguments, **options)
        self._update_placeholder()
        return result

    # ---- painting --------------------------------------------------------
    def restyle_inner(self):
        """Apply the theme colors to the native widget (implemented by Entry and
        Textbox).
        """
        raise NotImplementedError

    def on_theme_changed(self):
        """The theme changed: recolor the chrome and the native widget."""
        self.chrome.refresh_theme()
        self.restyle_inner()
        self.chrome.schedule_redraw()

    def inner_state(self):
        """The inner widget's state ('normal', 'readonly', or 'disabled')."""
        return str(self.inner.cget("state"))

    def _paint_chrome(self, chrome, width, height):
        """Paint the rounded border and fill (the fill is the inner widget's real
        background, so they always match).
        """
        fill = chrome.rc(self.inner.cget("background"))
        if self.inner_state() == "disabled":
            border = self.part("disabled_border_color", "border")
            border_width = self.border_width
        elif self._focused:
            border = self.part("focus_color", "focus_ring")
            border_width = self.focus_border_width
        else:
            border = self.part("border_color", "border")
            border_width = self.border_width
        chrome.draw_box(
            0,
            0,
            width,
            height,
            fill,
            border,
            border_width,
            self.corner(self.radius, "radius"),
        )
        self.paint_extras(chrome, width, height)

    def paint_extras(self, chrome, width, height):
        """Hook for subclasses to draw more on the chrome (arrows); nothing by default."""
        pass


def _select_all_in_entry(entry):
    """Control-a for entries: select everything (Tk's default would move the cursor to
    the line start).
    """
    entry.select_range(0, "end")
    entry.icursor("end")
    return "break"


class Entry(_FramedWidget):
    """A single-line text entry with a rounded canvas border."""

    def __init__(
        self,
        master,
        textvariable=None,
        show=None,
        state="normal",
        font=None,
        width=20,
        justify="left",
        theme=None,
        radius=None,
        border_width=1,
        focus_border_width=2,
        right_padding=8,
        placeholder="",
        **kwargs,
    ):
        """Create the entry.

        textvariable / show / state / font / width (characters) / justify: as tk.Entry.
        radius, border_width, focus_border_width: border shape. right_padding: space
        reserved at the right (Combobox/Spinbox put their arrows there). placeholder:
        hint while empty. Color options and native color names (bg, fg...) are accepted.
        """
        theme = {**(theme or {}), **self.extract_color_options(kwargs)}
        _FramedWidget.__init__(
            self,
            master,
            theme=theme,
            radius=radius,
            border_width=border_width,
            focus_border_width=focus_border_width,
            placeholder=placeholder,
        )
        options = dict(
            font=make_font(font),
            width=width,
            justify=justify,
            state=state,
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        if textvariable is not None:
            options["textvariable"] = textvariable
        if show is not None:
            options["show"] = show
        # The real editing widget; extra kwargs (validate, ...) go straight to it.
        entry = tk.Entry(self, **options, **kwargs)
        self.install_inner(
            entry, fill="both", expand=True, padx=(10, right_padding), pady=6
        )
        entry.bind("<Control-a>", lambda _: _select_all_in_entry(entry), add="+")
        # Refresh the placeholder when the text variable changes.
        self.watch_variable(textvariable)
        self.install_placeholder()
        self.restyle_inner()

    def inner_is_empty(self):
        """Whether the entry holds no text."""
        return not self.inner.get()

    def restyle_inner(self):
        """Apply fill, text, cursor, and selection colors to the tk.Entry (and the hint
        label).
        """
        disabled = self.inner_state() == "disabled"
        fill = self.field_fill(disabled)
        if disabled:
            foreground = self.part("disabled_text_color", "text_disabled")
        else:
            foreground = self.part("text_color", "text")
        self.restyle_placeholder(fill, disabled)
        self.apply_inner_style(
            bg=fill,
            fg=foreground,
            disabledbackground=fill,
            disabledforeground=foreground,
            readonlybackground=fill,
            insertbackground=self.part("cursor_color", "text"),
            selectbackground=self.part("selection_color", "selection"),
            selectforeground=self.part("selection_text_color", "selection_text"),
        )
        tk.Frame.configure(self, bg=fill)

    def set_text(self, text):
        """Replace the entry's text even when it is readonly/disabled."""
        state = self.inner_state()
        if state != "normal":
            self.inner.configure(state="normal")
        self.inner.delete(0, "end")
        self.inner.insert(0, text)
        if state != "normal":
            self.inner.configure(state=state)
        self._update_placeholder()


class Combobox(_DropdownOwner, Entry):
    """An entry with a drop-down list of values (type, or pick one).

    The list is a canvas-drawn popup that scrolls past popup_max_height. With
    state='readonly' the whole field opens the list instead of being editable.
    Generates <<ComboboxSelected>> when a value is picked.
    """

    ARROW_WIDTH = 28
    _COLOR_PARTS = Entry._COLOR_PARTS + _DropdownOwner.POPUP_COLOR_PARTS
    _OWN_OPTIONS = Entry._OWN_OPTIONS + (
        "values",
        "command",
        "postcommand",
        "popup_font",
        "popup_max_height",
        "popup_scrollbar_width",
    )

    def __init__(
        self,
        master,
        values=(),
        command=None,
        postcommand=None,
        state="normal",
        popup_font=None,
        popup_max_height=260,
        popup_scrollbar_width=None,
        **kwargs,
    ):
        """Create the combo box.

        values: the list entries. command(value) / postcommand(): called after a pick /
        before the list opens. popup_font / popup_max_height / popup_scrollbar_width: the
        list's font, the height (px) after which it scrolls, and its scroll bar's width
        (px). Everything else is as Entry.
        """
        Entry.__init__(
            self, master, state=state, right_padding=self.ARROW_WIDTH, **kwargs
        )
        self.popup_font = popup_font
        self.popup_max_height = popup_max_height
        self.popup_scrollbar_width = popup_scrollbar_width
        self.values = list(values)
        self.command = command
        self.postcommand = postcommand
        self._init_dropdown()
        self.chrome.bind("<ButtonPress-1>", self._on_chrome_press, add="+")
        self.inner.bind("<ButtonPress-1>", self._on_inner_press, add="+")
        self.inner.bind("<Down>", lambda _: self.open_dropdown(), add="+")

    def _on_chrome_press(self, event):
        """Click on the border area: the arrow part toggles the list."""
        if self.inner_state() == "disabled":
            return
        if event.x >= self.chrome.winfo_width() - self.ARROW_WIDTH:
            self.toggle_dropdown()

    def _on_inner_press(self, _):
        """Click on the text part: toggles the list only in the readonly state."""
        if self.inner_state() == "readonly":
            self.toggle_dropdown()

    def open_dropdown(self):
        """Open the list below the field (unless disabled or already open); postcommand
        runs first.
        """
        if self.inner_state() == "disabled" or self._dropdown is not None:
            return
        if self.postcommand is not None:
            self.postcommand()
        self.show_dropdown(
            self,
            self.values,
            self.inner.get(),
            self.pick,
            make_font(self.inner.cget("font")),
        )

    def pick(self, value):
        """A value was chosen in the list: set it, announce <<ComboboxSelected>>, and run
        the command.
        """
        self.set(value)
        self.inner.event_generate("<<ComboboxSelected>>")
        if self.command is not None:
            self.command(value)

    def set(self, value):
        """Set the text to a value."""
        self.set_text(str(value))

    def current(self, index=None):
        """With no argument: the index of the current text in values (-1 if absent);
        with an index: select that value.
        """
        if index is None:
            text = self.inner.get()
            return self.values.index(text) if text in self.values else -1
        self.set(self.values[index])

    def paint_extras(self, chrome, width, height):
        """Draw the drop-down chevron (pointing up while the list is open)."""
        chrome.draw_chevron(
            width - self.ARROW_WIDTH / 2 - 2,
            height / 2,
            "up" if self._dropdown is not None else "down",
            (
                self.part("disabled_arrow_color", "text_disabled")
                if self.inner_state() == "disabled"
                else self.part("arrow_color", "text_muted")
            ),
        )


def _decimal_places(number):
    """How many decimals a number needs (0 for 3, 1 for 0.5, 2 for 0.25...)."""
    text = f"{number:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


class Spinbox(Entry):
    """A number (or value-list) entry with up/down arrows.

    Typing is restricted to text that can be the start of a valid value; the
    arrows (hold to repeat) and the Up/Down keys step by `increment`; leaving the
    field corrects the value into range. With `values` it steps through that list.
    """

    ARROW_WIDTH = 24
    _COLOR_PARTS = Entry._COLOR_PARTS + ("arrow_active_color",)
    _OWN_OPTIONS = Entry._OWN_OPTIONS + (
        "from_",
        "to",
        "increment",
        "values",
        "wrap",
        "command",
    )

    def __init__(
        self,
        master,
        from_=0,
        to=100,
        increment=1,
        values=None,
        wrap=False,
        command=None,
        width=8,
        **kwargs,
    ):
        """Create the spin box.

        from_ / to / increment: the numeric range and step. values: step through this
        list of strings instead. wrap: go around at the ends. command(): called after
        every step. width: characters. Everything else is as Entry.
        """
        # A validatecommand the caller gave replaces the built-in typing rule.
        own_validation = "validatecommand" in kwargs
        Entry.__init__(
            self, master, width=width, right_padding=self.ARROW_WIDTH, **kwargs
        )
        if not own_validation:
            # Only text that can be (the start of) a valid value can be typed.
            self.inner.configure(
                validate="key",
                validatecommand=(self.register(self._allows_typing), "%P"),
            )
        self.from_ = from_
        self.to = to
        self.increment = increment
        self.values = list(values) if values else None
        self.wrap = wrap
        self.command = command
        self._pressed_arrow = None
        self._repeat_id = None
        if not self.inner.get():
            self.set_text(
                self._format(from_) if self.values is None else self.values[0]
            )
        self.chrome.bind("<ButtonPress-1>", self._on_arrow_press, add="+")
        self.chrome.bind("<ButtonRelease-1>", lambda _: self._stop_repeat(), add="+")
        self.inner.bind("<Up>", lambda _: self.step(1) or "break", add="+")
        self.inner.bind("<Down>", lambda _: self.step(-1) or "break", add="+")
        self.inner.bind("<FocusOut>", lambda _: self._normalize(), add="+")

    def _allows_typing(self, proposed):
        """validatecommand: whether the text, as it would be after this edit,
        can be (the beginning of) a valid value."""
        if proposed == "":
            return True
        if self.values is not None:
            return any(str(value).startswith(proposed) for value in self.values)
        places = max(
            _decimal_places(self.increment),
            _decimal_places(self.from_),
            _decimal_places(self.to),
        )
        sign = "-?" if min(self.from_, self.to) < 0 else ""
        decimals = rf"(\.\d{{0,{places}}})?" if places else ""
        return re.fullmatch(rf"{sign}\d*{decimals}", proposed) is not None

    def _format(self, number):
        """Format a number with as many decimals as the increment/start use (an integer
        if none).
        """
        places = max(_decimal_places(self.increment), _decimal_places(self.from_))
        return str(int(round(number))) if places == 0 else f"{number:.{places}f}"

    def _number(self):
        """The entry's text as a float, or None if it is not a number."""
        try:
            return float(self.inner.get())
        except ValueError:
            return None

    def _normalize(self):
        """Correct the text after editing: clamp a number into the range, or fall back
        to the first value.
        """
        if self.values is not None:
            if self.inner.get() not in self.values:
                self.set_text(self.values[0])
            return
        number = self._number()
        low, high = sorted((self.from_, self.to))
        self.set_text(
            self._format(low if number is None else min(max(number, low), high))
        )

    def step(self, direction):
        """Move one increment (or one of values) up (+1) or down (-1)."""
        if self.inner_state() == "disabled":
            return
        if self.values is not None:
            text = self.inner.get()
            index = (
                self.values.index(text)
                if text in self.values
                else (-1 if direction > 0 else len(self.values))
            )
            index += direction
            if self.wrap:
                index %= len(self.values)
            index = min(max(index, 0), len(self.values) - 1)
            self.set_text(str(self.values[index]))
        else:
            number = self._number()
            low, high = sorted((self.from_, self.to))
            number = low if number is None else number + direction * self.increment
            if number > high:
                number = low if self.wrap else high
            elif number < low:
                number = high if self.wrap else low
            self.set_text(self._format(number))
        if self.command is not None:
            self.command()

    def _on_arrow_press(self, event):
        """Click on an arrow: step once, then start the auto-repeat."""
        if event.x < self.chrome.winfo_width() - self.ARROW_WIDTH:
            return
        direction = 1 if event.y < self.chrome.winfo_height() / 2 else -1
        self._pressed_arrow = direction
        self.chrome.schedule_redraw()
        self.step(direction)
        self._repeat_id = self.call_later(400, self._repeat)

    def _repeat(self):
        """Auto-repeat while an arrow is held."""
        self.step(self._pressed_arrow)
        self._repeat_id = self.call_later(70, self._repeat)

    def _stop_repeat(self):
        """The mouse button came up: stop repeating and release the arrow highlight."""
        self.cancel_call(self._repeat_id)
        self._repeat_id = None
        self._pressed_arrow = None
        self.chrome.schedule_redraw()

    def paint_extras(self, chrome, width, height):
        """Draw the up and down chevrons (the pressed one in the active color)."""
        disabled = self.inner_state() == "disabled"
        x = width - self.ARROW_WIDTH / 2 - 2
        # Two chevrons: up at the top half, down at the bottom half.
        for direction, y in ((1, height / 2 - 5), (-1, height / 2 + 5)):
            if disabled:
                color = self.part("disabled_arrow_color", "text_disabled")
            elif self._pressed_arrow == direction:
                color = self.part("arrow_active_color", "accent")
            else:
                color = self.part("arrow_color", "text_muted")
            chrome.draw_chevron(x, y, "up" if direction > 0 else "down", color, size=4)


class Textbox(_FramedWidget):
    """A multi-line text box with a rounded canvas border and an optional
    built-in scrollbar. Everything tk.Text offers is forwarded."""

    _OWN_OPTIONS = _FramedWidget._OWN_OPTIONS + (
        "yscrollcommand",
        "xscrollcommand",
        "scrollbar_width",
    )
    _SCROLLBAR_PARTS = {
        "scrollbar_track_color": "track_color",
        "scrollbar_thumb_color": "thumb_color",
        "scrollbar_thumb_hover_color": "thumb_hover_color",
    }
    _COLOR_PARTS = _FramedWidget._COLOR_PARTS + tuple(_SCROLLBAR_PARTS)

    def __init__(
        self,
        master,
        scrolled=False,
        font=None,
        wrap="none",
        state="normal",
        width=80,
        height=24,
        yscrollcommand=None,
        xscrollcommand=None,
        orient="vertical",
        scrollbar_width=None,
        theme=None,
        radius=None,
        border_width=1,
        focus_border_width=2,
        placeholder="",
        **kwargs,
    ):
        """Create the text box.

        scrolled: add built-in canvas scroll bars that hide themselves when not needed.
        wrap / state / width (characters) / height (lines) / font: as tk.Text (80 x 24
        characters by default, like tk.Text).
        orient: with scrolled, which scroll bars there are: "vertical", "horizontal", or
        "both". yscrollcommand / xscrollcommand: for scroll bars of your own (they work
        together with scrolled). scrollbar_width: the width in px of the built-in scroll
        bars (14 by default).
        radius, border_width, focus_border_width: border shape (radius None = the
        theme's). placeholder: hint
        while empty.
        """
        if orient not in ("vertical", "horizontal", "both"):
            raise ValueError("orient must be 'vertical', 'horizontal' or 'both'")
        theme = {**(theme or {}), **self.extract_color_options(kwargs)}
        _FramedWidget.__init__(
            self,
            master,
            theme=theme,
            radius=radius,
            border_width=border_width,
            focus_border_width=focus_border_width,
            placeholder=placeholder,
        )
        kwargs.setdefault("padx", 3)
        kwargs.setdefault("pady", 3)
        # A 1 px cursor: Tk draws a wider one half-clipped at the start of a line.
        kwargs.setdefault("insertwidth", 1)
        self.scrollbar = self.horizontal_scrollbar = None
        self._user_yscrollcommand = yscrollcommand
        self._user_xscrollcommand = xscrollcommand
        text = tk.Text(
            self,
            font=make_font(font),
            wrap=wrap,
            state=state,
            width=width,
            height=height,
            relief="flat",
            bd=0,
            highlightthickness=0,
            **kwargs,
        )
        if scrolled:
            # Built-in scroll bars: the Text is packed to the left of the vertical one
            # and above the horizontal one, and scrolls them.
            vertical, horizontal = orient != "horizontal", orient != "vertical"
            scrollbar_theme = {
                own_name: theme[name]
                for name, own_name in self._SCROLLBAR_PARTS.items()
                if name in theme
            }
            width_option = (
                {} if scrollbar_width is None else {"thickness": scrollbar_width}
            )
            if horizontal:
                self.horizontal_scrollbar = Scrollbar(
                    self,
                    orient="horizontal",
                    command=text.xview,
                    autohide=True,
                    theme=scrollbar_theme,
                    **width_option,
                )
                self.horizontal_scrollbar.pack(
                    side="bottom", fill="x", padx=5, pady=(0, 5)
                )
                text.configure(xscrollcommand=self._on_xscroll)
            if vertical:
                self.scrollbar = Scrollbar(
                    self,
                    command=text.yview,
                    autohide=True,
                    theme=scrollbar_theme,
                    **width_option,
                )
                self.scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
                text.configure(yscrollcommand=self._on_yscroll)
            self.install_inner(
                text,
                side="left",
                fill="both",
                expand=True,
                padx=(7, 2) if vertical else 7,
                pady=(5, 2) if horizontal else 5,
            )
        else:
            if yscrollcommand is not None:
                text.configure(yscrollcommand=yscrollcommand)
            if xscrollcommand is not None:
                text.configure(xscrollcommand=xscrollcommand)
            self.install_inner(text, fill="both", expand=True, padx=7, pady=5)
        text.bind("<Control-a>", self._select_all, add="+")
        self.install_placeholder()
        self.restyle_inner()

    def inner_is_empty(self):
        """Whether the text box holds no text."""
        return not self.inner.get("1.0", "end-1c")

    def replace(self, *arguments, **options):
        """Forwarded replace that also refreshes the placeholder."""
        result = self.inner.replace(*arguments, **options)
        self._update_placeholder()
        return result

    def _select_all(self, _):
        """Control-a: select all the text."""
        self.inner.tag_add("sel", "1.0", "end")
        return "break"

    def _on_yscroll(self, first, last):
        """The Text scrolled: update the built-in scroll bar and pass it on to a user's
        yscrollcommand.
        """
        self.scrollbar.set(first, last)
        if self._user_yscrollcommand is not None:
            self._user_yscrollcommand(first, last)

    def _on_xscroll(self, first, last):
        """The Text scrolled sideways: update the built-in horizontal scroll bar and
        pass it on to a user's xscrollcommand.
        """
        self.horizontal_scrollbar.set(first, last)
        if self._user_xscrollcommand is not None:
            self._user_xscrollcommand(first, last)

    def apply_own_options(self, options):
        """Store changed own options; scroll bar colors are also applied to the built-in
        scroll bar.
        """
        for key, value in options.items():
            if key == "yscrollcommand":
                self._user_yscrollcommand = value
                if self.scrollbar is None:
                    self.inner.configure(yscrollcommand=value)
            elif key == "xscrollcommand":
                self._user_xscrollcommand = value
                if self.horizontal_scrollbar is None:
                    self.inner.configure(xscrollcommand=value)
            elif key == "scrollbar_width":
                self.scrollbar_width = value
                for bar in (self.scrollbar, self.horizontal_scrollbar):
                    if bar is not None:
                        bar.configure(thickness=value)
            elif key in self._COLOR_PARTS:
                self.set_color_part(key, value)
                if key in self._SCROLLBAR_PARTS:
                    for bar in (self.scrollbar, self.horizontal_scrollbar):
                        if bar is not None:
                            bar.set_color_part(self._SCROLLBAR_PARTS[key], value)
                            bar.schedule_redraw()
            else:
                setattr(self, key, value)

    def restyle_inner(self):
        """Apply fill, text, cursor, and selection colors to the tk.Text (and the hint
        label).
        """
        disabled = self.inner_state() == "disabled"
        selection = self.part("selection_color", "selection")
        fill = self.field_fill(disabled)
        if disabled:
            foreground = self.part("disabled_text_color", "text_disabled")
        else:
            foreground = self.part("text_color", "text")
        self.restyle_placeholder(fill, disabled)
        self.apply_inner_style(
            bg=fill,
            fg=foreground,
            insertbackground=self.part("cursor_color", "text"),
            selectbackground=selection,
            selectforeground=self.part("selection_text_color", "selection_text"),
            inactiveselectbackground=selection,
        )
        tk.Frame.configure(self, bg=fill)
