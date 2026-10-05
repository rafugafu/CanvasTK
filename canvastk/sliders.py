"""Scale, Progressbar, Scrollbar, and Separator: the track-and-thumb widgets.

Scale and Progressbar share _Slider's geometry (a rounded track along one axis);
Scrollbar speaks tkinter's scrollbar protocol (set() / command()).
"""

import tkinter as tk

from ._core import (
    CanvasWidget,
    _CANVAS_CHROME_TAG,
)

# =============================================================================
# Scale / Progressbar / Scrollbar / Separator
# =============================================================================


class _Slider(CanvasWidget):
    """Geometry shared by Scale and Progressbar: a rounded track along one
    axis, with fractions mapped to pixel positions."""

    END_PADDING = 2

    def axis_geometry(self, width, height):
        """(start, end, cross_center) along the widget's main axis."""
        if self.orient == "horizontal":
            return self.END_PADDING, width - self.END_PADDING, height / 2
        return self.END_PADDING, height - self.END_PADDING, width / 2

    def box_on_axis(self, start, end, cross_center, thickness):
        """The bounding box (x1, y1, x2, y2) of a bar `thickness` thick from `start` to
        `end` along the axis.
        """
        half = thickness / 2
        if self.orient == "horizontal":
            return start, cross_center - half, end, cross_center + half
        return cross_center - half, start, cross_center + half, end


