"""The theme dictionaries and the application-wide theme functions (no display)."""

import pytest

import canvastk as ctk
from canvastk import _core


def test_light_and_dark_palettes_have_the_same_keys():
    assert set(ctk.CANVAS_LIGHT_PALETTE) == set(ctk.CANVAS_DARK_PALETTE)


def test_global_theme_has_palette_radius_style_and_accent_keys():
    theme = ctk.CANVAS_WIDGET_THEME
    assert set(ctk.CANVAS_LIGHT_PALETTE) <= set(theme)
    assert set(ctk.CANVAS_RADII) <= set(theme)
    assert set(ctk.CANVAS_TAB_STYLE_KEYS) <= set(theme)
    for key in ("accent", "accent_hover", "accent_text", "focus_ring", "selection"):
        assert key in theme


def test_every_color_in_the_palettes_is_a_hex_color():
    for palette in (ctk.CANVAS_LIGHT_PALETTE, ctk.CANVAS_DARK_PALETTE):
        for key, value in palette.items():
            assert value.startswith("#") and len(value) == 7, key


def test_default_tab_style_and_radii():
    assert ctk.CANVAS_WIDGET_THEME["tab_style"] == "segmented"
    assert ctk.CANVAS_RADII["tab_radius"] == 10
    assert ctk.CANVAS_RADII["button_radius"] == 15


def test_set_theme_changes_and_reset_theme_restores():
    before = ctk.get_theme()
    ctk.set_theme({"surface": "#123456"})
    assert ctk.get_theme()["surface"] == "#123456"
    assert ctk.CANVAS_WIDGET_THEME["surface"] == "#123456"
    ctk.reset_theme()
    assert ctk.get_theme() == before


def test_set_theme_with_none_removes_a_change():
    ctk.set_theme({"surface": "#123456"})
    ctk.set_theme({"surface": None})
    assert ctk.get_theme()["surface"] == ctk.CANVAS_LIGHT_PALETTE["surface"]


def test_get_theme_returns_a_copy():
    theme = ctk.get_theme()
    theme["surface"] = "#000001"
    assert ctk.get_theme()["surface"] != "#000001"


def test_set_theme_survives_a_mode_switch():
    ctk.set_theme({"accent": "#ff0000"})
    ctk.set_appearance_mode("dark")
    assert ctk.get_theme()["accent"] == "#ff0000"
    assert ctk.get_theme()["window"] == ctk.CANVAS_DARK_PALETTE["window"]


def test_accent_derives_the_dependent_keys():
    ctk.set_theme({"accent": "#ff0000"})
    theme = ctk.get_theme()
    assert theme["accent_hover"] != theme["accent"]
    assert theme["accent_text"] in ("#ffffff", "#000000", "#FFFFFF", "#000000")
    assert "focus_ring" in theme and "selection" in theme and "row_current" in theme


def test_given_accent_hover_is_kept():
    ctk.set_theme({"accent": "#ff0000", "accent_hover": "#00ff00"})
    assert ctk.get_theme()["accent_hover"] == "#00ff00"


def test_color_themes_are_accent_dictionaries():
    for name, theme in ctk.CANVAS_COLOR_THEMES.items():
        assert set(theme) == {"accent"}, name
    ctk.set_theme(ctk.CANVAS_COLOR_THEMES["green"])
    assert ctk.get_theme()["accent"] == ctk.CANVAS_COLOR_THEMES["green"]["accent"]


def test_appearance_mode_functions():
    assert ctk.get_appearance_mode() == "light"
    ctk.set_appearance_mode("dark")
    assert ctk.get_appearance_mode() == "dark"
    ctk.set_appearance_mode("Light")
    assert ctk.get_appearance_mode() == "light"
    with pytest.raises(ValueError):
        ctk.set_appearance_mode("blue")


def test_check_appearance_mode():
    assert _core.check_appearance_mode(None) is None
    assert _core.check_appearance_mode("DARK") == "dark"
    for bad in ("blue", 3, ""):
        with pytest.raises(ValueError):
            _core.check_appearance_mode(bad)


