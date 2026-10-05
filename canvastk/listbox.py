"""Listbox: a scrollable list of text rows drawn entirely on a canvas.

It mirrors tkinter's Listbox API (insert, delete, curselection, selection_*, see,
yview...) so it can replace one, and can draw its own scroll bar (scrolled=True).
"""

from ._core import (
    CanvasWidget,
    _CANVAS_CHROME_TAG,
)

# =============================================================================
# Listbox
# =============================================================================


class Listbox(CanvasWidget):
    # Marks the widget as scrolling itself, so a ScrolledFrame around it leaves the
    # mouse wheel to the list.
    """A list of rows with single, multiple, or extended selection.

    Only the visible rows are drawn, so long lists stay cheap. Generates
    <<ListboxSelect>> when the user changes the selection. The `contents` argument
    is the initial list of items (shown with str()).
    """

    handles_wheel = True
    # Layout constants: inner margin and the width of the built-in scroll bar, in px.
    EDGE = 4
    BAR_WIDTH = 10
    _COLOR_PARTS = (
        "scrollbar_track_color",
        "scrollbar_thumb_color",
        "scrollbar_thumb_hover_color",
        "fill_color",
        "disabled_fill_color",
        "border_color",
        "focus_color",
        "disabled_border_color",
        "text_color",
        "disabled_text_color",
        "hover_color",
        "selected_color",
        "selected_inactive_color",
        "selected_text_color",
    )
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "scrolled",
        "border_width",
        "focus_border_width",
        "row_padding",
        "row_radius",
        "width",
        "height",
        "selectmode",
        "yscrollcommand",
        "radius",
        "exportselection",
    )

    def __init__(
        self,
        master,
        contents=None,
        width=20,
        height=10,
        selectmode="browse",
        yscrollcommand=None,
        exportselection=True,
        radius=8,
        border_width=1,
        focus_border_width=2,
        row_padding=8,
        row_radius=5,
        scrolled=False,
        theme=None,
        **kwargs
    ):
        """row_padding: extra px added to the font's line height per row;
        row_radius: corner radius of the selection/hover highlight;
        scrolled: draw a scroll bar inside the box (it only shows while the
        list is longer than the box)."""
        super().__init__(master, theme=theme, takefocus=True, **kwargs)
        self.scrolled = scrolled
        self._bar_hover = False
        self._bar_drag_offset = None
        self.row_padding = row_padding
        self.row_radius = row_radius
        self.border_width = border_width
        self.focus_border_width = focus_border_width
        self.width = width
        self.height = height
        self.selectmode = selectmode
        self.yscrollcommand = yscrollcommand
        self.exportselection = exportselection
        self.radius = radius
        # State: the items, the selected row numbers, the shift-click anchor, the active
        # row, and the first visible row.
        self._items = list(contents or ())
        self._selected = set()
        self._anchor = None
        self._active = None
        self._top = 0
        self._hover_row = None
        self._last_scroll_report = None
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind_wheel(lambda direction: self.yview_scroll(direction * 3, "units"))
        # Keyboard navigation.
        self.bind("<Up>", lambda e: self._key_move(-1, e), add="+")
        self.bind("<Down>", lambda e: self._key_move(1, e), add="+")
        self.bind(
            "<Prior>", lambda e: self._key_move(-self._visible_rows(), e), add="+"
        )
        self.bind("<Next>", lambda e: self._key_move(self._visible_rows(), e), add="+")
        self.bind("<Home>", lambda e: self._key_move(-len(self._items), e), add="+")
        self.bind("<End>", lambda e: self._key_move(len(self._items), e), add="+")
        self.refit()
        self.schedule_redraw()

    # ---- sizing ------------------------------------------------------------
    def _row_height(self):
        """The height of one row: the font's line height plus row_padding."""
        return self.font.metrics("linespace") + self.row_padding

    def requested_size(self):
        """The size for `width` characters by `height` rows (plus the built-in scroll
        bar if any).
        """
        return (
            self.width * self.font.measure("0")
            + 2 * self.EDGE
            + 8
            + (self.BAR_WIDTH + 4 if self.scrolled else 0),
            self.height * self._row_height() + 2 * self.EDGE,
        )

    def _apply_options(self, options):
        """A new width/height (in characters/rows) lets the widget size itself again."""
        if "width" in options or "height" in options:
            self._fixed_width = self._fixed_height = False
        super()._apply_options(options)

    def _visible_rows(self):
        """How many rows fit in the widget's current height (at least 1)."""
        return max(1, (self.winfo_height() - 2 * self.EDGE) // self._row_height())

    # ---- index helpers --------------------------------------------------------
    def _index(self, index, allow_end=False):
        """Turn a tkinter index ('end', 'active', 'anchor', or a number) into a row
        number.
        """
        if index == "end":
            return len(self._items) if allow_end else len(self._items) - 1
        if index == "active":
            return self._active or 0
        if index == "anchor":
            return self._anchor or 0
        return int(index)

    def size(self):
        """The number of items."""
        return len(self._items)

    def index(self, index):
        """A row number for a tkinter index ('end' gives the item count)."""
        return self._index(index, allow_end=True)

    def get(self, first, last=None):
        """The item at an index, or a tuple of the items between two indices
        (inclusive).
        """
        if last is None:
            return self._items[self._index(first)]
        return tuple(self._items[self._index(first) : self._index(last) + 1])

    def insert(self, index, *items):
        """Insert items before an index ('end' appends); the selection moves along with
        the rows.
        """
        position = min(self._index(index, allow_end=True), len(self._items))
        self._items[position:position] = items
        self._selected = {
            i + len(items) if i >= position else i for i in self._selected
        }
        self.schedule_redraw()

    def delete(self, first, last=None):
        """Delete the items from first to last (inclusive; just one if last is None),
        fixing up the selection.
        """
        start = self._index(first)
        stop = start if last is None else self._index(last)
        stop = min(stop, len(self._items) - 1)
        if start > stop or start < 0:
            return
        count = stop - start + 1
        del self._items[start : stop + 1]
        self._selected = {
            i - count if i > stop else i
            for i in self._selected
            if not start <= i <= stop
        }
        self._top = min(self._top, max(0, len(self._items) - 1))
        self.schedule_redraw()

    def curselection(self):
        """The selected row numbers as a sorted tuple."""
        return tuple(sorted(self._selected))

    def selection_set(self, first, last=None):
        """Select the rows first..last; in browse/single mode only the last one stays
        selected.
        """
        start = self._index(first)
        stop = start if last is None else self._index(last)
        if self.selectmode in ("browse", "single"):
            self._selected = {stop}
        else:
            self._selected.update(range(start, stop + 1))
        self.schedule_redraw()

    def selection_clear(self, first, last=None):
        """Deselect the rows first..last."""
        start = self._index(first)
        stop = start if last is None else self._index(last)
        self._selected.difference_update(range(start, stop + 1))
        self.schedule_redraw()

    def selection_includes(self, index):
        """Whether the row at the index is selected."""
        return self._index(index) in self._selected

    def selection_anchor(self, index):
        """Set the anchor row that shift-click ranges start from."""
        self._anchor = self._index(index)

    select_set = selection_set
    select_clear = selection_clear
    select_includes = selection_includes
    select_anchor = selection_anchor

    def activate(self, index):
        """Make the row at the index the 'active' one (the keyboard cursor)."""
        self._active = self._index(index)
        self.schedule_redraw()

    def nearest(self, y):
        # Row under y: offset inside the widget, in rows, plus the scrolled-off rows
        # above.
        """The row closest to a y coordinate in the widget (clamped to existing rows)."""
        row = int((y - self.EDGE) // self._row_height()) + self._top
        return min(max(row, 0), max(len(self._items) - 1, 0))

    def see(self, index):
        """Scroll just enough to bring the row at the index into view."""
        index = self._index(index)
        visible = self._visible_rows()
        if index < self._top:
            self._top = index
        elif index >= self._top + visible:
            self._top = index - visible + 1
        self.schedule_redraw()

    # ---- scrolling ---------------------------------------------------------------
    def yview(self, *arguments):
        """tkinter's yview: with no arguments the visible fractions; ('moveto', f) or
        ('scroll', n, what) scroll.
        """
        if not arguments:
            return self._scroll_fractions()
        if arguments[0] == "moveto":
            self.yview_moveto(float(arguments[1]))
        elif arguments[0] == "scroll":
            self.yview_scroll(int(arguments[1]), arguments[2])
        return None

    def _scroll_fractions(self):
        """(first, last) fractions of the list that are visible, as a scroll bar wants
        them.
        """
        count = max(len(self._items), 1)
        visible = self._visible_rows()
        return self._top / count, min(1.0, (self._top + visible) / count)

    def yview_moveto(self, fraction):
        """Scroll so the given fraction (0..1) of the list is at the top."""
        self._top = self._clamp_top(round(fraction * len(self._items)))
        self.schedule_redraw()

    def yview_scroll(self, number, what):
        """Scroll by `number` rows, or pages if `what` starts with 'page'."""
        amount = number * (self._visible_rows() if what.startswith("page") else 1)
        self._top = self._clamp_top(self._top + amount)
        self.schedule_redraw()

    def _clamp_top(self, top):
        """Keep the first visible row inside the range that fills the widget."""
        return min(max(top, 0), max(0, len(self._items) - self._visible_rows()))

    # ---- interaction ---------------------------------------------------------------
    def _notify_selection(self):
        """Tell listeners that the user changed the selection."""
        self.event_generate("<<ListboxSelect>>")

    def _row_at(self, y):
        """The row under a y coordinate, or None if the pointer is not over a row."""
        row = int((y - self.EDGE) // self._row_height()) + self._top
        return row if 0 <= row < len(self._items) else None

    def _on_leave(self, _):
        """Pointer left the widget: clear the row and scroll bar hover highlights."""
        self._set_hover_row(None)
        self._set_bar_hover(False)

    def _set_hover_row(self, row):
        """Remember which row is hovered (redraws only when it changes)."""
        if row != self._hover_row:
            self._hover_row = row
            self.schedule_redraw()

    # ---- built-in scroll bar ---------------------------------------------------
    def _bar_visible(self):
        """Whether the built-in scroll bar is shown (scrolled, and the list is longer
        than the box).
        """
        return self.scrolled and len(self._items) > self._visible_rows()

    def _bar_left(self):
        """The x coordinate of the built-in scroll bar's left edge."""
        return self.winfo_width() - self.EDGE - self.BAR_WIDTH

    def _over_bar(self, x):
        """Whether an x coordinate is over the built-in scroll bar."""
        return self._bar_visible() and x >= self._bar_left() - 2

    def _bar_thumb(self):
        """(top, height) of the thumb in pixels."""
        track = self.winfo_height() - 2 * self.EDGE
        visible = self._visible_rows()
        count = len(self._items)
        height = min(track, max(20, track * visible / count))
        hidden = count - visible
        top = self.EDGE + ((track - height) * self._top / hidden if hidden else 0)
        return top, height

    def _set_bar_hover(self, value):
        """Remember whether the pointer is over the scroll bar (redraws only when it
        changes).
        """
        if value != self._bar_hover:
            self._bar_hover = value
            self.schedule_redraw()

    def _press_bar(self, event):
        """Mouse down on the scroll bar: grab the thumb, or page towards the click."""
        top, height = self._bar_thumb()
        if top <= event.y <= top + height:
            self._bar_drag_offset = event.y - top
            self.schedule_redraw()
        else:
            self.yview_scroll(1 if event.y > top else -1, "pages")

    def _drag_bar(self, event):
        """Dragging the scroll bar thumb: scroll to the row that matches its position."""
        _, height = self._bar_thumb()
        movable = self.winfo_height() - 2 * self.EDGE - height
        hidden = len(self._items) - self._visible_rows()
        if movable <= 0 or hidden <= 0:
            return
        fraction = (event.y - self._bar_drag_offset - self.EDGE) / movable
        self._top = round(min(max(fraction, 0), 1) * hidden)
        self.schedule_redraw()

    def _on_release(self, _):
        """Mouse up: let go of the scroll bar thumb."""
        if self._bar_drag_offset is not None:
            self._bar_drag_offset = None
            self.schedule_redraw()

    def _on_motion(self, event):
        """Pointer moved: update the hovered row and the scroll bar hover."""
        over_bar = self._over_bar(event.x)
        self._set_bar_hover(over_bar)
        self._set_hover_row(None if over_bar else self._row_at(event.y))

    def _on_press(self, event):
        """Mouse down: focus the list, then either use the scroll bar or select a row.

        browse/single select one row; multiple toggles; extended handles Ctrl-click
        (toggle) and Shift-click (range from the anchor).
        """
        self.focus_set()
        if self.is_disabled():
            return
        if self._over_bar(event.x):
            self._press_bar(event)
            return
        row = self._row_at(event.y)
        if row is None:
            return
        mode = self.selectmode
        if mode in ("browse", "single"):
            self._selected = {row}
        elif mode == "multiple" or (mode == "extended" and event.state & 0x4):
            self._selected ^= {row}
        elif mode == "extended" and event.state & 0x1 and self._anchor is not None:
            low, high = sorted((self._anchor, row))
            self._selected = set(range(low, high + 1))
        else:
            self._selected = {row}
        if not (mode == "extended" and event.state & 0x1):
            self._anchor = row
        self._active = row
        self.schedule_redraw()
        self._notify_selection()

    def _on_drag(self, event):
        """Mouse moved with the button down: drag the scroll bar, or extend/move the
        selection (browse and extended).
        """
        if self._bar_drag_offset is not None:
            self._drag_bar(event)
            return
        if self.is_disabled() or self.selectmode not in ("browse", "extended"):
            return
        row = self.nearest(event.y)
        if not self._items:
            return
        if self.selectmode == "browse":
            if self._selected != {row}:
                self._selected = {row}
                self._active = row
                self.see(row)
                self._notify_selection()
        elif self._anchor is not None:
            low, high = sorted((self._anchor, row))
            self._selected = set(range(low, high + 1))
            self.see(row)
            self._notify_selection()

    def _key_move(self, step, event):
        """Up/Down/Page/Home/End: move the active row (and the selection unless Ctrl is
        held in multi modes).
        """
        if not self._items or self.is_disabled():
            return "break"
        current = self._active if self._active is not None else (-1 if step > 0 else 0)
        row = min(max(current + step, 0), len(self._items) - 1)
        self._active = row
        if self.selectmode in ("browse", "single") or not event.state & 0x4:
            self._selected = {row}
            self._anchor = row
            self._notify_selection()
        self.see(row)
        return "break"

    # ---- drawing -------------------------------------------------------------------
    def redraw(self, width, height):
        """Draw the box, the visible rows (with selection/hover highlights), and the scroll bar.

        Also reports the visible fractions to yscrollcommand when they changed, so an
        external scroll bar stays in sync.
        """
        disabled = self.is_disabled()
        if disabled:
            border = self.part("disabled_border_color", "border")
            border_width = self.border_width
        elif self._focused:
            border = self.part("focus_color", "focus_ring")
            border_width = self.focus_border_width
        else:
            border = self.part("border_color", "border")
            border_width = self.border_width
        self.draw_box(
            0,
            0,
            width,
            height,
            (
                self.part("disabled_fill_color", "surface_disabled")
                if disabled
                else self.part("fill_color", "surface")
            ),
            border,
            border_width,
            self.radius,
        )
        row_height = self._row_height()
        self._top = self._clamp_top(self._top)
        right = width - self.EDGE - (self.BAR_WIDTH + 4 if self._bar_visible() else 0)
        # Draw only the rows that can be seen (one extra for a partly visible row at the
        # bottom).
        for offset in range(self._visible_rows() + 1):
            row = self._top + offset
            if row >= len(self._items):
                break
            top = self.EDGE + offset * row_height
            if top + row_height > height - self.EDGE + row_height / 2:
                break
            selected = row in self._selected
            if selected:
                fill = (
                    self.part("selected_color", "accent_hover")
                    if self._focused
                    else self.part("selected_inactive_color", "row_current")
                )
                self.draw_box(
                    self.EDGE,
                    top,
                    right,
                    top + row_height,
                    fill,
                    radius=self.row_radius,
                )
            elif row == self._hover_row and not disabled:
                self.draw_box(
                    self.EDGE,
                    top,
                    right,
                    top + row_height,
                    self.part("hover_color", "surface_hover"),
                    radius=self.row_radius,
                )
            if disabled:
                color = self.part("disabled_text_color", "text_disabled")
            elif selected and self._focused:
                color = self.part("selected_text_color", "accent_text")
            else:
                color = self.current_text_color()
            self.create_text(
                self.EDGE + 8,
                top + row_height / 2,
                text=str(self._items[row]),
                font=self.font,
                fill=color,
                anchor="w",
                tags=_CANVAS_CHROME_TAG,
            )
        if self._bar_visible():
            bar_left = self._bar_left()
            self.draw_box(
                bar_left,
                self.EDGE,
                bar_left + self.BAR_WIDTH,
                height - self.EDGE,
                self.part("scrollbar_track_color", "track"),
                radius=self.BAR_WIDTH / 2,
            )
            thumb_top, thumb_height = self._bar_thumb()
            if self.is_disabled():
                thumb = self.part("scrollbar_track_color", "track")
            elif self._bar_hover or self._bar_drag_offset is not None:
                thumb = self.part("scrollbar_thumb_hover_color", "thumb_hover")
            else:
                thumb = self.part("scrollbar_thumb_color", "thumb")
            self.draw_box(
                bar_left + 1,
                thumb_top,
                bar_left + self.BAR_WIDTH - 1,
                thumb_top + thumb_height,
                thumb,
                radius=(self.BAR_WIDTH - 2) / 2,
            )
        # Tell a connected scroll bar what is visible now (only when it changed).
        fractions = self._scroll_fractions()
        if fractions != self._last_scroll_report:
            self._last_scroll_report = fractions
            if self.yscrollcommand is not None:
                self.yscrollcommand(*fractions)
