"""A color picker with the same API as tkinter.colorchooser, drawn with canvastk widgets.

    from canvastk import colorchooser

    rgb, hex_color = colorchooser.askcolor("#3b82f6", title="Pick a color")
    if hex_color:                 # (None, None) when the dialog was cancelled
        print(rgb, hex_color)     # (59, 130, 246) #3b82f6

The dialog is modal and follows the theme of the window it belongs to. It has a
saturation / value square, a hue slider, fields for the hex code and the red, green,
and blue values, a palette of ready-made colors, and the colors you chose before.

Everything that does not need a window (parsing and converting colors, building the
gradient images) is in plain functions at the top.
"""

import colorsys
import string
import tkinter as tk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from ._core import (
    CanvasWidget,
    resolve_color,
    window_appearance_mode,
    window_theme,
    _CANVAS_CHROME_TAG,
)
from .buttons import Button, Label
from .containers import Frame
from .entries import Entry, Spinbox
from .messagebox import _make_modal, _parent_toplevel
from .windows import Toplevel, Window

# The colors chosen before (newest first), shown under the palette in the next dialog.
_COLOR_PICKER_RECENT_COLORS = []
_COLOR_PICKER_RECENT_LIMIT = 12

# The ready-made palette: two rows of twelve.
_COLOR_PICKER_PALETTE = tuple("""
    #EF4444 #F97316 #F59E0B #EAB308 #84CC16 #22C55E
    #10B981 #14B8A6 #06B6D4 #0EA5E9 #3B82F6 #6366F1
    #8B5CF6 #A855F7 #D946EF #EC4899 #F43F5E #78716C
    #000000 #374151 #6B7280 #9CA3AF #E5E7EB #FFFFFF
    """.split())

# The options the dialog understands (the same names as tkinter.colorchooser).
_COLOR_PICKER_OPTIONS = ("parent", "title", "initialcolor", "color")

# Cache of the gradient images (PIL images, so they do not belong to any Tk root).
_COLOR_PICKER_IMAGE_CACHE = {}
_COLOR_PICKER_IMAGE_CACHE_LIMIT = 80


# =============================================================================
# Colors and images that need no window
# =============================================================================


def parse_color(text):
    """The (red, green, blue) integers (0-255) a typed color means, or None.

    Understands '#rgb', '#rrggbb', the same without the '#', and 'r, g, b'.
    """
    text = (text or "").strip()
    if "," in text:
        try:
            numbers = [int(part) for part in text.split(",")]
        except ValueError:
            return None
        if len(numbers) == 3 and all(0 <= number <= 255 for number in numbers):
            return tuple(numbers)
        return None
    digits = text[1:] if text.startswith("#") else text
    if len(digits) not in (3, 6) or any(c not in string.hexdigits for c in digits):
        return None
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    """'#rrggbb' (lowercase, like tkinter) for a (red, green, blue) of 0-255 numbers."""
    red, green, blue = (max(0, min(255, round(part))) for part in rgb)
    return f"#{red:02x}{green:02x}{blue:02x}"


def rgb_to_hsv(rgb):
    """(hue, saturation, value) as numbers from 0 to 1 for a (red, green, blue) of 0-255."""
    return colorsys.rgb_to_hsv(*(part / 255 for part in rgb))


def hsv_to_rgb(hue, saturation, value):
    """The (red, green, blue) integers (0-255) of a hue, saturation, and value (0-1)."""
    return tuple(
        round(part * 255) for part in colorsys.hsv_to_rgb(hue, saturation, value)
    )


def _remember_image(key, build):
    """The cached PIL image for `key`, built by build() the first time."""
    image = _COLOR_PICKER_IMAGE_CACHE.get(key)
    if image is None:
        if len(_COLOR_PICKER_IMAGE_CACHE) >= _COLOR_PICKER_IMAGE_CACHE_LIMIT:
            _COLOR_PICKER_IMAGE_CACHE.clear()
        image = _COLOR_PICKER_IMAGE_CACHE[key] = build()
    return image


def _rounded_alpha(width, height, radius):
    """An 'L' image of a white rounded rectangle on black (anti-aliased), for an alpha mask."""
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1), radius=radius * scale, fill=255
    )
    return mask.resize((width, height), Image.Resampling.LANCZOS)


