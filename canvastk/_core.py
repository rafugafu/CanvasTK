"""Core of canvastk: the theme/appearance machinery, the cached anti-aliased
rounded-box image renderer, and the CanvasWidget base class every
canvas-drawn widget builds on.

Every widget reads its colors from CANVAS_WIDGET_THEME (or from a `theme=`
dict of overrides given to that one widget), so all of them share one look
and follow set_appearance_mode() / set_theme().
"""

import math
import weakref
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

# Theme palettes: the colors every widget falls back to, by theme key. The accent keys
# are not here, they are derived (see _derive_accent_keys).
CANVAS_LIGHT_PALETTE = {
    "window": "#EBEBEB",
    "neutral": "#E9E2E2",
    "neutral_hover": "#F8F4F4",
    "surface": "#FFFFFF",
    "surface_hover": "#F1F7FA",
    "surface_disabled": "#EFEFEF",
    "border": "#8C9097",
    "text": "#1E1E1E",
    "text_muted": "#6B6F76",
    "text_disabled": "#A3A7AD",
    "track": "#D9DCE0",
    "thumb": "#B4B9C0",
    "thumb_hover": "#8C9097",
    "separator": "#D0D3D8",
    "tooltip": "#FFFFE0",
    "button_border": "#000000",
    "danger": "#D93025",
}

CANVAS_DARK_PALETTE = {
    "window": "#242424",
    "neutral": "#3A3A3C",
    "neutral_hover": "#56565B",
    "surface": "#2B2B2B",
    "surface_hover": "#353638",
    "surface_disabled": "#222222",
    "border": "#5A5F63",
    "text": "#DCE4EE",
    "text_muted": "#9AA0A6",
    "text_disabled": "#6A6F73",
    "track": "#46494C",
    "thumb": "#62666A",
    "thumb_hover": "#80858A",
    "separator": "#454849",
    "tooltip": "#3A3A3A",
    "button_border": "#1A1A1A",
    "danger": "#FF6B63",
}

# Accent presets: each is a theme dict, so ctk.set_theme(CANVAS_COLOR_THEMES["green"])
# applies one. Only the accent is given; the hover color and the rest are derived.
# "blue" is the default accent.
CANVAS_COLOR_THEMES = {
    "blue": {"accent": "#20B5EA"},
    "green": {"accent": "#2CC985"},
    "red": {"accent": "#E5534B"},
    "orange": {"accent": "#F39C12"},
    "purple": {"accent": "#9B6BDF"},
}


def _hex_to_rgb(color):
    """'#rrggbb' -> (red, green, blue) as 0-255 integers."""
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _blend_colors(color, other, amount):
    """color moved `amount` (0..1) of the way towards other."""
    a, b = _hex_to_rgb(color), _hex_to_rgb(other)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def _is_light_color(color, threshold=128):
    """Whether the perceived brightness (0-255, luma weights) of a '#rrggbb' color is
    above threshold.
    """
    red, green, blue = _hex_to_rgb(color)
    return (0.299 * red + 0.587 * green + 0.114 * blue) > threshold


# Colors brighter than this get a darker hover color, all others a lighter one.
_HOVER_DARKEN_ABOVE_BRIGHTNESS = 186


def hover_variant(color):
    """A hover color for a button-like color: lighter for dark and medium
    colors (a black button gets lighter), darker for very light ones (a
    near-white button gets darker), so the change is always visible."""
    color = _as_hex(color)
    if _is_light_color(color, _HOVER_DARKEN_ABOVE_BRIGHTNESS):
        return _blend_colors(color, "#000000", 0.15)
    return _blend_colors(color, "#FFFFFF", 0.35)


# The corner radii (px), theme keys like the colors; they are the same in both modes. A
# big number makes the corners as round as the shape allows (a pill / a circle).
CANVAS_RADII = {
    "radius": 8,  # entries, text boxes, list boxes, drop-downs, frames, tab pages
    "button_radius": 15,  # buttons
    "small_radius": 6,  # small highlights: menu bar items, file dialog parts, swatches
    "row_radius": 5,  # the selected / hovered rows of lists and menus
    "tab_radius": 10,  # the segmented tabs of a Notebook
    "checkbox_radius": 5,  # check boxes (for the default size, scaled with it)
    "track_radius": 99,  # the tracks of sliders, progress bars, and toggle switches
    "scrollbar_radius": 99,  # the track and thumb of every scroll bar
}

# Module state: the current mode, the live theme dict (rebuilt in place), and every
# themed widget/window (weak, so destroyed ones disappear).
_CANVAS_APPEARANCE_MODE = "light"
CANVAS_WIDGET_THEME = {}
_CANVAS_THEMED_WIDGETS = weakref.WeakSet()


# Changes made with set_theme(); applied on top of the palette so they survive mode
# switches.
_CANVAS_USER_THEME = {}


def _as_hex(color):
    """'#rrggbb' for a '#rrggbb' string or any named Tk color."""
    if len(color) == 7 and color[0] == "#":
        return color
    red, green, blue = tk._default_root.winfo_rgb(color)
    return "#%02x%02x%02x" % (red >> 8, green >> 8, blue >> 8)