class Scale(_Slider):
    """A slider for choosing a number between from_ and to.

    Click or drag the track/thumb, use the wheel, the arrow keys, Home, and End.
    The value lives in a tk variable (a DoubleVar is made if none is given);
    resolution snaps it to steps; command(value) is called when it changes.
    """

    END_PADDING = 10
    _COLOR_PARTS = (
        "track_color",
        "progress_color",
        "disabled_progress_color",
        "thumb_color",
        "thumb_hover_color",
        "disabled_thumb_color",
        "thumb_border_color",
        "thumb_hover_border_color",
        "disabled_thumb_border_color",
        "focus_color",
    )
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "track_thickness",
        "thumb_size",
        "from_",
        "to",
        "variable",
        "command",
        "orient",
        "resolution",
    )

    def __init__(
        self,
        master,
        from_=0,
        to=100,
        orient="horizontal",
        variable=None,
        command=None,
        resolution=0,
        length=160,
        value=None,
        track_thickness=6,
        thumb_size=18,
        theme=None,
        **kwargs
    ):
        """Create the slider.

        from_ / to: the range (to may be smaller than from_). orient: 'horizontal' or
        'vertical'. variable / value: the value's tk variable and an initial value.
        command: called with the new value when it changes. resolution: step size (0 =
        continuous). length: size along the main axis in px. track_thickness /
        thumb_size: sizes in px.
        """
        horizontal = orient == "horizontal"
        kwargs.setdefault("width", length if horizontal else max(28, thumb_size + 10))
        kwargs.setdefault("height", max(28, thumb_size + 10) if horizontal else length)
        super().__init__(master, theme=theme, takefocus=True, **kwargs)
        self.track_thickness = track_thickness
        self.thumb_size = thumb_size
        self.from_ = from_
        self.to = to
        self.orient = orient
        self.command = command
        self.resolution = resolution
        self.variable = (
            variable if variable is not None else tk.DoubleVar(self, value=from_)
        )
        self.watch_variable(self.variable)
        if value is not None:
            self.variable.set(self._snap(value))
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        # Wheel up raises the value (the wheel direction is +1 for down).
        self.bind_wheel(lambda direction: self._nudge(-direction))
        # Arrow keys: left/down decrease, right/up increase.
        for sequence, direction in (
            ("<Left>", -1),
            ("<Down>", -1),
            ("<Right>", 1),
            ("<Up>", 1),
        ):
            self.bind(sequence, lambda _, d=direction: self._nudge(d), add="+")
        self.bind("<Home>", lambda _: self.set(self.from_), add="+")
        self.bind("<End>", lambda _: self.set(self.to), add="+")
        self.schedule_redraw()

    def _apply_options(self, options):
        """Also (re)attach the watch when the variable option changes."""
        super()._apply_options(options)
        if "variable" in options:
            self.watch_variable(self.variable)

    def _snap(self, value):
        """Clamp value into the range and round it to the resolution."""
        low, high = sorted((self.from_, self.to))
        value = min(max(float(value), low), high)
        # Snap to the nearest multiple of the resolution, measured from the low end of
        # the range.
        if self.resolution:
            value = round((value - low) / self.resolution) * self.resolution + low
            value = min(max(value, low), high)
        return round(value, 10)

    def get(self):
        """The current value as a float (from_ if the variable holds nothing usable)."""
        try:
            return float(self.variable.get())
        except (tk.TclError, ValueError):
            return float(self.from_)

    def set(self, value):
        """Set the value (clamped and snapped); runs the command if it actually changed."""
        value = self._snap(value)
        if value != self.get():
            self.variable.set(value)
            if self.command is not None:
                self.command(value)

    def _nudge(self, direction):
        """Move one step (a resolution, or 1/20 of the range) in a direction (+1/-1),
        e.g. for the arrow keys.
        """
        if self.is_disabled():
            return
        step = self.resolution or (self.to - self.from_) / 20
        self.set(self.get() + direction * step * (1 if self.to >= self.from_ else -1))

    def _fraction(self):
        """The value as a position 0..1 along the range."""
        span = self.to - self.from_
        return 0 if span == 0 else (self.get() - self.from_) / span

    def _set_from_pointer(self, event):
        """Set the value from the mouse position projected onto the track."""
        start, end, _ = self.axis_geometry(self.winfo_width(), self.winfo_height())
        position = event.x if self.orient == "horizontal" else event.y
        fraction = min(max((position - start) / max(end - start, 1), 0), 1)
        self.set(self.from_ + fraction * (self.to - self.from_))

    def _on_press(self, event):
        """Mouse down: start dragging and jump the thumb to the pointer."""
        if not self.is_disabled():
            self._pressed = True
            self._set_from_pointer(event)
            self.schedule_redraw()

    def _on_drag(self, event):
        """Mouse moved with the button down: follow the pointer."""
        if self._pressed:
            self._set_from_pointer(event)

    def _on_release(self, _):
        """Mouse up: stop dragging."""
        self._pressed = False
        self.schedule_redraw()

    def redraw(self, width, height):
        """Draw the track, the filled part up to the thumb, and the round thumb (colors
        by state).
        """
        start, end, cross = self.axis_geometry(width, height)
        thickness = self.track_thickness
        disabled = self.is_disabled()
        x1, y1, x2, y2 = self.box_on_axis(start, end, cross, thickness)
        self.draw_box(
            x1, y1, x2, y2, self.part("track_color", "track"), radius=thickness / 2
        )
        # The thumb's position along the track; the filled part runs from the start to
        # it.
        thumb = start + self._fraction() * (end - start)
        if thumb - start >= 2:
            fx1, fy1, fx2, fy2 = self.box_on_axis(start, thumb, cross, thickness)
            if disabled:
                fill = self.part("disabled_progress_color", "text_disabled")
            else:
                fill = self.part("progress_color", "accent")
            self.draw_box(fx1, fy1, fx2, fy2, fill, radius=thickness / 2)
        half = self.thumb_size / 2
        if self.orient == "horizontal":
            box = (thumb - half, cross - half, thumb + half, cross + half)
        else:
            box = (cross - half, thumb - half, cross + half, thumb + half)
        if disabled:
            outline = self.part("disabled_thumb_border_color", "border")
            fill = self.part("disabled_thumb_color", "surface_disabled")
        elif self._focused:
            outline = self.part("focus_color", "focus_ring")
            fill = self.part("thumb_color", "surface")
        elif self._hovered or self._pressed:
            outline = self.part("thumb_hover_border_color", "accent")
            fill = self.part("thumb_hover_color", "accent_hover")
        else:
            outline = self.part("thumb_border_color", "accent")
            fill = self.part("thumb_color", "surface")
        self.draw_box(*box, fill, outline, 2, half)


