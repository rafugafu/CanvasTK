"""Popups: the drop-down list, menus, the menu bar, the option menu, and tooltips.

Everything that pops up is a borderless, always-on-top tk.Toplevel whose
contents are drawn on a canvas (_CanvasPopup). Combobox and OptionMenu open one
as a value list (_DropdownOwner), Menu opens one (with cascading submenus), and
MenuBar and Tooltip build on them.
"""

import time
import tkinter as tk
import tkinter.font as tkfont

from ._core import (
    CANVAS_WIDGET_THEME,
    CanvasWidget,
    expand_theme,
    starting_theme,
    window_theme,
    _CANVAS_CHROME_TAG,
    _WHEEL_SEQUENCES,
    _inside,
    make_font,
    measure_widths,
    resolve_color,
    rounded_box_image,
    wheel_direction,
)

# =============================================================================
# Popups shared by Combobox, OptionMenu, Menu, and MenuBar
# =============================================================================


class _CanvasPopup(tk.Toplevel):
    """A borderless popup list drawn on a canvas. entries is a list of dicts:
    kind ('item'|'command'|'check'|'radio'|'cascade'|'separator'), label,
    accelerator, state, checked, current, submenu (a Menu), invoke (callable).
    Closes on outside click, Escape, window move, or losing app focus."""

    ROW_PADDING = 10
    SEPARATOR_HEIGHT = 9
    VERTICAL_PADDING = 4
    SCROLLBAR_WIDTH = 12

    def __init__(
        self,
        owner,
        entries,
        font,
        colors,
        min_width=0,
        max_rows=40,
        max_height=None,
        on_close=None,
        parent_popup=None,
    ):
        """max_rows / max_height (pixels) limit how tall the list gets; past
        that it scrolls (wheel, keys, or its scroll bar). max_height wins."""
        tk.Toplevel.__init__(self, owner)
        self.withdraw()
        # A borderless window the window manager leaves alone, kept above everything
        # else, shown at an exact screen position.
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.owner = owner
        self.entries = entries
        self.font = font
        self.on_close = on_close
        self.parent_popup = parent_popup
        self.child_popup = None
        self._child_index = None
        self._colors = {
            key: resolve_color(self, value) for key, value in colors.items()
        }
        self._colors_source = colors
        self._closed = False
        self._hover = None
        self._pressed_inside = False
        self._images = []
        self._top = 0
        # State: first visible entry, hover, scroll thumb drag, pending timers, and the
        # owner-window binding.
        self._max_rows = max_rows
        self._max_height = max_height
        self._scroll_drag_offset = None
        self._cascade_id = None
        self._focus_check_id = None
        self._outside_binding = None
        self._row_height = font.metrics("linespace") + self.ROW_PADDING
        self._measure(min_width)
        self._reveal_current_entry()
        self.canvas = tk.Canvas(
            self,
            width=self.width,
            height=self.height,
            bd=0,
            highlightthickness=0,
            bg=self._colors["surface"],
        )
        self.canvas.pack()
        # Mouse handling on the canvas; keyboard handling on the window itself.
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        for sequence in _WHEEL_SEQUENCES:
            self.canvas.bind(sequence, self._on_wheel)
        # Keyboard: arrows move, Return/space choose, Right/Left enter/leave submenus,
        # Escape closes.
        self.bind("<Up>", lambda _: self._move(-1))
        self.bind("<Down>", lambda _: self._move(1))
        self.bind("<Home>", lambda _: self._move_to_edge(False))
        self.bind("<End>", lambda _: self._move_to_edge(True))
        self.bind("<Return>", lambda _: self._activate(self._hover))
        self.bind("<space>", lambda _: self._activate(self._hover))
        self.bind("<Right>", lambda _: self._open_cascade(self._hover, True))
        self.bind("<Left>", lambda _: self._close_to_parent())
        self.bind("<Escape>", lambda _: self._escape())
        self.bind("<FocusOut>", lambda _: self._schedule_focus_check())

    # ---- layout ----------------------------------------------------------
    def _entry_height(self, entry):
        """The height of one entry (a separator is thin)."""
        return (
            self.SEPARATOR_HEIGHT if entry["kind"] == "separator" else self._row_height
        )

    def _measure(self, min_width):
        """Work out the popup's size from its entries.

        Fits the widest label (plus mark column, accelerators, cascade arrow, and the
        scroll bar when needed) and the entries that fit in max_height; the rest scroll.
        """
        entries = self.entries
        has_marks = any(entry["kind"] in ("check", "radio") for entry in entries)
        has_arrow = any(entry["kind"] == "cascade" for entry in entries)
        self._text_x = 32 if has_marks else 14
        self._right_padding = 28 if has_arrow else 14
        label_width = max(
            measure_widths(
                self,
                self.font,
                [e["label"] for e in entries if e["kind"] != "separator"],
            ),
            default=0,
        )
        accelerator_width = max(
            measure_widths(
                self,
                self.font,
                [e["accelerator"] for e in entries if e.get("accelerator")],
            ),
            default=0,
        )
        # Fit as many entries as the maximum height allows; the others scroll.
        if self._max_height is not None:
            available = self._max_height - 2 * self.VERTICAL_PADDING
            used = fitting = 0
            for entry in entries:
                entry_height = self._entry_height(entry)
                if used + entry_height > available and fitting:
                    break
                used += entry_height
                fitting += 1
            self._max_rows = max(1, fitting)
        self._scrolling = len(entries) > self._max_rows
        self.width = max(
            min_width,
            self._text_x
            + label_width
            + (28 + accelerator_width if accelerator_width else 0)
            + self._right_padding
            + (self.SCROLLBAR_WIDTH if self._scrolling else 0),
        )
        visible = entries[: self._max_rows]
        self.height = sum(map(self._entry_height, visible)) + 2 * self.VERTICAL_PADDING

    def _reveal_current_entry(self):
        """Start scrolled so the entry marked current is in view."""
        if not self._scrolling:
            return
        for index, entry in enumerate(self.entries):
            if entry.get("current"):
                self._top = min(
                    max(index - self._max_rows // 2, 0),
                    len(self.entries) - self._max_rows,
                )
                return

    def _scroll_thumb(self):
        """(top, height) of the scroll bar thumb in pixels."""
        count = len(self.entries)
        span = self.height - 2 * self.VERTICAL_PADDING
        thumb_height = max(18, span * self._max_rows / count)
        movable = span - thumb_height
        hidden = count - self._max_rows
        top = self.VERTICAL_PADDING + (movable * self._top / hidden if hidden else 0)
        return top, thumb_height

    def _rows(self):
        """(index, top, bottom) of every visible entry."""
        y = self.VERTICAL_PADDING
        for index in range(
            self._top, min(len(self.entries), self._top + self._max_rows)
        ):
            bottom = y + self._entry_height(self.entries[index])
            yield index, y, bottom
            y = bottom

    def _index_at(self, y):
        """The entry index under a y coordinate, or None."""
        for index, top, bottom in self._rows():
            if top <= y < bottom:
                return index
        return None

    def _selectable(self, index):
        """Whether an entry can be hovered/chosen (not a separator, not disabled)."""
        entry = self.entries[index]
        return (
            entry["kind"] != "separator" and entry.get("state", "normal") != "disabled"
        )

    # ---- drawing ---------------------------------------------------------
    def _draw(self):
        """Redraw the whole popup: border, rows (hover/current highlight, check/radio marks,
        label, accelerator, cascade arrow), separators and the scroll bar.
        """
        canvas = self.canvas
        colors = self._colors
        canvas.delete("all")
        self._images = []

        def draw_box(x1, y1, x2, y2, fill, radius=0, outline=None, outline_width=0):
            """Draw one anti-aliased rounded box (the popup's own small helper; popups
            are plain canvases).
            """
            image = rounded_box_image(
                round(x2 - x1), round(y2 - y1), radius, fill, outline, outline_width
            )
            if image:
                self._images.append(image)
                canvas.create_image(round(x1), round(y1), anchor="nw", image=image)

        draw_box(
            0, 0, self.width, self.height, colors["surface"], 0, colors["border"], 1
        )
        for index, top, bottom in self._rows():
            entry = self.entries[index]
            center = (top + bottom) / 2
            if entry["kind"] == "separator":
                canvas.create_line(
                    10, center, self.width - 10, center, fill=colors["separator"]
                )
                continue
            disabled = entry.get("state", "normal") == "disabled"
            if index == self._hover and not disabled:
                draw_box(4, top, self.width - 4, bottom, colors["accent_hover"], 5)
                text_color = colors["accent_text"]
            else:
                if entry.get("current"):
                    draw_box(4, top, self.width - 4, bottom, colors["row_current"], 5)
                text_color = colors["text_disabled" if disabled else "text"]
            if entry["kind"] == "check" and entry.get("checked"):
                canvas.create_line(
                    11,
                    center,
                    14.5,
                    center + 3.5,
                    20,
                    center - 4,
                    fill=text_color,
                    width=2,
                    capstyle="round",
                    joinstyle="round",
                )
            elif entry["kind"] == "radio" and entry.get("checked"):
                draw_box(12, center - 3.5, 19, center + 3.5, text_color, 3.5)
            canvas.create_text(
                self._text_x,
                center,
                text=entry["label"],
                font=self.font,
                fill=text_color,
                anchor="w",
            )
            if entry.get("accelerator"):
                canvas.create_text(
                    self.width - self._right_padding,
                    center,
                    text=entry["accelerator"],
                    font=self.font,
                    fill=text_color if index == self._hover else colors["text_muted"],
                    anchor="e",
                )
            if entry["kind"] == "cascade":
                x = self.width - 16
                canvas.create_line(
                    x - 2,
                    center - 4,
                    x + 2,
                    center,
                    x - 2,
                    center + 4,
                    fill=text_color,
                    width=2,
                    capstyle="round",
                    joinstyle="round",
                )
        if self._scrolling:
            bar_left = self.width - self.SCROLLBAR_WIDTH
            draw_box(
                bar_left,
                self.VERTICAL_PADDING,
                self.width - 3,
                self.height - self.VERTICAL_PADDING,
                colors["track"],
                (self.SCROLLBAR_WIDTH - 3) / 2,
            )
            thumb_top, thumb_height = self._scroll_thumb()
            draw_box(
                bar_left + 1,
                thumb_top,
                self.width - 4,
                thumb_top + thumb_height,
                colors[
                    "thumb_hover" if self._scroll_drag_offset is not None else "thumb"
                ],
                (self.SCROLLBAR_WIDTH - 5) / 2,
            )

    # ---- showing / closing -------------------------------------------------
    def show(self, x, y, flip_y=None, left_x=None):
        """Show with its top-left at (x, y) in screen coordinates; if it
        would overflow the screen, flip above flip_y / left of left_x."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        if x + self.width > screen_width:
            x = left_x - self.width if left_x is not None else screen_width - self.width
        if y + self.height > screen_height:
            y = (
                flip_y - self.height
                if flip_y is not None
                else screen_height - self.height
            )
        self.geometry(f"{self.width}x{self.height}+{max(0, x)}+{max(0, y)}")
        self._draw()
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass
        # The top popup watches its owner's window: any click in it, or a move/resize,
        # closes the popups.
        if self.parent_popup is None:
            top = self.owner.winfo_toplevel()
            self._outside_binding = (
                top,
                top.bind("<ButtonPress>", lambda _: self.close(), add="+"),
                top.bind(
                    "<Configure>",
                    lambda e, t=top: e.widget is t and self.close(),
                    add="+",
                ),
            )

    def root_popup(self):
        """The top popup of a chain of cascading submenus (this one if it is the top)."""
        popup = self
        while popup.parent_popup is not None:
            popup = popup.parent_popup
        return popup

    def close_all(self):
        """Close the whole chain of popups, from the top one down."""
        self.root_popup().close()

    def close(self):
        """Close this popup and its submenus, cancel timers and bindings, destroy the
        window, and report on_close.
        """
        if self._closed:
            return
        self._closed = True
        child, self.child_popup = self.child_popup, None
        if child is not None:
            child.close()
        for identifier in (self._cascade_id, self._focus_check_id):
            if identifier is not None:
                self.after_cancel(identifier)
        if self._outside_binding is not None:
            top, press_id, configure_id = self._outside_binding
            top.unbind("<ButtonPress>", press_id)
            top.unbind("<Configure>", configure_id)
            self._outside_binding = None
        if self.parent_popup is not None:
            self.parent_popup.child_popup = None
        self.destroy()
        if self.on_close is not None:
            self.on_close()

    def _schedule_focus_check(self):
        """Focus left the popup: check shortly whether it left the whole application."""
        if self._focus_check_id is None and not self._closed:
            self._focus_check_id = self.after(80, self._check_focus)

    def _check_focus(self):
        """Close the popups if no window of this application has the focus any more."""
        self._focus_check_id = None
        if not self._closed and self.focus_displayof() is None:
            self.close_all()

    def _escape(self):
        """Escape: close a submenu (back to its parent) or, for the top popup,
        everything.
        """
        if self.parent_popup is not None:
            self._close_to_parent()
        else:
            self.close()

    def _close_to_parent(self):
        """Close this submenu and give the focus back to its parent popup."""
        parent = self.parent_popup
        if parent is not None:
            self.close()
            parent.focus_force()

    # ---- interaction -----------------------------------------------------
    def _set_hover(self, index):
        """Highlight the entry at index (or none).

        Hovering a cascade entry opens its submenu after a short delay; hovering any
        other entry closes an open submenu.
        """
        if index is not None and not self._selectable(index):
            index = None
        if index == self._hover:
            # Motion events keep firing on the same row; re-arming the
            # cascade timer here would close and recreate an open submenu.
            return
        self._hover = index
        self._draw()
        if self._cascade_id is not None:
            self.after_cancel(self._cascade_id)
            self._cascade_id = None
        if index is not None and self.entries[index]["kind"] == "cascade":
            # Open a submenu only after the pointer rests on its row (so moving across
            # rows does not flicker).
            self._cascade_id = self.after(250, lambda: self._open_cascade(index))
        elif self.child_popup is not None:
            self.child_popup.close()

    def _on_motion(self, event):
        """Pointer moved: hover the entry under it."""
        self._set_hover(self._index_at(event.y))

    def _on_leave(self, _):
        """Pointer left: clear the hover (unless a submenu is open from the hovered
        row).
        """
        if self.child_popup is None:
            self._set_hover(None)

    def _over_scrollbar(self, x):
        """Whether an x coordinate is over the scroll bar column."""
        return self._scrolling and x >= self.width - self.SCROLLBAR_WIDTH - 2

    def _on_press(self, event):
        """Mouse down: start dragging the scroll thumb / page the list, or remember a
        press on an entry.
        """
        if not self._over_scrollbar(event.x):
            self._pressed_inside = True
            return
        thumb_top, thumb_height = self._scroll_thumb()
        if thumb_top <= event.y <= thumb_top + thumb_height:
            self._scroll_drag_offset = event.y - thumb_top
            self._draw()
        else:
            self._scroll(self._max_rows if event.y > thumb_top else -self._max_rows)

    def _on_drag(self, event):
        """Dragging the scroll thumb: scroll to match."""
        if self._scroll_drag_offset is None:
            return
        _, thumb_height = self._scroll_thumb()
        movable = self.height - 2 * self.VERTICAL_PADDING - thumb_height
        hidden = len(self.entries) - self._max_rows
        if movable <= 0:
            return
        fraction = (
            event.y - self._scroll_drag_offset - self.VERTICAL_PADDING
        ) / movable
        top = round(min(max(fraction, 0), 1) * hidden)
        if top != self._top:
            self._top = top
            self._draw()

    def _on_release(self, event):
        """Mouse up: end a thumb drag, or choose the entry that was pressed."""
        if self._scroll_drag_offset is not None:
            self._scroll_drag_offset = None
            self._draw()
            return
        if self._pressed_inside:
            self._pressed_inside = False
            self._activate(self._index_at(event.y))

    def _on_wheel(self, event):
        """Mouse wheel: scroll the list two entries per notch (only if it scrolls)."""
        if self._scrolling:
            self._scroll(wheel_direction(event) * 2)

    def _scroll(self, amount):
        """Scroll by `amount` entries (clamped) and redraw."""
        top = min(max(self._top + amount, 0), len(self.entries) - self._max_rows)
        if top != self._top:
            self._top = top
            self._draw()

    def _move(self, step):
        """Keyboard: move the hover to the next selectable entry up (-1) or down (+1),
        wrapping and scrolling to keep it visible.
        """
        count = len(self.entries)
        index = self._hover if self._hover is not None else (-1 if step > 0 else count)
        for _ in range(count):
            index = (index + step) % count
            if self._selectable(index):
                break
        else:
            return
        if index < self._top:
            self._top = index
        elif index >= self._top + self._max_rows:
            self._top = index - self._max_rows + 1
        self._hover = index
        self._draw()

    def _move_to_edge(self, last):
        """Keyboard (Home/End): hover the first or last selectable entry."""
        self._hover = None
        self._move(-1 if last else 1)

    def _open_cascade(self, index, focus=False):
        """Open the submenu of a cascade entry beside its row (focus=True also hovers
        its first entry).
        """
        if index is None or self._closed:
            return
        entry = self.entries[index]
        if entry["kind"] != "cascade" or not self._selectable(index):
            return
        if self.child_popup is not None:
            if self._child_index == index:
                if focus:
                    self.child_popup._move(1)
                return
            self.child_popup.close()
        self._child_index = index
        submenu = entry["submenu"]
        child = _CanvasPopup(
            self.owner,
            submenu._snapshot(),
            self.font,
            self._colors_source,
            parent_popup=self,
        )
        self.child_popup = child
        top = next(top for i, top, _ in self._rows() if i == index)
        child.show(
            self.winfo_rootx() + self.width - 3,
            self.winfo_rooty() + top - self.VERTICAL_PADDING,
            left_x=self.winfo_rootx() + 3,
        )
        if focus:
            child._move(1)

    def _activate(self, index):
        """Choose an entry: open a cascade's submenu, or close everything and run the
        entry's action.
        """
        if index is None or not self._selectable(index):
            return
        entry = self.entries[index]
        if entry["kind"] == "cascade":
            self._open_cascade(index, True)
            return
        # Close the popups first, then run the action (it may open another window).
        invoke = entry.get("invoke")
        self.close_all()
        if invoke is not None:
            invoke()


# Popup-list color options (on Combobox/OptionMenu with a popup_ prefix, on
# Menu without it) and the theme color each one overrides inside the popup.
# Maps each popup color option to the theme key the popup draws with.
_POPUP_COLOR_THEME_KEYS = {
    "fill_color": "surface",
    "border_color": "border",
    "hover_color": "accent_hover",
    "hover_text_color": "accent_text",
    "text_color": "text",
    "disabled_text_color": "text_disabled",
    "muted_text_color": "text_muted",
    "current_color": "row_current",
    "separator_color": "separator",
    "thumb_color": "thumb",
}


class _DropdownOwner:
    """Opens a _CanvasPopup list below a widget (Combobox, OptionMenu)."""

    POPUP_COLOR_PARTS = tuple(f"popup_{name}" for name in _POPUP_COLOR_THEME_KEYS)

    def popup_colors(self):
        """The widget's colors with its popup_* options applied."""
        colors = dict(self.colors)
        for name, key in _POPUP_COLOR_THEME_KEYS.items():
            value = self._theme_overrides.get(f"popup_{name}")
            if value:
                colors[key] = value
        return colors

    popup_font = None  # a font for the dropdown list (None = the widget's font)
    popup_max_height = 260  # the list scrolls once it would be taller (pixels)

    def _init_dropdown(self):
        """Set up the open-popup state (call once from the widget's __init__)."""
        self._dropdown = None
        self._dropdown_closed_at = 0.0

    def toggle_dropdown(self):
        """Close the list if open, otherwise open it.

        The short grace period after closing prevents the click that closed the list
        (by hitting the widget) from immediately reopening it.
        """
        if self._dropdown is not None:
            self._dropdown.close_all()
        elif time.monotonic() - self._dropdown_closed_at > 0.2:
            self.open_dropdown()

    def show_dropdown(self, anchor, values, current, on_pick, font):
        """Open a list of `values` below `anchor`; the entry equal to `current` is marked.

        on_pick(value) is called with the chosen value. The list is at most
        popup_max_height px tall and scrolls beyond that.
        """
        font = make_font(self.popup_font) if self.popup_font else font
        entries = [
            {
                "kind": "item",
                "label": str(value),
                "current": str(value) == current,
                "invoke": lambda value=value: on_pick(value),
            }
            for value in values
        ]
        if not entries:
            return
        popup = _CanvasPopup(
            anchor,
            entries,
            font,
            self.popup_colors(),
            min_width=anchor.winfo_width(),
            max_height=self.popup_max_height,
            on_close=self._on_dropdown_closed,
        )
        self._dropdown = popup
        popup.show(
            anchor.winfo_rootx(),
            anchor.winfo_rooty() + anchor.winfo_height() + 2,
            flip_y=anchor.winfo_rooty() - 2,
        )
        self.schedule_redraw()

    def _on_dropdown_closed(self):
        """The list closed: forget it, note when (see toggle_dropdown) and redraw the
        widget (the chevron).
        """
        self._dropdown = None
        self._dropdown_closed_at = time.monotonic()
        self.schedule_redraw()

    def open_dropdown(self):
        """Open the value list (implemented by the widget)."""
        raise NotImplementedError


class OptionMenu(_DropdownOwner, CanvasWidget):
    """A drop-down button for choosing one of several values (like ttk.OptionMenu).

    Shows the variable's value, or `placeholder` while it is empty. Clicking (or
    Down/space/Return) opens a scrollable canvas-drawn list; command(value) runs
    after a pick.
    """

    ARROW_WIDTH = 28
    _COLOR_PARTS = (
        "fill_color",
        "hover_fill_color",
        "disabled_fill_color",
        "border_color",
        "hover_border_color",
        "focus_color",
        "disabled_border_color",
        "text_color",
        "disabled_text_color",
        "arrow_color",
        "disabled_arrow_color",
        "placeholder_color",
        "placeholder_fill_color",
    ) + _DropdownOwner.POPUP_COLOR_PARTS
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "placeholder",
        "variable",
        "values",
        "command",
        "radius",
        "border_width",
        "focus_border_width",
        "popup_font",
        "popup_max_height",
    )

    def __init__(
        self,
        master,
        variable=None,
        default=None,
        *values,
        command=None,
        radius=8,
        border_width=1,
        focus_border_width=2,
        popup_font=None,
        popup_max_height=260,
        placeholder="",
        theme=None,
        **kwargs,
    ):
        """Create the option menu: OptionMenu(master, variable, default, *values, ...).

        variable: the StringVar that holds the choice (one is made if None). default: the
        initially selected value (added to values if missing). command(value): after a
        pick. radius / border_width / focus_border_width: border shape. popup_font /
        popup_max_height: the list's font and the height (px) after which it scrolls.
        placeholder: text shown while nothing is chosen.
        """
        super().__init__(master, theme=theme, takefocus=True, **kwargs)
        self.placeholder = placeholder
        self.popup_font = popup_font
        self.popup_max_height = popup_max_height
        self.border_width = border_width
        self.focus_border_width = focus_border_width
        self.variable = variable if variable is not None else tk.StringVar(self)
        self.values = list(values)
        if default is not None:
            if default not in self.values:
                self.values.insert(0, default)
            self.variable.set(default)
        self.command = command
        self.radius = radius
        self._init_dropdown()
        self.watch_variable(self.variable)
        self.track_interaction()
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Down>", lambda _: self.open_dropdown(), add="+")
        self.bind("<space>", lambda _: self.toggle_dropdown(), add="+")
        self.bind("<Return>", lambda _: self.toggle_dropdown(), add="+")
        # OptionMenu sizes itself to its longest value.
        self.refit()
        self.schedule_redraw()

    def _apply_options(self, options):
        """Also (re)attach the watch when the variable option changes."""
        super()._apply_options(options)
        if "variable" in options:
            self.watch_variable(self.variable)

    def on_variable_changed(self):
        """The variable changed: redraw to show the new value."""
        self.schedule_redraw()

    def requested_size(self):
        """Wide enough for the longest value (or the placeholder), so the width does not
        jump when the value changes.
        """
        texts = [str(v) for v in self.values] + [
            str(self.variable.get()),
            self.placeholder,
        ]
        widest = max(measure_widths(self, self.font, texts))
        return widest + 24 + self.ARROW_WIDTH, self.font.metrics("linespace") + 14

    def _on_release(self, event):
        """Mouse up inside the widget: toggle the list."""
        if not self.is_disabled() and _inside(self, event):
            self.toggle_dropdown()

    def open_dropdown(self):
        """Open the value list below the button (unless disabled or already open)."""
        if self.is_disabled() or self._dropdown is not None:
            return
        self.show_dropdown(
            self, self.values, str(self.variable.get()), self.pick, self.font
        )

    def pick(self, value):
        """A value was chosen: store it in the variable and run the command."""
        self.variable.set(value)
        if self.command is not None:
            self.command(value)

    def showing_placeholder(self):
        """True while nothing is chosen (the variable is empty) and a
        placeholder was given."""
        return bool(self.placeholder) and str(self.variable.get()) == ""

    def redraw(self, width, height):
        """Draw the box (colors by state), the current value or placeholder, and the
        chevron.
        """
        disabled = self.is_disabled()
        placeholder = self.showing_placeholder()
        if disabled:
            fill = self.part("disabled_fill_color", "surface_disabled")
            border = self.part("disabled_border_color", "border")
            ow = self.border_width
        elif self._dropdown is not None or self._focused:
            fill = self.part("fill_color", "surface")
            border = self.part("focus_color", "focus_ring")
            ow = self.focus_border_width
        elif self._hovered:
            fill = self.part("hover_fill_color", "surface_hover")
            border = self.part("hover_border_color", "accent")
            ow = self.border_width
        else:
            fill = self.part("fill_color", "surface")
            border = self.part("border_color", "border")
            ow = self.border_width
        if (
            placeholder
            and not disabled
            and self._theme_overrides.get("placeholder_fill_color")
        ):
            fill = self.rc(self._theme_overrides["placeholder_fill_color"])
        self.draw_box(0, 0, width, height, fill, border, ow, self.radius)
        if placeholder:
            text_color = self.part(
                "placeholder_color", "text_disabled" if disabled else "text_muted"
            )
        else:
            text_color = self.current_text_color()
        self.create_text(
            12,
            height / 2,
            text=self.placeholder if placeholder else str(self.variable.get()),
            font=self.font,
            fill=text_color,
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )
        self.draw_chevron(
            width - self.ARROW_WIDTH / 2 - 2,
            height / 2,
            "up" if self._dropdown is not None else "down",
            (
                self.part("disabled_arrow_color", "text_disabled")
                if disabled
                else self.part("arrow_color", "text_muted")
            ),
        )