def _derive_accent_keys(accent, hover, surface, dark):
    """The theme keys that follow from an accent color."""
    accent = _as_hex(accent)
    hover = _as_hex(hover) if hover else hover_variant(accent)
    return dict(
        accent=accent,
        accent_hover=hover,
        accent_press=accent,
        accent_text="#000000" if _is_light_color(accent) else "#FFFFFF",
        focus_ring=_blend_colors(accent, "#FFFFFF" if dark else "#000000", 0.3),
        selection=hover,
        selection_text="#000000" if _is_light_color(hover) else "#FFFFFF",
        row_current=_blend_colors(accent, _as_hex(surface), 0.75 if dark else 0.82),
    )


def expand_theme(theme, base=None, dark=None):
    """theme (a dict of theme keys) plus, if it has an 'accent', every key
    that follows from it (accent_hover, accent_text, focus_ring, selection,
    row_current...) unless the dict gives that key itself. `base` is the theme
    underneath it (for its surface color), and `dark` says whether the keys are for
    the dark mode (by default the current appearance mode)."""
    expanded = dict(theme)
    if theme.get("accent"):
        base = base or CANVAS_WIDGET_THEME
        if dark is None:
            dark = _CANVAS_APPEARANCE_MODE == "dark"
        derived = _derive_accent_keys(
            theme["accent"],
            theme.get("accent_hover"),
            theme.get("surface") or base["surface"],
            dark,
        )
        for key, value in derived.items():
            expanded.setdefault(key, value)
    return expanded


def starting_theme(theme):
    """theme without the keys whose value is None: for a theme given when a widget or
    window is created, None means "use the default". The keys that follow from an
    'accent' are not added here but when the theme is used (see layered_theme), so
    they follow the appearance mode.
    """
    return {k: v for k, v in (theme or {}).items() if v is not None}


def _theme_for_mode(mode):
    """The whole theme for an appearance mode ('light' or 'dark').

    Layers, later ones winning: the light or dark palette, the default (blue) accent
    and the keys derived from it, then the changes made with set_theme().
    """
    dark = mode == "dark"
    theme = dict(CANVAS_RADII)
    theme.update(CANVAS_DARK_PALETTE if dark else CANVAS_LIGHT_PALETTE)
    theme.update(
        _derive_accent_keys(
            CANVAS_COLOR_THEMES["blue"]["accent"],
            None,
            theme["surface"],
            dark,
        )
    )
    theme.update(expand_theme(_CANVAS_USER_THEME, theme, dark))
    return theme


def _rebuild_canvas_widget_theme():
    """Recompute the global theme dict CANVAS_WIDGET_THEME in place, for the current
    appearance mode. The dict is updated in place so every importer sees it.
    """
    theme = _theme_for_mode(_CANVAS_APPEARANCE_MODE)
    CANVAS_WIDGET_THEME.clear()
    CANVAS_WIDGET_THEME.update(theme)


def _refresh_canvas_themed_widgets():
    """Tell every live themed widget and window to re-read the theme and recolor itself."""
    for widget in list(_CANVAS_THEMED_WIDGETS):
        try:
            widget.refresh_theme()
        except tk.TclError:
            pass


def set_appearance_mode(mode):
    """'light' or 'dark'; recolors every existing widget."""
    global _CANVAS_APPEARANCE_MODE
    mode = mode.lower()
    if mode not in ("light", "dark"):
        raise ValueError("mode must be 'light' or 'dark'")
    _CANVAS_APPEARANCE_MODE = mode
    _rebuild_canvas_widget_theme()
    _refresh_canvas_themed_widgets()


def get_appearance_mode():
    """The current appearance mode, 'light' or 'dark'."""
    return _CANVAS_APPEARANCE_MODE


def check_appearance_mode(mode):
    """`mode` as 'light', 'dark', or None (follow the surroundings); ValueError for
    anything else.
    """
    if mode is None:
        return None
    if not isinstance(mode, str) or mode.lower() not in ("light", "dark"):
        raise ValueError("mode must be 'light', 'dark', or None")
    return mode.lower()


def set_theme(theme):
    """Change any theme keys for the whole application, dynamically: every
    existing widget recolors. theme is a dict of theme keys (see
    CANVAS_WIDGET_THEME); a value of None removes that change. Giving an
    'accent' also derives accent_hover, accent_text, focus_ring, selection,
    and row_current unless you give them. The changes survive appearance
    mode and color theme changes."""
    for key, value in theme.items():
        if value is None:
            _CANVAS_USER_THEME.pop(key, None)
        else:
            _CANVAS_USER_THEME[key] = value
    # Build the theme once at import so CANVAS_WIDGET_THEME is never empty.
    _rebuild_canvas_widget_theme()
    _refresh_canvas_themed_widgets()


def reset_theme():
    """Remove every change made with set_theme()."""
    _CANVAS_USER_THEME.clear()
    _rebuild_canvas_widget_theme()
    _refresh_canvas_themed_widgets()


def get_theme():
    """A copy of the current global theme (theme key -> color)."""
    return dict(CANVAS_WIDGET_THEME)


def window_theme(widget):
    """The theme overrides of the window that contains widget (a dict;
    empty if the window is not a canvastk Window/Toplevel)."""
    if widget is None:
        return {}
    try:
        return widget.winfo_toplevel()._theme_overrides
    except (AttributeError, tk.TclError):
        return {}


