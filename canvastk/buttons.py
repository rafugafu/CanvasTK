"""Button, Label, Checkbutton, and Radiobutton: the simple canvas-drawn widgets.

Each draws itself with CanvasWidget.draw_box / draw_content, takes every color
as a named option (see _COLOR_PARTS) and follows the theme.
"""

import tkinter as tk

from ._core import (
    CanvasWidget,
    hover_variant,
    _CANVAS_CHROME_TAG,
    _inside,
    measure_content,
)

# =============================================================================
# Button / Label / Checkbutton / Radiobutton
# =============================================================================


class Button(CanvasWidget):
    """A rounded push button.

    Colors default to the theme's accent (None = "use the theme"); give
    default_bg / hover_bg / press_bg and the matching *_fg to restyle it. The
    command runs when the mouse is released over the button, or on Return/space
    while it has the keyboard focus. While pressed it shrinks by press_shrink px.
    """

    _COLOR_PARTS = ("focus_color", "disabled_border_color")
    DEFAULT_FONT_WEIGHT = "bold"
    DEFAULT_FONT_SIZE = 12
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "text",
        "command",
        "image",
        "default_bg",
        "hover_bg",
        "press_bg",
        "default_fg",
        "hover_fg",
        "press_fg",
        "disabled_bg",
        "disabled_fg",
        "border_width",
        "border_color",
        "radius",
        "press_shrink",
        "padx",
        "pady",
    )

    def __init__(
        self,
        master,
        text="",
        command=None,
        default_bg=None,
        hover_bg=None,
        default_fg=None,
        hover_fg=None,
        press_bg=None,
        press_fg=None,
        disabled_bg=None,
        disabled_fg=None,
        border_width=1,
        border_color=None,
        radius=15,
        press_shrink=2,
        image=None,
        padx=13,
        pady=8,
        theme=None,
        **kwargs
    ):
        """Create the button.

        text / image: its content. command: called with no arguments on click.
        default_bg, hover_bg, press_bg, default_fg, hover_fg, press_fg, disabled_bg,
        disabled_fg, border_color: colors (None = from the theme; a
        default_bg without hover_bg gets a derived hover color). border_width: the
        outline width in px (1 by default). radius: corner radius
        (15 by default). press_shrink: px the box shrinks while pressed. padx / pady:
        space around the content.
        """
        super().__init__(master, theme=theme, takefocus=True, **kwargs)
        self.text = text
        self.command = command
        self.image = image
        # None means "use the current theme's color" (resolved when drawing).
        self.default_bg = default_bg
        self.hover_bg = hover_bg
        self.press_bg = press_bg
        self.default_fg = default_fg
        self.hover_fg = hover_fg
        self.press_fg = press_fg
        self.disabled_bg = disabled_bg
        self.disabled_fg = disabled_fg
        self.border_width = border_width
        self.border_color = border_color
        self.radius = radius
        self.press_shrink = press_shrink
        self.padx = padx
        self.pady = pady
        # True for a moment after invoke(): shows the pressed look for keyboard clicks.
        self._flashing = False
        self.track_interaction()
        # Click handling: pressed on mouse down, command on release inside the widget.
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Return>", lambda _: self.invoke(), add="+")
        self.bind("<space>", lambda _: self.invoke(), add="+")
        self.refit()
        self.schedule_redraw()

    def requested_size(self):
        """The size that fits the text/image plus padx/pady on each side."""
        width, height = measure_content(self.text, self.image, self.font)
        return width + 2 * self.padx, height + 2 * self.pady

    def _on_press(self, _):
        """Mouse button went down: remember it so the redraw shows the pressed look."""
        if not self.is_disabled():
            self._pressed = True
            self.schedule_redraw()

    def _on_release(self, event):
        """Mouse button came up: run the command if the pointer is still over the
        button.
        """
        was_pressed = self._pressed
        self._pressed = False
        self.schedule_redraw()
        if was_pressed and _inside(self, event):
            self.invoke(flash=False)

    def invoke(self, flash=True):
        """Run the command (briefly showing the pressed look if flash)."""
        if self.is_disabled():
            return None
        if flash:
            self._flashing = True
            self.schedule_redraw()
            self.call_later(120, self._end_flash)
        if self.command is not None:
            return self.command()
        return None

    def _end_flash(self):
        """Stop showing the pressed look after a keyboard/programmatic invoke()."""
        self._flashing = False
        self.schedule_redraw()

    def redraw(self, width, height):
        """Draw the box in the state's colors (disabled, pressed, hovered, normal) and its content.

        Unset colors come from the theme; a custom default_bg derives its hover color
        with hover_variant() so the hover is always visible. Keyboard focus draws a
        thicker border in the focus color.
        """
        colors = self.colors
        default_bg = self.default_bg or colors["accent"]
        default_fg = self.default_fg or colors["accent_text"]
        if self.is_disabled():
            fill = self.disabled_bg or colors["surface_disabled"]
            fg, shrink = self.disabled_fg or colors["text_disabled"], 0
        elif self._flashing or (self._pressed and self._hovered):
            fill = self.press_bg or (
                default_bg if self.default_bg else colors["accent_press"]
            )
            fg, shrink = self.press_fg or default_fg, self.press_shrink
        elif self._hovered:
            fill = self.hover_bg or (
                hover_variant(self.rc(default_bg))
                if self.default_bg
                else colors["accent_hover"]
            )
            fg, shrink = self.hover_fg or default_fg, 0
        else:
            fill, fg, shrink = default_bg, default_fg, 0
        border_width = self.border_width
        # Border: a custom color if given, the disabled/focus colors override it.
        border_color = self.border_color or colors["button_border"]
        if self.is_disabled():
            border_color = self.part("disabled_border_color", "border")
        elif self._focused:
            border_color = self.part("focus_color", "focus_ring")
            border_width = max(border_width, 2)
        self.draw_box(
            0,
            0,
            width,
            height,
            self.rc(fill),
            self.rc(border_color),
            border_width,
            self.radius,
            inset=shrink / 2,
        )
        self.draw_content((0, 0, width, height), self.rc(fg), self.text, self.image)