def square_image(hue, width, height, radius=8):
    """The saturation / value square of a hue as an RGBA image: white at the top left,
    the pure hue at the top right, and black along the bottom.
    """

    def build():
        pure = Image.new("RGB", (width, height), hsv_to_rgb(hue, 1, 1))
        white = Image.new("RGB", (width, height), (255, 255, 255))
        black = Image.new("RGB", (width, height), (0, 0, 0))
        gradient = Image.linear_gradient("L")  # black at the top, white at the bottom
        left_to_right = gradient.transpose(Image.Transpose.ROTATE_90).resize(
            (width, height)
        )
        top_to_bottom = ImageOps.invert(gradient).resize((width, height))
        result = Image.composite(pure, white, left_to_right)
        result = Image.composite(result, black, top_to_bottom).convert("RGBA")
        result.putalpha(_rounded_alpha(width, height, radius))
        return result

    return _remember_image(("square", round(hue * 360), width, height, radius), build)


def hue_strip_image(width, height):
    """The rainbow of the hue slider as a pill-shaped RGBA image."""

    def build():
        pad = height / 2
        span = max(width - 2 * pad, 1)
        strip = Image.new("RGB", (width, 1))
        strip.putdata(
            [hsv_to_rgb(min(max((x - pad) / span, 0), 1), 1, 1) for x in range(width)]
        )
        image = strip.resize((width, height), Image.Resampling.NEAREST).convert("RGBA")
        image.putalpha(_rounded_alpha(width, height, height // 2))
        return image

    return _remember_image(("hue", width, height), build)


# =============================================================================
# The widgets of the dialog
# =============================================================================


class _ColorSquare(CanvasWidget):
    """The saturation / value square of the current hue; drag in it to choose."""

    def __init__(self, master, on_change, **kwargs):
        """on_change(saturation, value) is called while the pointer drags (0-1 each)."""
        kwargs.setdefault("width", 354)
        kwargs.setdefault("height", 210)
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.hue, self.saturation, self.value = 0.0, 1.0, 1.0
        self.configure(cursor="crosshair")
        self.bind("<ButtonPress-1>", self._on_pointer, add="+")
        self.bind("<B1-Motion>", self._on_pointer, add="+")

    def set_color(self, hue, saturation, value):
        """Show a color (the marker moves, and the square changes with the hue)."""
        self.hue, self.saturation, self.value = hue, saturation, value
        self.schedule_redraw()

    def _on_pointer(self, event):
        """Pointer pressed or dragged: choose the color under it."""
        width, height = max(self.winfo_width() - 1, 1), max(self.winfo_height() - 1, 1)
        saturation = min(max(event.x / width, 0), 1)
        value = 1 - min(max(event.y / height, 0), 1)
        self.on_change(saturation, value)

    def redraw(self, width, height):
        """Draw the gradient and the round marker."""
        image = ImageTk.PhotoImage(
            square_image(self.hue, width, height, self.colors["radius"])
        )
        self._images.append(image)
        self.create_image(0, 0, anchor="nw", image=image, tags=_CANVAS_CHROME_TAG)
        x = self.saturation * (width - 1)
        y = (1 - self.value) * (height - 1)
        for radius, color, line in (
            (8, "#000000", 1),
            (7, "#ffffff", 2),
            (5, "#000000", 1),
        ):
            self.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                outline=color,
                width=line,
                tags=_CANVAS_CHROME_TAG,
            )


class _HueSlider(CanvasWidget):
    """The rainbow bar for choosing the hue."""

    def __init__(self, master, on_change, **kwargs):
        """on_change(hue) is called while the pointer drags (0-1)."""
        kwargs.setdefault("width", 354)
        kwargs.setdefault("height", 22)
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.hue = 0.0
        self.configure(cursor="hand2")
        self.bind("<ButtonPress-1>", self._on_pointer, add="+")
        self.bind("<B1-Motion>", self._on_pointer, add="+")

    def set_hue(self, hue):
        """Show a hue (0-1)."""
        self.hue = hue
        self.schedule_redraw()

    def _on_pointer(self, event):
        """Pointer pressed or dragged: choose the hue under it."""
        pad = self.winfo_height() / 2
        span = max(self.winfo_width() - 2 * pad, 1)
        self.on_change(min(max((event.x - pad) / span, 0), 1))

    def redraw(self, width, height):
        """Draw the rainbow and the round thumb (filled with the chosen hue)."""
        image = ImageTk.PhotoImage(hue_strip_image(width, height))
        self._images.append(image)
        self.create_image(0, 0, anchor="nw", image=image, tags=_CANVAS_CHROME_TAG)
        pad = height / 2
        x = pad + self.hue * max(width - 2 * pad, 1)
        fill = rgb_to_hex(hsv_to_rgb(self.hue, 1, 1))
        for radius, line, color in (
            (pad - 0.5, 1, "#000000"),
            (pad - 1.5, 2, "#ffffff"),
        ):
            self.create_oval(
                x - radius,
                pad - radius,
                x + radius,
                pad + radius,
                outline=color,
                width=line,
                fill=fill,
                tags=_CANVAS_CHROME_TAG,
            )


class ColorDisplay(CanvasWidget):
    """A small rounded square showing one color, like a swatch of the color picker.

        swatch = ColorDisplay(root, color="#ff8800")
        swatch.config(color="#3366cc")

    `color` is any tk color ("#rrggbb", a name) or a theme key; `size` is the side in
    px (or give `width` and `height`), `radius` rounds the corners, and `border_width` is
    the border's width in px. The border follows the theme (`border_color` overrides
    it); `highlight` (None, "hover", or "selected") draws a thicker border in the
    theme's text or accent color.
    """

    _COLOR_PARTS = ("border_color",)
    _CUSTOM_OPTIONS = CanvasWidget._CUSTOM_OPTIONS + (
        "color",
        "radius",
        "border_width",
        "highlight",
    )

    # The theme color of each highlight.
    _COLOR_DISPLAY_HIGHLIGHTS = {"hover": "text", "selected": "accent"}

    def __init__(
        self,
        master,
        color="#000000",
        size=24,
        radius=None,
        border_width=1,
        highlight=None,
        **kwargs,
    ):
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)
        self._color = color
        self.radius = radius
        self.border_width = border_width
        self.highlight = highlight
        self.schedule_redraw()

    def _apply_options(self, options):
        """Keep `color` as _color: the name `color` is the base class's method."""
        if "color" in options:
            self._color = options.pop("color")
        super()._apply_options(options)

    def cget(self, key):
        """tkinter cget(): `color` is the color shown."""
        return self._color if key == "color" else super().cget(key)

    def redraw(self, width, height):
        """Draw the square in its color with a thin border."""
        border, border_width = self.part("border_color", "border"), self.border_width
        if self.highlight:  # a thicker border in a theme color
            border = resolve_color(
                self, self.colors[self._COLOR_DISPLAY_HIGHLIGHTS[self.highlight]]
            )
            border_width = max(border_width, 2)
        self.draw_box(
            0,
            0,
            width,
            height,
            resolve_color(self, self.colors.get(self._color, self._color)),
            border,
            border_width,
            self.corner(self.radius, "small_radius"),
        )