def window_appearance_mode(widget):
    """The appearance mode of the window that contains widget ('light' or 'dark'), or
    None if that window follows the global one (or is not a canvastk Window/Toplevel).
    """
    if widget is None:
        return None
    try:
        return widget.winfo_toplevel()._appearance_mode
    except (AttributeError, tk.TclError):
        return None


def theme_scopes(widget):
    """The containers (frames and windows) that hold `widget`, the outermost first: the
    ones whose theme and appearance mode apply to everything inside them. The search
    stops at the window, so a Toplevel does not inherit from the window it belongs to.
    """
    scopes = []
    current = widget
    while current is not None:
        if getattr(current, "_is_theme_scope", False):
            # The outer frame of a composite container stands for the container.
            scope = getattr(current, "_scope_owner", current)
            if not any(scope is other for other in scopes):
                scopes.append(scope)
        if getattr(current, "_is_window", False):
            break
        current = getattr(current, "master", None)
    scopes.reverse()
    return scopes


def refresh_theme_inside(root, skip=None):
    """Make every themed widget inside the container `root` (not in other windows)
    re-read its theme, the containers before what they hold. `skip` is left out.
    """
    inside = []
    for widget in list(_CANVAS_THEMED_WIDGETS):
        current = widget
        while current is not None and current is not root:
            if getattr(current, "_is_window", False):
                current = None
                break
            current = getattr(current, "master", None)
        if current is root and widget is not skip:
            inside.append(widget)
    for widget in sorted(inside, key=lambda widget: str(widget).count(".")):
        try:
            widget.refresh_theme()
        except tk.TclError:
            pass


def effective_appearance_mode(widget, own_mode=None):
    """The appearance mode that applies to `widget`: its own `own_mode`, else the one of
    the innermost container around it that has one, else the global mode.
    """
    if own_mode:
        return own_mode
    for scope in reversed(theme_scopes(widget)):
        if scope._appearance_mode:
            return scope._appearance_mode
    return _CANVAS_APPEARANCE_MODE


def layered_theme(widget, own_mode, own_overrides):
    """The effective theme of something inside `widget`'s containers: the whole theme of
    the appearance mode that applies (see effective_appearance_mode), then the themes
    of the containers around it, outermost first, then its own `own_overrides`.
    """
    scopes = theme_scopes(widget)
    mode = effective_appearance_mode(widget, own_mode)
    theme = dict(
        CANVAS_WIDGET_THEME
        if mode == _CANVAS_APPEARANCE_MODE
        else _theme_for_mode(mode)
    )
    # The keys that follow from an accent are worked out here, for this mode.
    for layer in [scope._theme_overrides for scope in scopes] + [own_overrides]:
        theme.update(expand_theme(layer, theme, mode == "dark"))
    return theme


_rebuild_canvas_widget_theme()

# Rendering constants. Every drawn item carries the chrome tag; boxes are rendered at 4x
# and scaled down for smooth edges; the image caches are bounded.
_CANVAS_CHROME_TAG = "chrome"
_ROUNDED_BOX_SUPERSAMPLE = 4
_ROUNDED_BOX_CACHE_LIMIT = 600
_ROUNDED_BOX_IMAGE_CACHE = {}
# Boxes bigger than this (in px^2) are drawn from corner pieces, not one image.
_SLICED_BOX_MINIMUM_AREA = 6000