class Progressbar(_Slider):
    """A progress bar: determinate (value / maximum) or an animated indeterminate bar.

    value can be read and assigned, or driven by a tk variable; start() / stop()
    run the indeterminate animation and step() advances the value.
    """

    _COLOR_PARTS = ("track_color", "progress_color")
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "track_thickness",
        "orient",
        "mode",
        "maximum",
        "value",
        "variable",
    )

    def __init__(
        self,
        master,
        orient="horizontal",
        length=200,
        mode="determinate",
        maximum=100,
        value=0,
        variable=None,
        track_thickness=10,
        theme=None,
        **kwargs
    ):
        """Create the bar.

        orient / length / track_thickness: shape and size. mode: 'determinate' or
        'indeterminate'. maximum: the value that fills the bar. value / variable: the
        current value or the tk variable that holds it.
        """
        horizontal = orient == "horizontal"
        kwargs.setdefault("width", length if horizontal else track_thickness + 4)
        kwargs.setdefault("height", track_thickness + 4 if horizontal else length)
        super().__init__(master, theme=theme, **kwargs)
        self.track_thickness = track_thickness
        self.orient = orient
        self.mode = mode
        self.maximum = maximum
        self._value = value
        self.variable = variable
        self._phase = 0.0
        self._animation_id = None
        self.watch_variable(variable)
        self.schedule_redraw()

    def _apply_options(self, options):
        """Also (re)attach the watch when the variable option changes."""
        super()._apply_options(options)
        if "variable" in options:
            self.watch_variable(self.variable)

    @property
    def value(self):
        """The current value: the variable's if there is one (0.0 if unusable), else the
        stored one.
        """
        if self.variable is not None:
            try:
                return float(self.variable.get())
            except (tk.TclError, ValueError):
                return 0.0
        return self._value

    @value.setter
    def value(self, new_value):
        """Set the value, writing it through to the tk variable if there is one."""
        if self.variable is not None:
            self.variable.set(new_value)
        self._value = new_value

    def step(self, amount=1):
        """Add `amount` to the value, wrapping back to 0 at the maximum."""
        self.configure(value=(self.value + amount) % (self.maximum or 1))

    def start(self, interval=15):
        """Switch to the indeterminate mode and animate it (one frame every `interval`
        ms).
        """
        self.mode = "indeterminate"
        self.stop()
        self._animate(interval)

    def stop(self):
        """Stop the indeterminate animation."""
        self.cancel_call(self._animation_id)
        self._animation_id = None

    def _animate(self, interval):
        # Animation phase 0..2: the first half moves the chunk forward, the second half
        # back.
        """Advance the animation one frame and schedule the next."""
        self._phase = (self._phase + 1 / 70) % 2
        self.schedule_redraw()
        self._animation_id = self.call_later(interval, lambda: self._animate(interval))

    def redraw(self, width, height):
        """Draw the track and either the filled part (determinate) or the bouncing chunk
        (indeterminate).
        """
        start, end, cross = self.axis_geometry(width, height)
        thickness = self.track_thickness
        x1, y1, x2, y2 = self.box_on_axis(start, end, cross, thickness)
        self.draw_box(
            x1, y1, x2, y2, self.part("track_color", "track"), radius=thickness / 2
        )
        length = end - start
        if self.mode == "indeterminate":
            # Indeterminate: a chunk 30% of the bar long bounces from end to end.
            chunk = length * 0.3
            fraction = self._phase if self._phase <= 1 else 2 - self._phase
            chunk_start = start + fraction * (length - chunk)
            chunk_end = chunk_start + chunk
        else:
            fraction = min(max(self.value / (self.maximum or 1), 0), 1)
            chunk_start, chunk_end = start, start + fraction * length
        if chunk_end - chunk_start >= 2:
            fx1, fy1, fx2, fy2 = self.box_on_axis(
                chunk_start, chunk_end, cross, thickness
            )
            self.draw_box(
                fx1,
                fy1,
                fx2,
                fy2,
                self.part("progress_color", "accent"),
                radius=thickness / 2,
            )