class Label(CanvasWidget):
    """Text and/or an image drawn on a transparent canvas.

    The label blends into whatever it sits on. textvariable keeps the text in
    sync with a tk variable; wraplength wraps long text; anchor/justify align it.
    """

    _COLOR_PARTS = ("text_color", "disabled_text_color")
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "text",
        "textvariable",
        "image",
        "anchor",
        "justify",
        "wraplength",
        "padx",
        "pady",
    )

    def __init__(
        self,
        master,
        text="",
        textvariable=None,
        image=None,
        anchor="w",
        justify="left",
        wraplength=0,
        padx=2,
        pady=2,
        theme=None,
        **kwargs
    ):
        """Create the label.

        text / textvariable: what to show (the variable wins). image: shown left of the
        text. anchor: where the content sits inside the widget. justify / wraplength:
        multi-line alignment and wrapping width in px (0 = no wrapping). padx / pady:
        space around the content.
        """
        super().__init__(master, theme=theme, **kwargs)
        self.text = text
        self.textvariable = textvariable
        self.image = image
        self.anchor = anchor
        self.justify = justify
        self.wraplength = wraplength
        self.padx = padx
        self.pady = pady
        self.watch_variable(textvariable)
        self.refit()
        self.schedule_redraw()

    def display_text(self):
        """The text currently shown: the variable's value if there is one, else text."""
        if self.textvariable is not None:
            return str(self.textvariable.get())
        return self.text

    def _apply_options(self, options):
        """Also (re)attach the watch when the textvariable option changes."""
        super()._apply_options(options)
        if "textvariable" in options:
            self.watch_variable(self.textvariable)

    def on_variable_changed(self):
        """The textvariable changed: the label may need a new size as well as a redraw."""
        self.refit()
        self.schedule_redraw()

    def requested_size(self):
        """The size of the (wrapped) text and image plus padx/pady on each side."""
        width, height = measure_content(
            self.display_text(), self.image, self.font, self.wraplength
        )
        return width + 2 * self.padx, height + 2 * self.pady

    def redraw(self, width, height):
        """Draw the image and text inside the padded area, aligned by anchor/justify."""
        self.draw_content(
            (self.padx, self.pady, width - self.padx, height - self.pady),
            self.current_text_color(),
            self.display_text(),
            self.image,
            self.anchor,
            self.justify,
            self.wraplength,
        )


