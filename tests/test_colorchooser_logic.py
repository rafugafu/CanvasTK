"""The color conversions of the color picker (no display)."""

import pytest

from canvastk import colorchooser as cc


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#ff8800", (255, 136, 0)),
        ("ff8800", (255, 136, 0)),
        ("#f80", (255, 136, 0)),
        ("F80", (255, 136, 0)),
        ("  #FF8800  ", (255, 136, 0)),
        ("255, 136, 0", (255, 136, 0)),
        ("0,0,0", (0, 0, 0)),
    ],
)
def test_parse_color_accepts(text, expected):
    assert cc.parse_color(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", None, "red", "#ff88", "#gg0000", "256, 0, 0", "1, 2", "1, 2, 3, 4", "a, b, c"],
)
def test_parse_color_rejects(text):
    assert cc.parse_color(text) is None


def test_rgb_to_hex_is_lowercase_and_clamped():
    assert cc.rgb_to_hex((255, 0, 10)) == "#ff000a"
    assert cc.rgb_to_hex((300, -5, 127.6)) == "#ff0080"


def test_hsv_round_trip():
    for rgb in [(0, 0, 0), (255, 255, 255), (58, 123, 213), (200, 10, 30), (1, 2, 3)]:
        assert cc.hsv_to_rgb(*cc.rgb_to_hsv(rgb)) == rgb


def test_rgb_to_hsv_of_primary_colors():
    assert cc.rgb_to_hsv((255, 0, 0)) == (0.0, 1.0, 1.0)
    hue, saturation, value = cc.rgb_to_hsv((0, 255, 0))
    assert (round(hue, 3), saturation, value) == (0.333, 1.0, 1.0)
    assert cc.rgb_to_hsv((255, 255, 255)) == (0.0, 0.0, 1.0)
    assert cc.rgb_to_hsv((0, 0, 0)) == (0.0, 0.0, 0.0)


def test_hsv_to_rgb_corners():
    assert cc.hsv_to_rgb(0, 1, 1) == (255, 0, 0)
    assert cc.hsv_to_rgb(0.5, 0, 1) == (255, 255, 255)
    assert cc.hsv_to_rgb(0.7, 1, 0) == (0, 0, 0)


def test_square_and_hue_images_have_the_asked_size():
    assert cc.square_image(0.3, 40, 30, 4).size == (40, 30)
    assert cc.hue_strip_image(50, 10).size == (50, 10)


def _close(pixel, expected, tolerance=12):
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, expected))


def test_square_image_corners_follow_saturation_and_value():
    image = cc.square_image(0.0, 60, 40, 0).convert("RGB")
    assert _close(image.getpixel((0, 0)), (255, 255, 255))  # no saturation, full value
    assert _close(image.getpixel((59, 0)), (255, 0, 0))  # the hue itself
    assert _close(image.getpixel((0, 39)), (0, 0, 0))  # no value