def test_hover_keys_follow_their_base_colors():
    ctk.set_theme({"surface": "#101010"})
    assert ctk.get_theme()["surface_hover"] == ctk.hover_variant("#101010")
    ctk.set_theme({"neutral": "#f0f0f0"})
    assert ctk.get_theme()["neutral_hover"] == ctk.hover_variant("#f0f0f0")


def test_given_hover_key_is_not_derived_over():
    ctk.set_theme({"surface": "#101010", "surface_hover": "#abcdef"})
    assert ctk.get_theme()["surface_hover"] == "#abcdef"


def test_hover_variant_lightens_dark_and_darkens_light():
    dark = ctk.hover_variant("#202020")
    light = ctk.hover_variant("#fafafa")
    assert _core._brightness(dark) > _core._brightness("#202020")
    assert _core._brightness(light) < _core._brightness("#fafafa")


def test_hover_variant_accepts_named_colors(root):
    assert ctk.hover_variant("black") == ctk.hover_variant("#000000")


def test_hover_variant_against_moves_away_from_the_background():
    lighter = _core.hover_variant_against("#cccccc", "#444444")
    darker = _core.hover_variant_against("#222222", "#dddddd")
    assert _core._brightness(lighter) > _core._brightness("#cccccc")
    assert _core._brightness(darker) < _core._brightness("#222222")


def test_expand_theme_adds_derived_keys_and_keeps_given_ones():
    expanded = ctk.expand_theme({"accent": "#2266cc", "focus_ring": "#abcdef"})
    assert expanded["focus_ring"] == "#abcdef"
    assert expanded["accent"] == "#2266cc"
    assert "accent_hover" in expanded and "selection_text" in expanded


def test_expand_theme_without_accent_changes_nothing_else():
    assert ctk.expand_theme({"text": "#111111"}) == {"text": "#111111"}


def test_starting_theme_drops_none_values():
    assert _core.starting_theme(None) == {}
    assert _core.starting_theme({"a": 1, "b": None}) == {"a": 1}


def test_theme_for_mode_ignores_user_changes_when_asked():
    ctk.set_theme({"surface": "#123456"})
    assert _core._theme_for_mode("light")["surface"] == "#123456"
    plain = _core._theme_for_mode("light", user_theme=False)
    assert plain["surface"] == ctk.CANVAS_LIGHT_PALETTE["surface"]


def test_shown_text_matches_tkinter():
    assert _core.shown_text(5) == "5"
    assert _core.shown_text(0) == "0"
    assert _core.shown_text(2.5) == "2.5"
    assert _core.shown_text("x") == "x"
    assert _core.shown_text(None) is None
    assert _core.shown_text(["a"]) == "['a']"


class _FakeFont:
    """measure() is the number of characters, metrics('linespace') is 10."""

    def measure(self, text):
        return len(text)

    def metrics(self, name):
        return 10


def test_measure_content_of_text_lines():
    font = _FakeFont()
    assert _core.measure_content("abc", None, font) == (3, 10)
    assert _core.measure_content("ab\nabcd", None, font) == (4, 20)
    assert _core.measure_content("", None, font) == (0, 0)
    assert _core.measure_content(None, None, font) == (0, 0)


def test_measure_content_converts_numbers_to_text():
    font = _FakeFont()
    assert _core.measure_content(12345, None, font) == (5, 10)
    assert _core.measure_content(0, None, font) == (1, 10)


def test_wheel_direction_for_x11_buttons_and_deltas():
    class Event:
        def __init__(self, num=0, delta=0):
            self.num, self.delta = num, delta

    assert _core.wheel_direction(Event(num=4)) == -1
    assert _core.wheel_direction(Event(num=5)) == 1
    assert _core.wheel_direction(Event(delta=120)) == -1
    assert _core.wheel_direction(Event(delta=-120)) == 1