class _ToggleButton(CanvasWidget):
    """Shared behavior of Checkbutton and Radiobutton: an indicator on the
    left, a text label on the right, toggled by click or space."""

    _COLOR_PARTS = (
        "text_color",
        "disabled_text_color",
        "fill_color",
        "disabled_fill_color",
        "unchecked_color",
        "hover_color",
        "disabled_unchecked_color",
        "border_color",
        "hover_border_color",
        "focus_color",
        "disabled_border_color",
        "check_color",
        "disabled_check_color",
    )

    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "text",
        "command",
        "variable",
        "indicator_size",
        "indicator_radius",
        "spacing",
    )

    def __init__(
        self,
        master,
        text,
        variable,
        command,
        theme,
        indicator_size=18,
        indicator_radius=None,
        spacing=10,
        **kwargs
    ):
        """indicator_size: the box/circle size in px; indicator_radius: its
        corner radius (None = the default look); spacing: px between the
        indicator and the text."""
        super().__init__(master, theme=theme, takefocus=True, **kwargs)
        self.indicator_size = indicator_size
        self.indicator_radius = indicator_radius
        self.spacing = spacing
        self.text = text
        self.command = command
        self.variable = variable
        self.watch_variable(variable)
        self.track_interaction()
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<space>", lambda _: self.invoke(), add="+")
        self.refit()
        self.schedule_redraw()

    def _apply_options(self, options):
        """Also (re)attach the watch when the variable option changes."""
        super()._apply_options(options)
        if "variable" in options:
            self.watch_variable(self.variable)

    def requested_size(self):
        """The indicator plus the spacing and the text, with a little margin."""
        text_width, text_height = measure_content(self.text, None, self.font)
        return (
            2
            + self.indicator_size
            + (self.spacing + text_width if text_width else 0)
            + 4,
            max(self.indicator_size + 6, text_height + 8),
        )

    def _on_press(self, _):
        """Mouse button went down: remember it so a release inside the widget counts as
        a click.
        """
        if not self.is_disabled():
            self._pressed = True
            self.schedule_redraw()

    def _on_release(self, event):
        """Mouse button came up: toggle if the pointer is still over the widget."""
        was_pressed = self._pressed
        self._pressed = False
        self.schedule_redraw()
        if was_pressed and _inside(self, event):
            self.invoke()

    def invoke(self):
        """Toggle as a click would (unless disabled) and run the command."""
        if self.is_disabled():
            return None
        self.activate()
        self.schedule_redraw()
        if self.command is not None:
            return self.command()
        return None

    def activate(self):
        """Change the variable the way a click does (subclasses implement it)."""
        raise NotImplementedError

    def is_selected(self):
        """Whether the indicator should look selected (subclasses implement it)."""
        raise NotImplementedError

    def draw_indicator(self, x1, y1, x2, y2, selected, border_color):
        """Draw the box/circle in the given square and its selected mark (subclasses
        implement it).
        """
        raise NotImplementedError

    def redraw(self, width, height):
        """Draw the indicator (border color by state) and the text beside it."""
        size = self.indicator_size
        top = round((height - size) / 2)
        selected = self.is_selected()
        if self.is_disabled():
            border_color = self.part("disabled_border_color", "border")
        elif self._focused:
            border_color = self.part("focus_color", "focus_ring")
        elif self._hovered:
            border_color = self.part("hover_border_color", "accent")
        else:
            border_color = self.part("border_color", "border")
        self.draw_indicator(2, top, 2 + size, top + size, selected, border_color)
        if self.text:
            self.create_text(
                2 + size + self.spacing,
                height / 2,
                text=self.text,
                font=self.font,
                fill=self.current_text_color(),
                anchor="w",
                tags=_CANVAS_CHROME_TAG,
            )