class Menu:
    """A popup menu (not a widget). Mirrors tk.Menu's add_*/insert_*/delete/
    entryconfigure/post API; submenus open as cascades."""

    COLOR_PARTS = tuple(_POPUP_COLOR_THEME_KEYS)

    def __init__(self, master=None, font=None, theme=None, tearoff=0, **options):
        """Color options (fill_color, border_color, hover_color,
        hover_text_color, text_color, disabled_text_color, muted_text_color,
        separator_color) restyle this menu's popups; others are ignored."""
        self.master = master
        self.entries = []
        self.font = font
        self._theme_overrides = starting_theme(theme)
        self.configure(**options)
        self._popup = None
        self._observers = []

    def colors_for(self, owner=None):
        """The colors this menu's popups use when shown from owner: the
        global theme, the owner window's theme, then this menu's own."""
        colors = {
            **CANVAS_WIDGET_THEME,
            **window_theme(owner),
            **self._theme_overrides,
        }
        for name, key in _POPUP_COLOR_THEME_KEYS.items():
            if self._color_options.get(name):
                colors[key] = self._color_options[name]
        return colors

    @property
    def colors(self):
        """The colors this menu uses when shown without a specific owner window."""
        return self.colors_for(None)

    def set_theme(self, theme):
        """Change theme keys for this menu only, dynamically (it takes effect
        the next time it is shown); None removes a change."""
        for key, value in expand_theme(theme, self.colors).items():
            if value is None:
                self._theme_overrides.pop(key, None)
            else:
                self._theme_overrides[key] = value

    def reset_theme(self):
        """Remove every theme change made on this menu."""
        self._theme_overrides.clear()

    def configure(self, **options):
        """Set (or, with None, reset) the menu's popup color options."""
        if not hasattr(self, "_color_options"):
            self._color_options = {}
        for name in self.COLOR_PARTS:
            if name in options:
                value = options[name]
                if value is None:
                    self._color_options.pop(name, None)
                else:
                    self._color_options[name] = value

    config = configure

    def cget(self, name):
        """The value of one of the menu's color options (None if not set)."""
        return self._color_options.get(name)

    def _get_font(self):
        """The menu's font as a Font object (made on first use, so a Menu can exist
        before a window does).
        """
        if not isinstance(self.font, tkfont.Font):
            self.font = make_font(self.font)
        return self.font

    def _insert(self, index, kind, options):
        """Add an entry of the given kind at an index ('end'/None appends) and tell
        observers (menu bars).
        """
        entry = {
            "kind": kind,
            "label": "",
            "state": "normal",
            "accelerator": "",
            **options,
        }
        position = len(self.entries) if index in (None, "end") else self.index(index)
        self.entries.insert(position, entry)
        self._notify()

    def _notify(self):
        """Call the observers (MenuBars showing this menu) so they redraw."""
        for observer in list(self._observers):
            observer()

    def add_command(self, **options):
        """Append a command entry (label, command, accelerator, state)."""
        self._insert(None, "command", options)

    def add_separator(self, **options):
        """Append a separator line."""
        self._insert(None, "separator", options)

    def add_checkbutton(self, **options):
        """Append a check entry (label, variable, onvalue, offvalue, command, ...)."""
        self._insert(None, "check", {"onvalue": 1, "offvalue": 0, **options})

    def add_radiobutton(self, **options):
        """Append a radio entry (label, variable, value, command, ...)."""
        self._insert(None, "radio", options)

    def add_cascade(self, **options):
        """Append an entry that opens `menu` as a submenu."""
        self._insert(None, "cascade", {"menu": None, **options})

    def insert_command(self, index, **options):
        """Insert a command entry before the given index."""
        self._insert(index, "command", options)

    def insert_separator(self, index, **options):
        """Insert a separator before the given index."""
        self._insert(index, "separator", options)

    def insert_checkbutton(self, index, **options):
        """Insert a check entry before the given index."""
        self._insert(index, "check", {"onvalue": 1, "offvalue": 0, **options})

    def insert_radiobutton(self, index, **options):
        """Insert a radio entry before the given index."""
        self._insert(index, "radio", options)

    def insert_cascade(self, index, **options):
        """Insert a cascade entry before the given index."""
        self._insert(index, "cascade", {"menu": None, **options})

    def index(self, index):
        """An int, 'end' (the last entry), or a label -> an entry position."""
        if isinstance(index, int):
            return index
        if index == "end":
            return len(self.entries) - 1
        for position, entry in enumerate(self.entries):
            if entry["label"] == index:
                return position
        raise ValueError(f"no menu entry {index!r}")

    def delete(self, first, last=None):
        """Delete the entries from first to last (inclusive; just one if last is None)."""
        start = self.index(first)
        stop = start if last is None else self.index(last)
        del self.entries[start : stop + 1]
        self._notify()

    def entryconfigure(self, index, **options):
        """Change options of the entry at an index (label, command, state,
        accelerator...).
        """
        self.entries[self.index(index)].update(options)
        self._notify()

    entryconfig = entryconfigure

    def entrycget(self, index, option):
        """Read one option of the entry at an index."""
        return self.entries[self.index(index)].get(option)

    def invoke(self, index):
        """Run the entry at an index as if it was chosen (unless disabled)."""
        entry = self._snapshot()[self.index(index)]
        if entry.get("invoke") and entry.get("state") != "disabled":
            entry["invoke"]()

    def _snapshot(self):
        """Entries in the form _CanvasPopup draws, with invoke callables."""
        snapshot = []
        for entry in self.entries:
            item = {
                "kind": entry["kind"],
                "label": entry["label"],
                "accelerator": entry["accelerator"],
                "state": entry["state"],
                "checked": False,
                "submenu": entry.get("menu"),
            }
            command = entry.get("command")
            variable = entry.get("variable")
            if entry["kind"] == "check":
                item["checked"] = _variable_matches(variable, entry["onvalue"])
                item["invoke"] = lambda e=entry, v=variable, c=command: (
                    v is not None
                    and v.set(
                        e["offvalue"]
                        if _variable_matches(v, e["onvalue"])
                        else e["onvalue"]
                    ),
                    c and c(),
                )
            elif entry["kind"] == "radio":
                item["checked"] = _variable_matches(variable, entry.get("value"))
                item["invoke"] = lambda e=entry, v=variable, c=command: (
                    v is not None and v.set(e.get("value")),
                    c and c(),
                )
            elif entry["kind"] == "command":
                item["invoke"] = command
            snapshot.append(item)
        return snapshot

    def post(self, x, y, owner=None, flip_y=None, on_close=None):
        """Show the menu as a popup with its top-left at screen position (x, y).

        owner: the widget it belongs to (its window's theme is used). flip_y: where to
        flip above if there is no room below. on_close: called when it closes.
        """
        # Showing a menu closes one that is already open.
        self.unpost()
        owner = owner or self.master or tk._default_root
        popup = _CanvasPopup(
            owner,
            self._snapshot(),
            self._get_font(),
            self.colors_for(owner),
            on_close=lambda: self._popup_closed(popup, on_close),
        )
        self._popup = popup
        popup.show(x, y, flip_y=flip_y)

    tk_popup = post

    def _popup_closed(self, popup, on_close):
        """The popup closed: forget it and report to whoever asked for on_close."""
        if self._popup is popup:
            self._popup = None
        if on_close is not None:
            on_close()

    def unpost(self):
        """Close the menu's popup (and submenus) if it is showing."""
        if self._popup is not None:
            self._popup.close_all()