def rounded_box_image(
    width,
    height,
    radius,
    fill,
    outline=None,
    outline_width=0,
    inset=0,
    corners=(True, True, True, True),
):
    """A cached, anti-aliased rounded box (transparent outside the shape)
    as a PhotoImage. fill/outline are '#rrggbb' strings (fill may be None).
    corners is (top-left, top-right, bottom-right, bottom-left) roundness."""
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return None
    key = (width, height, radius, fill, outline, outline_width, inset, corners)
    image = _ROUNDED_BOX_IMAGE_CACHE.get(key)
    if image is not None:
        return image
    scale = _ROUNDED_BOX_SUPERSAMPLE
    pad = inset * scale
    x1 = y1 = pad
    x2 = width * scale - 1 - pad
    y2 = height * scale - 1 - pad
    if x2 <= x1 or y2 <= y1:
        return None
    # Draw large (supersampled) on a transparent background, then shrink: the downscale
    # anti-aliases the edges.
    big = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle(
        [x1, y1, x2, y2],
        radius=min(radius * scale, (x2 - x1) / 2, (y2 - y1) / 2),
        fill=fill,
        outline=outline if outline_width > 0 else None,
        width=max(1, int(outline_width * scale)),
        corners=corners,
    )
    image = ImageTk.PhotoImage(big.resize((width, height), Image.Resampling.LANCZOS))
    # Keep the cache bounded.
    if len(_ROUNDED_BOX_IMAGE_CACHE) >= _ROUNDED_BOX_CACHE_LIMIT:
        # Drop the oldest half; widgets still showing an image keep their
        # own reference to it.
        for old_key in list(_ROUNDED_BOX_IMAGE_CACHE)[: _ROUNDED_BOX_CACHE_LIMIT // 2]:
            del _ROUNDED_BOX_IMAGE_CACHE[old_key]
    _ROUNDED_BOX_IMAGE_CACHE[key] = image
    return image


_CORNER_IMAGE_CACHE = {}


def corner_images(radius, fill, outline, outline_width, corners):
    """The four anti-aliased corner pieces (top-left, top-right, bottom-right,
    bottom-left; each radius x radius) of a rounded box, cached by style only.
    Big boxes are assembled from these plus plain rectangles for the straight
    edges, so resizing never re-renders an image."""
    key = (radius, fill, outline, outline_width, corners)
    images = _CORNER_IMAGE_CACHE.get(key)
    if images is not None:
        return images
    scale = _ROUNDED_BOX_SUPERSAMPLE
    # Render a box 3 radii wide so that the corners are separated by a straight
    # stretch (PIL fails on a box exactly 2 radii wide when only some corners
    # are rounded), then cut the four corners out of it.
    size = 3 * radius
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle(
        [0, 0, size * scale - 1, size * scale - 1],
        radius=radius * scale,
        fill=fill,
        outline=outline if outline_width > 0 else None,
        width=max(1, outline_width * scale),
        corners=corners,
    )
    small = big.resize((size, size), Image.Resampling.LANCZOS)
    # Cut the four corners (top-left, top-right, bottom-right, bottom-left) out of the
    # rendered box.
    far = 2 * radius
    pieces = (
        small.crop((0, 0, radius, radius)),
        small.crop((far, 0, size, radius)),
        small.crop((far, far, size, size)),
        small.crop((0, far, radius, size)),
    )
    images = tuple(ImageTk.PhotoImage(piece) for piece in pieces)
    _CORNER_IMAGE_CACHE[key] = images
    return images


def cross_image(size, color, background=None, reach=3.5, thickness=1.6):
    """A cached, anti-aliased, perfectly symmetric 'x' (optionally on a round
    background disc) as a size x size PhotoImage; colors are '#rrggbb'."""
    key = ("cross", size, color, background, reach, thickness)
    image = _ROUNDED_BOX_IMAGE_CACHE.get(key)
    if image is not None:
        return image
    scale = 8
    big_size = size * scale
    center = big_size / 2
    arm = reach * scale
    half_width = thickness * scale / 2
    big = Image.new("RGBA", (big_size, big_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    if background is not None:
        draw.ellipse([0, 0, big_size, big_size], fill=background)
    for sign in (1, -1):
        start = (center - arm, center - sign * arm)
        end = (center + arm, center + sign * arm)
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        normal_x = -(end[1] - start[1]) / length * half_width
        normal_y = (end[0] - start[0]) / length * half_width
        # A polygon (not draw.line) keeps the stroke exactly symmetric.
        draw.polygon(
            [
                (start[0] + normal_x, start[1] + normal_y),
                (end[0] + normal_x, end[1] + normal_y),
                (end[0] - normal_x, end[1] - normal_y),
                (start[0] - normal_x, start[1] - normal_y),
            ],
            fill=color,
        )
        for x, y in (start, end):
            draw.ellipse(
                [x - half_width, y - half_width, x + half_width, y + half_width],
                fill=color,
            )
    image = ImageTk.PhotoImage(big.resize((size, size), Image.Resampling.LANCZOS))
    _ROUNDED_BOX_IMAGE_CACHE[key] = image
    return image


def load_canvas_image(path, size=None):
    """Load an image file as a PhotoImage (resized to size=(w, h) if given)
    suitable for the `image` option of Button and Label."""
    image = Image.open(path).convert("RGBA")
    if size is not None:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)


def resolve_color(widget, color):
    """Any Tk color (name, #rgb, #rrggbb) as '#rrggbb'."""
    if color is None:
        return None
    if len(color) == 7 and color[0] == "#":
        return color
    red, green, blue = widget.winfo_rgb(color)
    return "#%02x%02x%02x" % (red >> 8, green >> 8, blue >> 8)


def child_background_role(master):
    """The theme color role ('window', 'surface'...) children of master get
    by default, or None if master is not one of these themed containers."""
    return getattr(master, "child_background_role", None)


def parent_background(widget):
    """The background color of widget (tk or ttk) as '#rrggbb'."""
    try:
        return resolve_color(widget, widget.cget("background"))
    except tk.TclError:
        pass
    try:
        style = ttk.Style(widget)
        name = str(widget.cget("style")) or widget.winfo_class()
        color = style.lookup(name, "background") or style.lookup("TFrame", "background")
        if color:
            return resolve_color(widget, color)
    except tk.TclError:
        pass
    return "#F0F0F0"


def make_font(font=None, size=11, weight="normal"):
    """A tkfont.Font from a Font, a font spec, or None (the default family).
    Fonts built from a spec are shared between widgets (creating a Tk font
    costs a font-matching lookup, which adds up with hundreds of widgets)."""
    if isinstance(font, tkfont.Font):
        return font
    root = tk._default_root
    cache = root.__dict__.setdefault("_canvastk_font_cache", {}) if root else {}
    key = (None if font is None else repr(font), size, weight)
    shared = cache.get(key)
    if shared is None:
        if font is None:
            family = cache.get("default family")
            if family is None:
                family = cache["default family"] = tkfont.nametofont(
                    "TkDefaultFont"
                ).actual("family")
            shared = tkfont.Font(family=family, size=size, weight=weight)
        else:
            shared = tkfont.Font(font=font)
        cache[key] = shared
    return shared


def measure_widths(parent, font, texts):
    """The pixel widths of many strings in a font, as tkfont.Font.measure() gives them.

    Every Font.measure() call can take milliseconds (the font is looked up again each
    time), which makes measuring hundreds of strings, such as a font list, freeze the
    program for seconds. Here one hidden canvas text item is reused for all strings,
    which is thousands of times faster.
    """
    texts = list(texts)
    if len(texts) < 4:
        return [font.measure(text) for text in texts]
    canvas = tk.Canvas(parent)
    try:
        item = canvas.create_text(0, 0, text="0", font=font, anchor="nw")
        left, _, right, _ = canvas.bbox(item)
        # A canvas text box is a little wider than the text; remove that difference.
        extra = (right - left) - font.measure("0")
        widths = []
        for text in texts:
            canvas.itemconfigure(item, text=text)
            box = canvas.bbox(item)
            widths.append(max(0, box[2] - box[0] - extra) if text and box else 0)
        return widths
    finally:
        canvas.destroy()


def measure_content(text, image, font, wraplength=0, gap=6):
    """(width, height) of text with an optional image to its left."""
    lines = text.split("\n") if text else []
    text_width = max((font.measure(line) for line in lines), default=0)
    line_count = len(lines)
    if wraplength and text_width > wraplength:
        line_count = sum(
            max(1, math.ceil(font.measure(line) / wraplength)) for line in lines
        )
        text_width = wraplength
    text_height = line_count * font.metrics("linespace")
    image_width = image.width() if image else 0
    image_height = image.height() if image else 0
    width = image_width + (gap if image_width and text_width else 0) + text_width
    return width, max(text_height, image_height)


def wheel_direction(event):
    """+1 for a scroll-down wheel event, -1 for scroll-up."""
    if event.num == 4:
        return -1
    if event.num == 5:
        return 1
    return -1 if event.delta > 0 else 1


_WHEEL_SEQUENCES = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def _inside(widget, event):
    """Whether a mouse event happened inside the widget's own area (used to cancel a
    click dragged away).
    """
    return 0 <= event.x < widget.winfo_width() and 0 <= event.y < widget.winfo_height()


def pop_color_parts(parts, kwargs):
    """Remove the color options named in parts from kwargs and return them
    (as a dict suitable for a widget's theme overrides)."""
    return {name: kwargs.pop(name) for name in parts if name in kwargs}


class _WidgetPlumbing:
    """Shared by every widget: theme colors, cancellable timers, and a
    watched tk variable that triggers a refresh when it changes.

    Every color a widget draws is a named part (listed in its _COLOR_PARTS,
    e.g. border_color, hover_fill_color): pass it as a keyword argument or to
    configure() to override the theme for that one widget; None goes back to
    the theme."""

    _COLOR_PARTS = ()
    _appearance_mode = None  # 'light' / 'dark' for this widget alone, else follows

    def _merged_colors(self):
        """The theme of the appearance mode that applies, then the window's theme, then
        this widget's own.
        """
        return layered_theme(self, self._appearance_mode, self._theme_overrides)

    def set_appearance_mode(self, mode):
        """'light' or 'dark' for this widget alone; None follows its window (or the
        global mode). Theme keys set on the window or the widget still win.
        """
        self._appearance_mode = check_appearance_mode(mode)
        self.refresh_theme()

    def get_appearance_mode(self):
        """The appearance mode this widget uses, 'light' or 'dark'."""
        return effective_appearance_mode(self, self._appearance_mode)

    def _init_plumbing(self, theme):
        """Set up theme state, the pending-call set, and the watched-variable slot.

        Must be called after the Tk widget exists (it needs winfo for the window
        theme). `theme` is this widget's own theme-key / color-part overrides.
        """
        # An 'accent' in the theme also derives accent_hover, accent_text...
        self._theme_overrides = starting_theme(theme)
        self.colors = self._merged_colors()
        _CANVAS_THEMED_WIDGETS.add(self)
        self._pending_calls = set()
        self._watched_variable = None
        self._watch_trace_id = None

    def refresh_theme(self):
        """Re-read the global and window themes (they changed)."""
        self.colors = self._merged_colors()
        self.on_theme_changed()

    def set_theme(self, theme):
        """Change theme keys (or color options) for this widget only,
        dynamically; None removes a change. See set_theme() for 'accent'."""
        for key, value in theme.items():
            if value is None:
                self._theme_overrides.pop(key, None)
            else:
                self._theme_overrides[key] = value
        self.refresh_theme()

    def get_theme(self):
        """This widget's effective theme (theme key -> color)."""
        return dict(self.colors)

    def reset_theme(self):
        """Remove every color change made on this widget."""
        self._theme_overrides.clear()
        self.refresh_theme()

    def on_theme_changed(self):
        """Hook called after the colors were re-read; redraws by default (composites
        override it).
        """
        self.schedule_redraw()

    def color(self, key):
        """The theme color for  as '#rrggbb' (this widget's merged theme)."""
        return resolve_color(self, self.colors[key])

    def corner(self, own, key):
        """A corner radius: `own` if the widget was given one, else the theme's `key`
        (see CANVAS_RADII).
        """
        return self.colors[key] if own is None else own

    def part(self, name, default_key):
        """The color of the named part: the widget's own override if set,
        else the theme color default_key."""
        value = self._theme_overrides.get(name)
        if value:
            return resolve_color(self, value)
        return resolve_color(self, self.colors[default_key])

    def set_color_part(self, name, value):
        """Set (or, with None, remove) this widget's override for one named color part
        and rebuild its colors.
        """
        if value is None:
            self._theme_overrides.pop(name, None)
        else:
            self._theme_overrides[name] = value
        self.colors = self._merged_colors()

    def rc(self, value):
        """Resolve any Tk color (name, #rgb, #rrggbb) to '#rrggbb'."""
        return resolve_color(self, value)

    def call_later(self, milliseconds, callback):
        """after()/after_idle() that is cancelled automatically on destroy.
        milliseconds=None means 'when idle'."""

        def run():
            """Run the callback and forget its after-id (it has fired, so there is
            nothing left to cancel).
            """
            self._pending_calls.discard(identifier)
            callback()

        if milliseconds is None:
            identifier = self.after_idle(run)
        else:
            identifier = self.after(milliseconds, run)
        self._pending_calls.add(identifier)
        return identifier

    def cancel_call(self, identifier):
        """Cancel a timer made by call_later(); None is ignored."""
        if identifier is not None:
            self._pending_calls.discard(identifier)
            self.after_cancel(identifier)

    def watch_variable(self, variable):
        """Redraw/refresh whenever the tk variable changes (replaces any variable watched before).

        None just stops watching. The change is reported through on_variable_changed().
        """
        self._unwatch_variable()
        if variable is not None:
            self._watched_variable = variable
            self._watch_trace_id = variable.trace_add(
                "write", lambda *_: self.on_variable_changed()
            )

    def _unwatch_variable(self):
        """Remove the trace from the watched variable (if any); a variable that is
        already gone is fine.
        """
        if self._watched_variable is not None:
            try:
                self._watched_variable.trace_remove("write", self._watch_trace_id)
            except tk.TclError:
                pass
            self._watched_variable = None

    def on_variable_changed(self):
        """Hook called when the watched variable is written; redraws by default."""
        self.schedule_redraw()

    def destroy(self):
        """Cancel timers, stop watching the variable, leave the theme registry, then
        destroy the widget.
        """
        for identifier in list(self._pending_calls):
            try:
                self.after_cancel(identifier)
            except tk.TclError:
                pass
        self._pending_calls.clear()
        self._unwatch_variable()
        _CANVAS_THEMED_WIDGETS.discard(self)
        super().destroy()


class CanvasWidget(_WidgetPlumbing, tk.Canvas):
    """Base of every purely canvas-drawn widget. Subclasses implement
    redraw(width, height) (and requested_size() if they size to content);
    redraws are coalesced to one per idle cycle."""

    DEFAULT_WIDTH = 100
    DEFAULT_HEIGHT = 30
    DEFAULT_FONT_SIZE = 11
    DEFAULT_FONT_WEIGHT = "normal"
    _CUSTOM_OPTIONS = ("bg", "background", "fg", "foreground", "state", "font")

    def __init__(
        self, master, theme=None, takefocus=False, background_from=None, **kwargs
    ):
        """Create the canvas and set up theme, font, redraw bookkeeping, and the resize binding.

        Pops the options this class handles itself (color parts, bg/fg, state, font)
        out of kwargs before the rest go to tk.Canvas. `background_from` names the
        widget whose background this one blends into (default: its master).
        """
        self._fixed_width = "width" in kwargs
        self._fixed_height = "height" in kwargs
        theme = {**(theme or {}), **pop_color_parts(self._COLOR_PARTS, kwargs)}
        self._appearance_mode = check_appearance_mode(
            kwargs.pop("appearance_mode", None)
        )
        background = kwargs.pop("bg", kwargs.pop("background", None))
        self.fg = kwargs.pop("fg", kwargs.pop("foreground", None))
        self.state = kwargs.pop("state", "normal")
        font = kwargs.pop("font", None)
        kwargs.setdefault("width", self.DEFAULT_WIDTH)
        kwargs.setdefault("height", self.DEFAULT_HEIGHT)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        self._background_source = background_from or master
        self._background_override = background
        self._applied_background = background or parent_background(
            self._background_source
        )
        # Canvas created with the parent's background so the transparent corners of
        # rounded images blend in.
        tk.Canvas.__init__(
            self, master, takefocus=takefocus, bg=self._applied_background, **kwargs
        )
        # Theme/timer state needs the Tk widget to exist.
        self._init_plumbing(theme)
        self.font = make_font(font, self.DEFAULT_FONT_SIZE, self.DEFAULT_FONT_WEIGHT)
        self._redraw_id = None
        self._images = []
        self._hovered = False
        self._pressed = False
        self._focused = False
        # Redraw whenever the widget is resized.
        self.bind("<Configure>", lambda _: self.schedule_redraw(), add="+")

    # ---- options -------------------------------------------------------
    def configure(self, cnf=None, **kw):
        """tkinter configure(): handles the custom options (colors, font, state, subclass
        options) itself and passes the rest to tk.Canvas, then re-fits and redraws.
        """
        if cnf is None and not kw:
            return tk.Canvas.configure(self)
        if isinstance(cnf, str):
            return tk.Canvas.configure(self, cnf)
        if cnf:
            kw = {**cnf, **kw}
        # Options handled by this class and its subclasses never reach tk.Canvas.
        custom = {
            k: kw.pop(k)
            for k in list(kw)
            if k in self._CUSTOM_OPTIONS or k in self._COLOR_PARTS
        }
        if custom:
            self._apply_options(custom)
        if kw:
            if "width" in kw:
                self._fixed_width = True
            if "height" in kw:
                self._fixed_height = True
            tk.Canvas.configure(self, **kw)
        self.refit()
        self.schedule_redraw()

    config = configure

    def cget(self, key):
        """tkinter cget(): custom options come from our attributes, the rest from
        tk.Canvas.
        """
        if key == "foreground":
            key = "fg"
        if key in ("bg", "background"):
            return self._background_override or tk.Canvas.cget(self, "bg")
        if key in self._COLOR_PARTS:
            return self._theme_overrides.get(key)
        if key in self._CUSTOM_OPTIONS:
            return getattr(self, key)
        return tk.Canvas.cget(self, key)

    def _apply_options(self, options):
        """Store changed custom options (colors, font...); subclasses extend this to
        react to specific ones.
        """
        for key, value in options.items():
            if key in ("bg", "background"):
                self._background_override = value
                self._applied_background = None
            elif key in ("fg", "foreground"):
                self.fg = value
            elif key in self._COLOR_PARTS:
                self.set_color_part(key, value)
            elif key == "font":
                self.font = make_font(
                    value, self.DEFAULT_FONT_SIZE, self.DEFAULT_FONT_WEIGHT
                )
            else:
                setattr(self, key, value)

    # ---- sizing / redrawing ---------------------------------------------
    def requested_size(self):
        """(width, height) this widget wants for its content, or None."""
        return None

    def refit(self):
        """Resize the canvas to requested_size() on the axes the user did not fix with
        width/height.
        """
        size = self.requested_size()
        if size is None:
            return
        options = {}
        if not self._fixed_width:
            options["width"] = int(size[0])
        if not self._fixed_height:
            options["height"] = int(size[1])
        if options:
            tk.Canvas.configure(self, **options)

    def schedule_redraw(self):
        """Ask for a redraw soon; any number of requests before the next idle moment
        cost a single redraw.
        """
        if self._redraw_id is None:
            self._redraw_id = self.call_later(None, self._run_redraw)

    def _run_redraw(self):
        """Clear the canvas and call redraw() with the current size (the idle callback
        of schedule_redraw).

        Also re-reads the parent's background first, so a themed parent that changed
        color is followed without anyone telling the widget.
        """
        self._redraw_id = None
        try:
            width = self.winfo_width()
            height = self.winfo_height()
        except tk.TclError:
            return  # destroyed (e.g. by its parent) before this ran
        if width <= 1 or height <= 1:
            return
        background = self._background_override or parent_background(
            self._background_source
        )
        if background != self._applied_background:
            tk.Canvas.configure(self, bg=background)
            self._applied_background = background
        # Start from a blank canvas; redraw() recreates everything (the image cache
        # keeps this cheap).
        tk.Canvas.delete(self, "all")
        self._images = []
        self.redraw(width, height)

    def redraw(self, width, height):
        """Draw the widget at the given pixel size; every concrete widget implements
        this.
        """
        raise NotImplementedError

    # ---- drawing helpers -------------------------------------------------
    def is_disabled(self):
        """Whether the widget is in the 'disabled' state."""
        return self.state == "disabled"

    def current_text_color(self):
        """The text color for the current state: the disabled color, else fg /
        text_color / the theme text.
        """
        if self.is_disabled():
            return self.part("disabled_text_color", "text_disabled")
        return self.rc(self.fg) if self.fg else self.part("text_color", "text")

    def draw_box(
        self,
        x1,
        y1,
        x2,
        y2,
        fill,
        outline=None,
        outline_width=0,
        radius=8,
        inset=0,
        corners=(True, True, True, True),
    ):
        """Draw a rounded box covering (x1, y1)-(x2, y2) with an optional outline.

        Small boxes are a single cached anti-aliased image; large ones are assembled
        from cached corner pieces plus rectangles (see _draw_sliced_box) so resizing
        never renders an image. `inset` shrinks the box on all sides (button press
        effect); `corners` says which corners are rounded.
        """
        left, top, right, bottom = round(x1), round(y1), round(x2), round(y2)
        width, height = right - left, bottom - top
        corner = int(round(min(radius, width / 2, height / 2)))
        # Large boxes: corner pieces + rectangles instead of one big image.
        if width * height > _SLICED_BOX_MINIMUM_AREA and not inset and corner >= 2:
            self._draw_sliced_box(
                left, top, right, bottom, fill, outline, outline_width, corner, corners
            )
            return None
        image = rounded_box_image(
            width, height, radius, fill, outline, outline_width, inset, corners
        )
        if image is None:
            return None
        self._images.append(image)
        return self.create_image(
            left, top, anchor="nw", image=image, tags=_CANVAS_CHROME_TAG
        )

    def _draw_sliced_box(
        self, left, top, right, bottom, fill, outline, outline_width, radius, corners
    ):
        """A large rounded box built from cached corner images and plain
        rectangles (the straight edges), so it costs no image rendering at
        any size."""
        # Straight edges are whole-pixel rectangles, so the outline width is rounded to
        # whole pixels here.
        border = max(1, round(outline_width)) if outline and outline_width > 0 else 0
        pieces = corner_images(
            radius, fill, outline if border else None, border, corners
        )
        self._images.extend(pieces)
        # Corner images go at the four corners of the box.
        for piece, (x, y) in zip(
            pieces,
            (
                (left, top),
                (right - radius, top),
                (right - radius, bottom - radius),
                (left, bottom - radius),
            ),
        ):
            self.create_image(x, y, anchor="nw", image=piece, tags=_CANVAS_CHROME_TAG)

        def rectangle(x1, y1, x2, y2, color):
            """A borderless filled rectangle (skipped when it would be empty)."""
            if x2 > x1 and y2 > y1:
                self.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=color,
                    outline="",
                    width=0,
                    tags=_CANVAS_CHROME_TAG,
                )

        if fill:
            rectangle(left + radius, top, right - radius, bottom, fill)
            rectangle(left, top + radius, left + radius, bottom - radius, fill)
            rectangle(right - radius, top + radius, right, bottom - radius, fill)
        if border:
            rectangle(left + radius, top, right - radius, top + border, outline)
            rectangle(left + radius, bottom - border, right - radius, bottom, outline)
            rectangle(left, top + radius, left + border, bottom - radius, outline)
            rectangle(right - border, top + radius, right, bottom - radius, outline)

    def draw_chevron(self, center_x, center_y, direction, color, size=4, width=2):
        """A small ‹ › ⌃ ⌄ arrow head made of two round-capped lines."""
        if direction == "down":
            points = (
                center_x - size,
                center_y - size / 2,
                center_x,
                center_y + size / 2,
                center_x + size,
                center_y - size / 2,
            )
        elif direction == "up":
            points = (
                center_x - size,
                center_y + size / 2,
                center_x,
                center_y - size / 2,
                center_x + size,
                center_y + size / 2,
            )
        elif direction == "left":
            points = (
                center_x + size / 2,
                center_y - size,
                center_x - size / 2,
                center_y,
                center_x + size / 2,
                center_y + size,
            )
        else:
            points = (
                center_x - size / 2,
                center_y - size,
                center_x + size / 2,
                center_y,
                center_x - size / 2,
                center_y + size,
            )
        self.create_line(
            *points,
            fill=color,
            width=width,
            capstyle="round",
            joinstyle="round",
            tags=_CANVAS_CHROME_TAG,
        )

    def draw_content(
        self,
        box,
        fill,
        text,
        image=None,
        anchor="center",
        justify="left",
        wraplength=0,
        gap=6,
    ):
        """Draw an optional image and text side by side inside box."""
        x1, y1, x2, y2 = box
        text_item = None
        text_width = text_height = 0
        if text:
            options = {}
            if wraplength:
                options["width"] = wraplength
            text_item = self.create_text(
                0,
                0,
                text=text,
                font=self.font,
                fill=fill,
                anchor="w",
                justify=justify,
                tags=_CANVAS_CHROME_TAG,
                **options,
            )
            left, top, right, bottom = tk.Canvas.bbox(self, text_item)
            text_width = right - left
            text_height = bottom - top
        image_width = image.width() if image else 0
        image_height = image.height() if image else 0
        total = image_width + (gap if image_width and text_width else 0) + text_width
        content_height = max(text_height, image_height)
        # Horizontal placement of the image+text group, then vertical placement,
        # according to the anchor.
        if anchor in ("w", "nw", "sw"):
            x = x1
        elif anchor in ("e", "ne", "se"):
            x = x2 - total
        else:
            x = (x1 + x2) / 2 - total / 2
        if anchor in ("n", "nw", "ne"):
            y = y1 + content_height / 2
        elif anchor in ("s", "sw", "se"):
            y = y2 - content_height / 2
        else:
            y = (y1 + y2) / 2
        if image:
            self.create_image(x, y, image=image, anchor="w", tags=_CANVAS_CHROME_TAG)
            x += image_width + gap
        if text_item is not None:
            self.coords(text_item, x, y)

    # ---- interaction helpers ----------------------------------------------
    def track_interaction(self):
        """Keep self._hovered / self._focused up to date (and redraw)."""

        def set_flag(name, value):
            """Set a state attribute (_hovered / _focused) and redraw."""
            setattr(self, name, value)
            self.schedule_redraw()

        self.bind("<Enter>", lambda _: set_flag("_hovered", True), add="+")
        self.bind("<Leave>", lambda _: set_flag("_hovered", False), add="+")
        self.bind("<FocusIn>", lambda _: set_flag("_focused", True), add="+")
        self.bind("<FocusOut>", lambda _: set_flag("_focused", False), add="+")

    def bind_wheel(self, callback):
        """Call callback(+1 or -1) for a mouse wheel turn (works with Windows/macOS and
        X11 events).
        """
        for sequence in _WHEEL_SEQUENCES:
            self.bind(sequence, lambda event: callback(wheel_direction(event)), add="+")


class _ChromeCanvas(CanvasWidget):
    """The canvas behind a composite widget; paints via the owner's callback."""

    def __init__(self, master, painter, background_from=None, theme=None):
        """Create the 1x1 starting canvas; `painter(canvas, width, height)` does the
        drawing.
        """
        super().__init__(
            master, theme=theme, background_from=background_from, width=1, height=1
        )
        self._painter = painter

    def redraw(self, width, height):
        """Let the owning composite widget paint its chrome on this canvas."""
        self._painter(self, width, height)
