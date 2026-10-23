"""How themes and appearance modes layer: the application, windows, Toplevels,
containers, and widgets; isolation; reset_theme and reset_full_theme."""

import pytest

import canvastk as ctk

from conftest import settle

LIGHT = ctk.CANVAS_LIGHT_PALETTE
DARK = ctk.CANVAS_DARK_PALETTE


# ---- the application theme reaches everything ------------------------------------------
def test_window_and_widgets_follow_the_application_theme(root):
    button = ctk.Button(root, "x")
    button.pack()
    assert root.get_theme()["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]
    ctk.set_theme({"accent": "#ff0000"})
    assert root.get_theme()["accent"] == "#ff0000"
    assert button.colors["accent"] == "#ff0000"


def test_window_background_follows_the_theme_and_the_mode(root):
    assert root.cget("bg").lower() == LIGHT["window"].lower()
    ctk.set_appearance_mode("dark")
    settle(root)
    assert root.cget("bg").lower() == DARK["window"].lower()
    ctk.set_theme({"window": "#112233"})
    settle(root)
    assert root.cget("bg").lower() == "#112233"


def test_fixed_background_does_not_follow_the_theme():
    window = ctk.Window(bg="#123456")
    try:
        ctk.set_appearance_mode("dark")
        window.update()
        assert window.cget("bg").lower() == "#123456"
    finally:
        window.destroy()


def test_frame_background_is_its_masters(root):
    frame = ctk.Frame(root)
    frame.pack()
    assert frame.cget("bg").lower() == LIGHT["window"].lower()
    ctk.set_theme({"window": "#778899"})
    settle(root)
    assert frame.cget("bg").lower() == "#778899"


# ---- windows --------------------------------------------------------------------------
def test_window_theme_applies_to_its_widgets_only(root):
    other = ctk.Toplevel(root, theme={})
    label = ctk.Label(root, "x")
    other_label = ctk.Label(other, "x")
    root.set_theme({"text": "#010203"})
    assert label.colors["text"].lower() == "#010203"
    assert other_label.colors["text"].lower() == LIGHT["text"].lower()


def test_window_set_theme_get_theme_reset_theme(root):
    assert root.get_theme()["surface"].lower() == LIGHT["surface"].lower()
    root.set_theme({"surface": "#101010"})
    assert root.get_theme()["surface"] == "#101010"
    root.reset_theme()
    assert root.get_theme()["surface"].lower() == LIGHT["surface"].lower()


def test_window_created_with_a_theme_is_cut_off_from_the_application():
    window = ctk.Window(theme={"accent": "#00ff00"})
    try:
        ctk.set_theme({"accent": "#ff0000", "surface": "#222222"})
        theme = window.get_theme()
        assert theme["accent"] == "#00ff00"
        assert theme["surface"].lower() == LIGHT["surface"].lower()
    finally:
        window.destroy()


def test_an_empty_theme_dictionary_also_cuts_a_window_off():
    window = ctk.Window(theme={})
    try:
        ctk.set_theme({"surface": "#222222"})
        assert window.get_theme()["surface"].lower() == LIGHT["surface"].lower()
    finally:
        window.destroy()


def test_window_without_a_theme_follows_the_application():
    window = ctk.Window()
    try:
        ctk.set_theme({"surface": "#222222"})
        assert window.get_theme()["surface"] == "#222222"
    finally:
        window.destroy()


def test_window_reset_theme_goes_back_to_the_creation_theme():
    window = ctk.Window(theme={"accent": "#00ff00"})
    try:
        window.set_theme({"accent": "#0000ff", "surface": "#333333"})
        window.reset_theme()
        theme = window.get_theme()
        assert theme["accent"] == "#00ff00"
        assert theme["surface"].lower() == LIGHT["surface"].lower()
    finally:
        window.destroy()


def test_reset_theme_of_a_window_without_a_theme_follows_the_application_again(root):
    root.set_theme({"surface": "#444444"})
    root.reset_theme()
    ctk.set_theme({"surface": "#555555"})
    assert root.get_theme()["surface"] == "#555555"


def test_window_reset_full_theme_goes_to_the_defaults_and_stays_cut_off(root):
    root.set_theme({"accent": "#00ff00"})
    ctk.set_theme({"surface": "#222222"})
    root.set_appearance_mode("dark")
    root.reset_full_theme()
    theme = root.get_theme()
    assert theme["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]
    assert theme["surface"].lower() == LIGHT["surface"].lower()
    assert root.get_appearance_mode() == "light"
    ctk.set_theme({"surface": "#333333"})
    assert root.get_theme()["surface"].lower() == LIGHT["surface"].lower()
    root.reset_theme()  # nothing to go back to but the defaults now
    assert root.get_theme()["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]


def test_reset_full_theme_forgets_the_creation_theme():
    window = ctk.Window(theme={"accent": "#00ff00"})
    try:
        window.reset_full_theme()
        window.reset_theme()
        assert window.get_theme()["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]
    finally:
        window.destroy()


# ---- appearance modes ---------------------------------------------------------------------
def test_window_appearance_mode(root):
    label = ctk.Label(root, "x")
    assert root.get_appearance_mode() == "light"
    root.set_appearance_mode("dark")
    assert root.get_appearance_mode() == "dark"
    assert label.colors["text"].lower() == DARK["text"].lower()
    assert ctk.get_appearance_mode() == "light"  # the application did not change
    root.set_appearance_mode(None)
    assert root.get_appearance_mode() == "light"
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_window_created_with_an_appearance_mode():
    window = ctk.Window(appearance_mode="dark")
    try:
        assert window.get_appearance_mode() == "dark"
        assert window.get_theme()["window"].lower() == DARK["window"].lower()
        ctk.set_appearance_mode("light")
        assert window.get_appearance_mode() == "dark"
    finally:
        window.destroy()


def test_bad_appearance_modes_are_rejected(root):
    with pytest.raises(ValueError):
        root.set_appearance_mode("blue")
    with pytest.raises(ValueError):
        ctk.Frame(root, appearance_mode="blue")
    with pytest.raises(ValueError):
        ctk.Button(root, "x").set_appearance_mode(3)


def test_widget_appearance_mode(root):
    button = ctk.Button(root, "x")
    button.pack()
    assert button.get_appearance_mode() == "light"
    button.set_appearance_mode("dark")
    assert button.get_appearance_mode() == "dark"
    assert button.colors["window"].lower() == DARK["window"].lower()
    ctk.set_appearance_mode("dark")
    button.set_appearance_mode(None)
    assert button.get_appearance_mode() == "dark"


def test_widget_created_with_an_appearance_mode(root):
    button = ctk.Button(root, "x", appearance_mode="dark")
    assert button.get_appearance_mode() == "dark"


def test_theme_keys_win_over_the_mode(root):
    root.set_appearance_mode("dark")
    root.set_theme({"surface": "#abcdef"})
    assert root.get_theme()["surface"] == "#abcdef"
    assert root.get_theme()["window"].lower() == DARK["window"].lower()


def test_the_accent_follows_the_mode_of_the_window(root):
    root.set_theme({"accent": "#20B5EA"})
    light_row = root.get_theme()["row_current"]
    root.set_appearance_mode("dark")
    assert root.get_theme()["row_current"] != light_row


# ---- containers -----------------------------------------------------------------------
def test_container_theme_applies_to_what_is_inside(root):
    frame = ctk.Frame(root)
    frame.pack()
    inside = ctk.Label(frame, "x")
    outside = ctk.Label(root, "x")
    frame.set_theme({"text": "#0a0b0c"})
    assert inside.colors["text"].lower() == "#0a0b0c"
    assert outside.colors["text"].lower() == LIGHT["text"].lower()


def test_container_inside_container_wins(root):
    outer = ctk.Frame(root)
    inner = ctk.Frame(outer)
    label = ctk.Label(inner, "x")
    outer.set_theme({"text": "#111111"})
    inner.set_theme({"text": "#222222"})
    assert label.colors["text"].lower() == "#222222"
    inner.reset_theme()
    assert label.colors["text"].lower() == "#111111"


def test_widget_colors_win_over_the_container(root):
    frame = ctk.Frame(root)
    label = ctk.Label(frame, "x", text_color="#333333")
    frame.set_theme({"text": "#111111"})
    assert label.cget("text_color") == "#333333"


def test_container_created_with_a_theme_is_cut_off_from_everything_outside(root):
    root.set_theme({"text": "#111111"})
    frame = ctk.Frame(root, theme={"accent": "#00ff00"})
    label = ctk.Label(frame, "x")
    assert label.colors["accent"] == "#00ff00"
    assert label.colors["text"].lower() == LIGHT["text"].lower()
    ctk.set_theme({"text": "#222222"})
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_container_reset_theme_goes_back_to_its_creation_theme(root):
    frame = ctk.Frame(root, theme={"text": "#111111"})
    frame.set_theme({"text": "#999999", "accent": "#ff00ff"})
    frame.reset_theme()
    theme = frame.get_theme()
    assert theme["text"] == "#111111"
    assert theme["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]


def test_container_reset_theme_refreshes_what_is_inside(root):
    frame = ctk.Frame(root, theme={"text": "#111111"})
    label = ctk.Label(frame, "x")
    frame.set_theme({"text": "#999999"})
    assert label.colors["text"] == "#999999"
    frame.reset_theme()
    assert label.colors["text"] == "#111111"


def test_container_reset_full_theme(root):
    frame = ctk.Frame(root, theme={"text": "#111111"}, appearance_mode="dark")
    label = ctk.Label(frame, "x")
    frame.reset_full_theme()
    assert label.colors["text"].lower() == LIGHT["text"].lower()
    assert frame.get_appearance_mode() == "light"
    frame.reset_theme()
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_container_appearance_mode(root):
    frame = ctk.Frame(root)
    label = ctk.Label(frame, "x")
    frame.set_appearance_mode("dark")
    assert label.colors["text"].lower() == DARK["text"].lower()
    assert frame.get_appearance_mode() == "dark"
    assert frame.cget("bg").lower() == DARK["window"].lower()
    frame.set_appearance_mode(None)
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_container_created_with_an_appearance_mode(root):
    frame = ctk.Frame(root, appearance_mode="dark")
    assert ctk.Label(frame, "x").colors["text"].lower() == DARK["text"].lower()


def test_container_mode_inside_a_dark_application(root):
    ctk.set_appearance_mode("dark")
    frame = ctk.Frame(root, appearance_mode="light")
    label = ctk.Label(frame, "x")
    assert label.colors["text"].lower() == LIGHT["text"].lower()


@pytest.mark.parametrize(
    "factory",
    [
        lambda master, **kw: ctk.ScrolledFrame(master, **kw),
        lambda master, **kw: ctk.Foldable(master, "t", **kw),
        lambda master, **kw: ctk.LabelFrame(master, "t", **kw),
        lambda master, **kw: ctk.Notebook(master, **kw),
        lambda master, **kw: ctk.Panedwindow(master, **kw),
        lambda master, **kw: ctk.GridPanedwindow(master, **kw),
    ],
    ids=[
        "ScrolledFrame",
        "Foldable",
        "LabelFrame",
        "Notebook",
        "Panedwindow",
        "GridPanedwindow",
    ],
)
def test_every_container_is_a_theme_scope(root, factory):
    container = factory(root, theme={"text": "#0c0c0c"})
    container.pack()
    child = ctk.Label(container, "x")
    assert child.colors["text"] == "#0c0c0c"
    container.set_theme({"text": "#0d0d0d"})
    assert child.colors["text"] == "#0d0d0d"
    container.reset_theme()
    assert child.colors["text"] == "#0c0c0c"
    container.set_appearance_mode("dark")
    assert container.get_appearance_mode() == "dark"
    container.reset_full_theme()
    assert child.colors["text"].lower() == LIGHT["text"].lower()


# ---- Toplevels -----------------------------------------------------------------------
def test_toplevel_takes_the_theme_of_its_master(root):
    root.set_theme({"text": "#111111"})
    top = ctk.Toplevel(root)
    label = ctk.Label(top, "x")
    assert top.get_theme()["text"] == "#111111"
    assert label.colors["text"] == "#111111"


def test_toplevel_follows_later_changes_of_its_master(root):
    top = ctk.Toplevel(root)
    label = ctk.Label(top, "x")
    root.set_theme({"text": "#222222"})
    assert label.colors["text"] == "#222222"
    root.set_appearance_mode("dark")
    assert label.colors["text"] == "#222222"
    assert top.get_appearance_mode() == "dark"
    assert label.colors["window"].lower() == DARK["window"].lower()
    root.reset_theme()
    assert label.colors["text"].lower() == DARK["text"].lower()


def test_toplevel_takes_the_theme_of_the_container_it_was_made_with(root):
    frame = ctk.Frame(root, theme={"text": "#333333"})
    top = ctk.Toplevel(frame)
    assert ctk.Label(top, "x").colors["text"] == "#333333"


def test_toplevel_own_theme_adds_on_top_of_its_master(root):
    root.set_theme({"text": "#111111", "surface": "#222222"})
    top = ctk.Toplevel(root)
    top.set_theme({"text": "#999999"})
    label = ctk.Label(top, "x")
    assert label.colors["text"] == "#999999"
    assert label.colors["surface"] == "#222222"
    top.reset_theme()
    assert label.colors["text"] == "#111111"


def test_toplevel_with_its_own_appearance_mode(root):
    top = ctk.Toplevel(root, appearance_mode="dark")
    assert ctk.Label(top, "x").colors["text"].lower() == DARK["text"].lower()
    assert root.get_appearance_mode() == "light"


def test_toplevel_created_with_a_theme_is_cut_off_from_its_master(root):
    root.set_theme({"text": "#111111"})
    top = ctk.Toplevel(root, theme={"accent": "#00ff00"})
    label = ctk.Label(top, "x")
    assert label.colors["accent"] == "#00ff00"
    assert label.colors["text"].lower() == LIGHT["text"].lower()
    root.set_theme({"text": "#222222"})
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_toplevel_with_an_empty_theme_is_cut_off_too(root):
    root.set_theme({"text": "#111111"})
    top = ctk.Toplevel(root, theme={})
    assert ctk.Label(top, "x").colors["text"].lower() == LIGHT["text"].lower()


def test_toplevel_reset_full_theme(root):
    root.set_theme({"text": "#111111"})
    top = ctk.Toplevel(root)
    label = ctk.Label(top, "x")
    top.reset_full_theme()
    assert label.colors["text"].lower() == LIGHT["text"].lower()
    root.set_theme({"text": "#222222"})
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_toplevel_is_transient_by_default(root):
    top = ctk.Toplevel(root)
    assert str(top.transient()) == str(root)
    free = ctk.Toplevel(root, transient=False)
    assert str(free.transient()) == ""


def test_toplevel_background_follows_the_theme(root):
    top = ctk.Toplevel(root)
    assert top.cget("bg").lower() == LIGHT["window"].lower()
    root.set_appearance_mode("dark")
    settle(root)
    assert top.cget("bg").lower() == DARK["window"].lower()


# ---- widgets -----------------------------------------------------------------------------
def test_widget_theme_dictionary_and_methods(root):
    label = ctk.Label(root, "x", theme={"text": "#101010"})
    assert label.colors["text"] == "#101010"
    label.set_theme({"text": "#202020"})
    assert label.get_theme()["text"] == "#202020"
    label.reset_theme()
    assert label.colors["text"] == "#101010"  # the theme it was created with
    label.reset_full_theme()
    assert label.colors["text"].lower() == LIGHT["text"].lower()
    label.reset_theme()
    assert label.colors["text"].lower() == LIGHT["text"].lower()


def test_widget_color_options_are_part_of_its_creation_theme(root):
    label = ctk.Label(root, "x", text_color="#112233")
    label.configure(text_color="#445566")
    assert label.cget("text_color") == "#445566"
    label.reset_theme()
    assert label.cget("text_color") == "#112233"


def test_widget_created_with_a_theme_has_it_applied_over_a_dark_mode(root):
    ctk.set_appearance_mode("dark")
    button = ctk.Button(root, "x", theme={"accent": "#ff00ff"})
    assert button.colors["accent"] == "#ff00ff"
    assert button.colors["window"].lower() == DARK["window"].lower()


def test_widget_theme_accent_derives_hover_and_text_keys(root):
    button = ctk.Button(root, "x", theme={"accent": "#ffcc00"})
    assert button.colors["accent_hover"] != "#ffcc00"
    assert button.colors["accent_text"].lower() in ("#000000", "#ffffff")


def test_get_theme_of_a_widget_is_a_copy(root):
    label = ctk.Label(root, "x")
    theme = label.get_theme()
    theme["text"] = "#000001"
    assert label.colors["text"] != "#000001"


# ---- the tab style and radius keys ---------------------------------------------------------
def test_theme_keys_for_radii_and_tab_style_reach_containers(root):
    frame = ctk.Frame(root)
    frame.set_theme({"radius": 1, "tab_style": "underline"})
    assert frame.get_theme()["radius"] == 1
    assert frame.get_theme()["tab_style"] == "underline"