def _variable_matches(variable, value):
    """Whether a tk variable currently equals value (BooleanVar compares truthiness; a
    missing variable never matches).
    """
    if variable is None:
        return False
    try:
        current = variable.get()
    except tk.TclError:
        return False
    if isinstance(variable, tk.BooleanVar):
        return bool(current) == bool(value)
    return str(current) == str(value)


class MenuBar(CanvasWidget):
    """A horizontal bar of the cascade entries of a Menu."""

    ITEM_PADDING = 10
    _COLOR_PARTS = (
        "hover_color",
        "open_color",
        "text_color",
        "disabled_text_color",
    )

    def __init__(self, master, menu=None, theme=None, **kwargs):
        """Create the bar; `menu` is the Menu whose cascade entries become the labels
        (can be set later with set_menu).
        """
        kwargs.setdefault("height", 32)
        kwargs.setdefault("width", 200)
        super().__init__(master, theme=theme, **kwargs)
        self.menu = None
        self._boxes = []
        self._hover_index = None
        self._open_menu = None
        self._open_index = None
        # When a menu last closed: a click on its own label that just closed it must not
        # reopen it.
        self._last_close = 0.0
        self.set_menu(menu)
        # Hover and click handling on the labels.
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")

    def set_menu(self, menu):
        """Show another Menu (or None for an empty bar): stop observing the old one and
        observe the new one.
        """
        if self.menu is not None and self.schedule_redraw in self.menu._observers:
            self.menu._observers.remove(self.schedule_redraw)
        self.menu = menu
        if menu is not None:
            menu._observers.append(self.schedule_redraw)
        self.schedule_redraw()

    def destroy(self):
        """Stop observing the menu, then destroy the widget."""
        self.set_menu(None)
        super().destroy()

    def _index_at(self, x):
        """The menu entry index of the label under an x coordinate, or None."""
        for left, right, index in self._boxes:
            if left <= x < right:
                return index
        return None

    def _on_motion(self, event):
        """Pointer moved: hover the label under it; if a menu is open, switch to the
        hovered label's menu.
        """
        index = self._index_at(event.x)
        if index != self._hover_index:
            self._hover_index = index
            self.schedule_redraw()
        if (
            self._open_menu is not None
            and index is not None
            and index != self._open_index
        ):
            self._open(index)

    def _on_leave(self, _):
        """Pointer left the bar: clear the hover."""
        self._hover_index = None
        self.schedule_redraw()

    def _on_press(self, event):
        """Click on a label: open its menu, or close it if it was the open one."""
        index = self._index_at(event.x)
        if index is None:
            return
        if self._open_index == index:
            self._close()
        elif time.monotonic() - self._last_close > 0.15:
            self._open(index)

    def _open(self, index):
        """Open the submenu of the cascade at an index just below its label (closing any
        other).
        """
        entry = self.menu.entries[index]
        if (
            entry["kind"] != "cascade"
            or entry["menu"] is None
            or entry["state"] == "disabled"
        ):
            return
        self._close()
        left = next(l for l, _, i in self._boxes if i == index)
        menu = entry["menu"]
        self._open_menu, self._open_index = menu, index
        menu.post(
            self.winfo_rootx() + left,
            self.winfo_rooty() + self.winfo_height(),
            owner=self,
            on_close=lambda: self._menu_closed(menu),
        )
        self.schedule_redraw()

    def _close(self):
        """Close the open menu, if any."""
        menu, self._open_menu, self._open_index = self._open_menu, None, None
        if menu is not None:
            menu.unpost()
        self.schedule_redraw()

    def _menu_closed(self, menu):
        """An opened menu closed: forget it and note the time (see _on_press)."""
        if self._open_menu is menu:
            self._open_menu = self._open_index = None
        self._last_close = time.monotonic()
        self.schedule_redraw()

    def redraw(self, width, height):
        """Draw the labels (with hover/open highlights) and remember where each one is
        for hit testing.
        """
        self._boxes = []
        if self.menu is None:
            return
        x = 4
        for index, entry in enumerate(self.menu.entries):
            if entry["kind"] != "cascade":
                continue
            item_width = self.font.measure(entry["label"]) + 2 * self.ITEM_PADDING
            if index == self._open_index or index == self._hover_index:
                self.draw_box(
                    x,
                    3,
                    x + item_width,
                    height - 3,
                    (
                        self.part("open_color", "accent_hover")
                        if index == self._open_index
                        else self.part("hover_color", "row_current")
                    ),
                    radius=6,
                )
            self.create_text(
                x + item_width / 2,
                height / 2,
                text=entry["label"],
                font=self.font,
                fill=(
                    self.part("disabled_text_color", "text_disabled")
                    if entry["state"] == "disabled"
                    else self.part("text_color", "text")
                ),
                tags=_CANVAS_CHROME_TAG,
            )
            self._boxes.append((x, x + item_width, index))
            x += item_width + 2