class _SwatchGrid(Frame):
    """A grid of small color squares (ColorDisplay widgets); click one to choose it."""

    GAP = 6

    def __init__(self, master, colors, columns, on_pick, **kwargs):
        """colors: '#rrggbb' strings, filled row by row into `columns` columns;
        on_pick(color) is called for a click.
        """
        super().__init__(master, **kwargs)
        self.on_pick = on_pick
        self.current = None
        self.swatches = []
        for index, color in enumerate(colors):
            swatch = ColorDisplay(self, color=color, cursor="hand2")
            swatch.grid(
                row=index // columns,
                column=index % columns,
                padx=(0, self.GAP if index % columns < columns - 1 else 0),
                pady=(
                    0,
                    self.GAP if index // columns < (len(colors) - 1) // columns else 0,
                ),
            )
            swatch.bind(
                "<Enter>", lambda _, s=swatch: self._mark(s, hover=True), add="+"
            )
            swatch.bind("<Leave>", lambda _, s=swatch: self._mark(s), add="+")
            swatch.bind("<ButtonPress-1>", lambda _, c=color: self.on_pick(c), add="+")
            self.swatches.append(swatch)

    def set_current(self, color):
        """Mark the swatch that equals this color (if there is one)."""
        self.current = color
        for swatch in self.swatches:
            self._mark(swatch)

    def _mark(self, swatch, hover=False):
        """Highlight a swatch while hovered, or if it is the current color."""
        if hover:
            swatch.config(highlight="hover")
        elif swatch.cget("color").lower() == self.current:
            swatch.config(highlight="selected")
        else:
            swatch.config(highlight=None)