class Checkbutton(_ToggleButton):
    """A check box that sets a variable to onvalue or offvalue.

    Without a variable it makes its own. The state is read from the variable, so
    other code (or other widgets) changing it is reflected immediately.
    """

    def __init__(
        self,
        master,
        text="",
        variable=None,
        onvalue=1,
        offvalue=0,
        command=None,
        theme=None,
        **kwargs
    ):
        """Create the check box; onvalue/offvalue are what the variable holds when
        checked/unchecked.
        """
        self.onvalue = onvalue
        self.offvalue = offvalue
        if variable is None:
            variable = tk.Variable(master, value=offvalue)
        super().__init__(master, text, variable, command, theme, **kwargs)

    _CUSTOM_OPTIONS = _ToggleButton._CUSTOM_OPTIONS + ("onvalue", "offvalue")

    def is_selected(self):
        """Whether the variable currently equals onvalue (a BooleanVar compares
        truthiness).
        """
        try:
            value = self.variable.get()
        except tk.TclError:
            return False
        if isinstance(self.variable, tk.BooleanVar):
            return bool(value) == bool(self.onvalue)
        return str(value) == str(self.onvalue)

    def activate(self):
        """Flip the variable between onvalue and offvalue."""
        self.variable.set(self.offvalue if self.is_selected() else self.onvalue)

    def select(self):
        """Check the box (set the variable to onvalue)."""
        self.variable.set(self.onvalue)

    def deselect(self):
        """Uncheck the box (set the variable to offvalue)."""
        self.variable.set(self.offvalue)

    def toggle(self):
        """Flip the box without running the command."""
        self.activate()

    def draw_indicator(self, x1, y1, x2, y2, selected, border_color):
        """Draw the rounded box and, when selected, the check mark (scaled to the
        indicator size).
        """
        if selected:
            if self.is_disabled():
                fill = self.part("disabled_fill_color", "surface_disabled")
            else:
                fill = self.part("fill_color", "accent")
        elif self.is_disabled():
            fill = self.part("disabled_unchecked_color", "surface_disabled")
        elif self._hovered:
            fill = self.part("hover_color", "surface_hover")
        else:
            fill = self.part("unchecked_color", "surface")
        # The check mark and corner radius were designed for an 18 px box; scale them to
        # other sizes.
        scale = (x2 - x1) / 18
        radius = 5 * scale if self.indicator_radius is None else self.indicator_radius
        self.draw_box(x1, y1, x2, y2, fill, border_color, 1.5, radius)
        if selected:
            self.create_line(
                x1 + 4.5 * scale,
                y1 + 9.5 * scale,
                x1 + 7.8 * scale,
                y1 + 12.8 * scale,
                x1 + 13.5 * scale,
                y1 + 5.5 * scale,
                fill=(
                    self.part("disabled_check_color", "text_disabled")
                    if self.is_disabled()
                    else self.part("check_color", "accent_text")
                ),
                width=2.2 * scale,
                capstyle="round",
                joinstyle="round",
                tags=_CANVAS_CHROME_TAG,
            )


class Radiobutton(_ToggleButton):
    """A radio button: selected while the shared variable equals its value.

    Radio buttons with the same variable form a group; value defaults to the text.
    """

    def __init__(
        self,
        master,
        text="",
        variable=None,
        value=None,
        command=None,
        theme=None,
        **kwargs
    ):
        """Create the radio button; selecting it sets the variable to value (default:
        the text).
        """
        self.value = text if value is None else value
        if variable is None:
            variable = tk.StringVar(master)
        super().__init__(master, text, variable, command, theme, **kwargs)

    _CUSTOM_OPTIONS = _ToggleButton._CUSTOM_OPTIONS + ("value",)

    def is_selected(self):
        """Whether the variable currently equals this button's value."""
        try:
            return str(self.variable.get()) == str(self.value)
        except tk.TclError:
            return False

    def activate(self):
        """Select this button by setting the variable to its value."""
        self.variable.set(self.value)

    def draw_indicator(self, x1, y1, x2, y2, selected, border_color):
        """Draw the circle and, when selected, the inner dot (pixel-aligned to its
        center).
        """
        if self.is_disabled():
            fill = self.part("disabled_unchecked_color", "surface_disabled")
        elif self._hovered:
            fill = self.part("hover_color", "surface_hover")
        else:
            fill = self.part("unchecked_color", "surface")
        size = x2 - x1
        radius = size / 2 if self.indicator_radius is None else self.indicator_radius
        self.draw_box(
            x1, y1, x2, y2, fill, border_color, 2 if selected else 1.5, radius
        )
        if selected:
            dot = (
                self.part("disabled_fill_color", "text_disabled")
                if self.is_disabled()
                else self.part("fill_color", "accent")
            )
            # Whole-pixel geometry: the dot's size must have the same parity
            # as the circle's so both land on exactly the same center.
            # Inner dot: about 44% of the circle, adjusted below to the same parity.
            dot_size = round(size * 0.44)
            if (size - dot_size) % 2:
                dot_size += 1
            inset = (size - dot_size) // 2
            self.draw_box(
                x1 + inset,
                y1 + inset,
                x2 - inset,
                y2 - inset,
                dot,
                radius=(
                    dot_size / 2
                    if self.indicator_radius is None
                    else self.indicator_radius / 2
                ),
            )