class Tooltip:
    """A hover tooltip for widget (drawn on a canvas in a borderless window)."""

    def __init__(
        self,
        widget,
        text,
        delay=500,
        theme=None,
        fill_color=None,
        border_color=None,
        text_color=None,
        font=None,
    ):
        """Attach a tooltip to `widget` showing `text` (may be several lines).

        delay: milliseconds the pointer must rest first. theme / fill_color /
        border_color / text_color / font: styling.
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.font = font
        self._theme_overrides = starting_theme(theme)
        for key, value in (
            ("tooltip", fill_color),
            ("border", border_color),
            ("text", text_color),
        ):
            if value:
                self._theme_overrides[key] = value
        self._window = None
        self._after_id = None
        self._images = []
        # add="+" keeps the widget's own bindings.
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _schedule(self, event):
        """Pointer entered the widget: show the tooltip after the delay (restarting it
        if already pending).
        """
        self.hide()
        self._after_id = self.widget.after(self.delay, lambda: self.show(event))

    def show(self, event):
        """Create the tooltip window next to the pointer, drawn with the (window)
        theme's tooltip colors.
        """
        self._after_id = None
        font = make_font(self.font, 10)
        lines = self.text.split("\n")
        width = max(font.measure(line) for line in lines) + 16
        height = len(lines) * font.metrics("linespace") + 10
        window = tk.Toplevel(self.widget)
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        colors = {
            **CANVAS_WIDGET_THEME,
            **window_theme(self.widget),
            **self._theme_overrides,
        }
        fill = resolve_color(window, colors["tooltip"])
        border = resolve_color(window, colors["border"])
        canvas = tk.Canvas(
            window, width=width, height=height, bd=0, highlightthickness=0, bg=fill
        )
        canvas.pack()
        image = rounded_box_image(width, height, 0, fill, border, 1)
        self._images = [image]
        canvas.create_image(0, 0, anchor="nw", image=image)
        canvas.create_text(
            8,
            5,
            text=self.text,
            font=font,
            anchor="nw",
            fill=resolve_color(window, colors["text"]),
        )
        x = min(event.x_root + 12, window.winfo_screenwidth() - width)
        y = min(event.y_root + 16, window.winfo_screenheight() - height)
        window.geometry(f"{width}x{height}+{x}+{y}")
        self._window = window

    def set_theme(self, theme):
        """Change theme keys for this tooltip only (used the next time it
        shows); None removes a change."""
        for key, value in theme.items():
            if value is None:
                self._theme_overrides.pop(key, None)
            else:
                self._theme_overrides[key] = value

    def hide(self, _=None):
        """Cancel a pending tooltip and destroy a showing one (also bound to
        Leave/ButtonPress/Destroy).
        """
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._window is not None:
            self._window.destroy()
            self._window = None