class Scrollbar(CanvasWidget):
    """A scroll bar that works like tkinter's: connect it with command= and set().

    The thumb shows first..last (fractions of the content); dragging it calls
    command('moveto', fraction), clicking the track pages, the wheel scrolls. With
    autohide it draws nothing while the whole content is visible.
    """

    MINIMUM_THUMB_LENGTH = 24
    _COLOR_PARTS = (
        "track_color",
        "thumb_color",
        "thumb_hover_color",
        "disabled_thumb_color",
    )
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "orient",
        "command",
        "autohide",
        "thickness",
    )

    def __init__(
        self,
        master,
        orient="vertical",
        command=None,
        autohide=False,
        thickness=14,
        theme=None,
        **kwargs
    ):
        """Create the bar; orient 'vertical'/'horizontal', command: the scrolled
        widget's xview/yview, thickness: width in px.
        """
        vertical = orient == "vertical"
        kwargs.setdefault("width", thickness if vertical else 50)
        kwargs.setdefault("height", 50 if vertical else thickness)
        super().__init__(master, theme=theme, **kwargs)
        self.orient = orient
        self.command = command
        self.autohide = autohide
        self.thickness = thickness
        self._first = 0.0
        self._last = 1.0
        self._drag_offset = None
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind_wheel(lambda direction: self._send("scroll", direction * 3, "units"))
        self.schedule_redraw()

    def set(self, first, last):
        """The yscrollcommand/xscrollcommand target."""
        first, last = float(first), float(last)
        if (first, last) != (self._first, self._last):
            self._first, self._last = first, last
            self.schedule_redraw()

    def get(self):
        """The (first, last) fractions last given to set()."""
        return self._first, self._last

    def _send(self, *arguments):
        """Call the scroll command with the arguments (unless disabled)."""
        if self.command is not None and not self.is_disabled():
            self.command(*arguments)

    def _track_length(self):
        """The length of the track in px (the widget's height or width)."""
        return self.winfo_height() if self.orient == "vertical" else self.winfo_width()

    def _thumb_span(self):
        """(thumb_start, thumb_length) in pixels along the track."""
        track = self._track_length()
        visible = self._last - self._first
        length = min(track, max(self.MINIMUM_THUMB_LENGTH, visible * track))
        denominator = 1 - visible
        # Map the scrolled fraction onto the free track, keeping a minimum thumb length.
        start = (self._first / denominator) * (track - length) if denominator > 0 else 0
        return start, length

    def _on_press(self, event):
        """Mouse down: grab the thumb if the pointer is on it, otherwise page towards
        the pointer.
        """
        position = event.y if self.orient == "vertical" else event.x
        start, length = self._thumb_span()
        if start <= position <= start + length:
            self._drag_offset = position - start
            self._pressed = True
            self.schedule_redraw()
        else:
            self._send("scroll", 1 if position > start else -1, "pages")

    def _on_drag(self, event):
        """Mouse moved while dragging the thumb: ask the scrolled widget to move to the
        matching fraction.
        """
        if self._drag_offset is None:
            return
        position = event.y if self.orient == "vertical" else event.x
        track = self._track_length()
        _, length = self._thumb_span()
        movable = track - length
        denominator = 1 - (self._last - self._first)
        if movable <= 0 or denominator <= 0:
            return
        # Thumb position as a fraction of the movable track, converted to the content's
        # 'first' fraction.
        fraction = min(max((position - self._drag_offset) / movable, 0), 1)
        self._send("moveto", fraction * denominator)

    def _on_release(self, _):
        """Mouse up: let go of the thumb."""
        self._drag_offset = None
        self._pressed = False
        self.schedule_redraw()

    def redraw(self, width, height):
        """Draw the track and the thumb (nothing at all when autohide and everything is
        visible).
        """
        if self.autohide and self._first <= 0 and self._last >= 1:
            return
        vertical = self.orient == "vertical"
        radius = (width if vertical else height) / 2
        self.draw_box(
            0, 0, width, height, self.part("track_color", "track"), radius=radius
        )
        start, length = self._thumb_span()
        inset = 2
        if self.is_disabled():
            fill = self.part("disabled_thumb_color", "track")
        elif self._pressed or self._hovered:
            fill = self.part("thumb_hover_color", "thumb_hover")
        else:
            fill = self.part("thumb_color", "thumb")
        if vertical:
            box = (inset, start + inset, width - inset, start + length - inset)
        else:
            box = (start + inset, inset, start + length - inset, height - inset)
        self.draw_box(*box, fill, radius=radius)


class Separator(CanvasWidget):
    """A thin line, horizontal or vertical, in the theme's separator color."""

    _COLOR_PARTS = ("color",)

    def __init__(self, master, orient="horizontal", thickness=1, theme=None, **kwargs):
        """Create the line; orient 'horizontal'/'vertical', thickness in px. Pack it
        with fill='x' or 'y'.
        """
        horizontal = orient == "horizontal"
        kwargs.setdefault("width", 100 if horizontal else thickness + 4)
        kwargs.setdefault("height", thickness + 4 if horizontal else 100)
        super().__init__(master, theme=theme, **kwargs)
        self.orient = orient
        self.thickness = thickness
        self.schedule_redraw()

    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + ("orient", "thickness")

    def redraw(self, width, height):
        """Draw one rectangle across the middle of the widget."""
        half = self.thickness / 2
        if self.orient == "horizontal":
            box = (0, height / 2 - half, width, height / 2 + half)
        else:
            box = (width / 2 - half, 0, width / 2 + half, height)
        self.create_rectangle(
            *box, fill=self.part("color", "separator"), width=0, tags=_CANVAS_CHROME_TAG
        )