# =============================================================================
# The dialog
# =============================================================================


class _ColorPickerDialog:
    """The picker window. show() returns ((r, g, b), '#rrggbb'), or (None, None) if the
    dialog was cancelled.
    """

    def __init__(self, parent=None, title="Choose a color", initialcolor=None):
        """parent: the window it belongs to (default: the application's main window)."""
        self.parent = parent
        self.title = title or "Choose a color"
        self.initialcolor = initialcolor
        self.result = (None, None)
        self.hue, self.saturation, self.value = 0.0, 1.0, 1.0
        self._updating = False

    # ---- showing ------------------------------------------------------------------
    def show(self):
        """Open the dialog, wait until it is closed, and return the result."""
        temporary_root = None
        owner = _parent_toplevel(self.parent)
        if owner is None:  # like tkinter: make a root if the program has none
            temporary_root = owner = Window()
            owner.withdraw()
        try:
            self._build(owner)
            _make_modal(self.window, owner)
        finally:
            if temporary_root is not None:
                temporary_root.destroy()
        return self.result

    def _starting_rgb(self, owner):
        """The (r, g, b) of the initial color: hex, 'r, g, b', or a Tk color name."""
        if self.initialcolor is None or self.initialcolor == "":
            return (255, 255, 255)
        if isinstance(self.initialcolor, (tuple, list)) and len(self.initialcolor) == 3:
            return tuple(max(0, min(255, int(part))) for part in self.initialcolor)
        parsed = parse_color(str(self.initialcolor))
        if parsed is not None:
            return parsed
        try:
            return tuple(part >> 8 for part in owner.winfo_rgb(str(self.initialcolor)))
        except tk.TclError:
            raise ValueError(f"unknown color {self.initialcolor!r}") from None

    def _build(self, owner):
        """Create the window and every widget."""
        starting = self._starting_rgb(owner)
        self.hue, self.saturation, self.value = rgb_to_hsv(starting)
        self.window = window = Toplevel(
            owner,
            theme=dict(window_theme(owner)),
            appearance_mode=window_appearance_mode(owner),
        )
        window.title(self.title)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self.cancel)

        body = Frame(window)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        self.square = _ColorSquare(body, self._on_square)
        self.square.pack()
        self.hue_slider = _HueSlider(body, self._on_hue)
        self.hue_slider.pack(pady=(10, 0))

        # --- the numbers: hex, then red, green, and blue
        fields = Frame(body)
        fields.pack(fill="x", pady=(12, 0))
        Label(fields, "Hex").grid(row=0, column=0, padx=(0, 6))
        self.hex_entry = Entry(fields, width=9)
        self.hex_entry.grid(row=0, column=1, padx=(0, 12))
        self.hex_entry.bind("<KeyRelease>", self._on_hex_typed, add="+")
        self.rgb_fields = []
        for column, letter in enumerate("RGB"):
            Label(fields, letter).grid(row=0, column=2 + 2 * column, padx=(0, 4))
            spinbox = Spinbox(
                fields, from_=0, to=255, width=4, command=self._on_rgb_changed
            )
            spinbox.grid(
                row=0, column=3 + 2 * column, padx=(0, 10 if column < 2 else 0)
            )
            spinbox.bind("<KeyRelease>", lambda _: self._on_rgb_changed(), add="+")
            self.rgb_fields.append(spinbox)

        # --- the palette and the colors chosen before
        Label(body, "Colors").pack(anchor="w", pady=(14, 4))
        self.palette = _SwatchGrid(body, _COLOR_PICKER_PALETTE, 12, self._pick_swatch)
        self.palette.pack()
        self.recent = None
        if _COLOR_PICKER_RECENT_COLORS:
            Label(body, "Recent").pack(anchor="w", pady=(10, 4))
            self.recent = _SwatchGrid(
                body, _COLOR_PICKER_RECENT_COLORS, 12, self._pick_swatch
            )
            self.recent.pack(anchor="w")

        row = Frame(window)
        row.pack(fill="x", padx=16, pady=(8, 16))
        Button(row, "OK", command=self.accept).pack(side="right", padx=(8, 0))
        Button(row, "Cancel", command=self.cancel).pack(side="right")
        window.bind("<Return>", lambda _: self.accept())
        window.bind("<Escape>", lambda _: self.cancel())
        self._refresh()
        self.hex_entry.focus_set()
        self.hex_entry.select_range(0, "end")

    # ---- the current color -----------------------------------------------------------
    def current_rgb(self):
        """The (r, g, b) of the color being edited."""
        return hsv_to_rgb(self.hue, self.saturation, self.value)

    def _refresh(self, skip=None):
        """Show the current color everywhere (except in the field named by `skip`, which
        is the one being typed in).
        """
        rgb = self.current_rgb()
        color = rgb_to_hex(rgb)
        self.square.set_color(self.hue, self.saturation, self.value)
        self.hue_slider.set_hue(self.hue)
        self._updating = True
        try:
            if skip != "hex":
                self.hex_entry.set_text(color)
            if skip != "rgb":
                for spinbox, part in zip(self.rgb_fields, rgb):
                    spinbox.set_text(str(part))
        finally:
            self._updating = False
        for grid in (self.palette, self.recent):
            if grid is not None:
                grid.set_current(color)

    def _set_rgb(self, rgb, skip=None):
        """Choose the color of a (r, g, b). A color with no hue (black, white, and the
        grays) keeps the hue that was chosen; black puts the marker in the bottom left
        corner of the square.
        """
        hue, saturation, value = rgb_to_hsv(rgb)
        if saturation > 0 and value > 0:
            self.hue = hue
        self.saturation = saturation
        self.value = value
        self._refresh(skip)

    def _on_square(self, saturation, value):
        """Dragging in the square."""
        self.saturation, self.value = saturation, value
        self._refresh()

    def _on_hue(self, hue):
        """Dragging the hue slider."""
        self.hue = hue
        self._refresh()

    def _pick_swatch(self, color):
        """Click on a swatch."""
        self._set_rgb(parse_color(color))

    def _on_hex_typed(self, _event=None):
        """Typing in the hex field: follow it as soon as it is a valid color."""
        if self._updating:
            return
        rgb = parse_color(self.hex_entry.get())
        if rgb is not None:
            self._set_rgb(rgb, skip="hex")

    def _on_rgb_changed(self):
        """Typing or stepping in the red, green, or blue field."""
        if self._updating:
            return
        try:
            rgb = tuple(int(spinbox.get()) for spinbox in self.rgb_fields)
        except ValueError:
            return  # a field is empty for the moment
        if all(0 <= part <= 255 for part in rgb):
            self._set_rgb(rgb, skip="rgb")

    # ---- finishing ------------------------------------------------------------------
    def accept(self):
        """OK: remember the color for the next dialog and close."""
        rgb = self.current_rgb()
        color = rgb_to_hex(rgb)
        if color in _COLOR_PICKER_RECENT_COLORS:
            _COLOR_PICKER_RECENT_COLORS.remove(color)
        _COLOR_PICKER_RECENT_COLORS.insert(0, color)
        del _COLOR_PICKER_RECENT_COLORS[_COLOR_PICKER_RECENT_LIMIT:]
        self.result = (rgb, color)
        self.window.destroy()

    def cancel(self):
        """Close without choosing (the result stays (None, None))."""
        self.window.destroy()


# =============================================================================
# The tkinter.colorchooser API
# =============================================================================


class Chooser:
    """The color dialog as a class, like tkinter.colorchooser.Chooser: show() returns
    ((r, g, b), '#rrggbb'), or (None, None) if it was cancelled.
    """

    def __init__(self, master=None, **options):
        """Remember the parent (master) and the default options for show()."""
        self.master = master
        self.options = options

    def show(self, **options):
        """Show the dialog; options override the ones given to the constructor."""
        merged = {**self.options, **options}
        merged.setdefault("parent", self.master)
        unknown = set(merged) - set(_COLOR_PICKER_OPTIONS)
        if unknown:
            raise TypeError(f"unexpected option {sorted(unknown)[0]!r}")
        initial = merged.get("initialcolor", merged.get("color"))
        return _ColorPickerDialog(
            merged["parent"], merged.get("title", "Choose a color"), initial
        ).show()


def askcolor(color=None, **options):
    """Ask for a color, starting from `color` (a '#rrggbb' hex code, 'r, g, b', or a
    color name); returns ((r, g, b), '#rrggbb'), or (None, None) if cancelled.
    """
    if color is not None:
        options["initialcolor"] = color
    return Chooser(**options).show()
