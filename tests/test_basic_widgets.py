"""Label, Button, Checkbutton, Radiobutton, Toggle, Separator, and ColorDisplay."""

import tkinter as tk

import pytest

import canvastk as ctk

from conftest import settle


# ---- Label -----------------------------------------------------------------------
def test_label_text_and_configure(root):
    label = ctk.Label(root, "Hello")
    label.pack()
    assert label.text == "Hello"
    label.configure(text="Bye")
    assert label.text == "Bye"
    assert label.cget("text") == "Bye"


@pytest.mark.parametrize("value, shown", [(42, "42"), (0, "0"), (2.5, "2.5")])
def test_label_shows_numbers_like_tkinter(root, value, shown):
    label = ctk.Label(root, value)
    label.pack()
    settle(root)
    assert label.text == shown
    assert label.requested_size()[0] > 0


def test_label_number_set_later_is_converted(root):
    label = ctk.Label(root, "x")
    label.pack()
    label.configure(text=7)
    settle(root)
    assert label.text == "7"


def test_label_without_text_has_no_width(root):
    label = ctk.Label(root)
    assert label.requested_size()[0] == 2 * label.padx


def test_label_textvariable_follows_the_variable(root):
    variable = tk.StringVar(root, "first")
    label = ctk.Label(root, textvariable=variable)
    label.pack()
    settle(root)
    assert label.display_text() == "first"
    variable.set("second")
    settle(root)
    assert label.display_text() == "second"


def test_label_textvariable_with_a_number(root):
    variable = tk.IntVar(root, 5)
    label = ctk.Label(root, textvariable=variable)
    label.pack()
    assert label.display_text() == "5"


def test_label_wraplength_makes_it_taller(root):
    text = "word " * 40
    plain = ctk.Label(root, text)
    wrapped = ctk.Label(root, text, wraplength=120)
    for widget in (plain, wrapped):
        widget.pack()
    settle(root)
    assert wrapped.requested_size()[1] > plain.requested_size()[1]
    assert wrapped.requested_size()[0] <= 120 + 40


def test_label_bigger_text_needs_more_width(root):
    short = ctk.Label(root, "ab")
    long = ctk.Label(root, "abcdefghijklmnop")
    assert long.requested_size()[0] > short.requested_size()[0]


def test_label_multiline_needs_more_height(root):
    one = ctk.Label(root, "a")
    two = ctk.Label(root, "a\nb")
    assert two.requested_size()[1] > one.requested_size()[1]


def test_label_text_color_option(root):
    label = ctk.Label(root, "x", text_color="#ff0000")
    assert label.cget("text_color") == "#ff0000"
    label.configure(text_color="#00ff00")
    assert label.cget("text_color") == "#00ff00"


# ---- Button ----------------------------------------------------------------------
def test_button_invoke_calls_the_command(root):
    calls = []
    button = ctk.Button(root, "Go", command=lambda: calls.append(1))
    button.pack()
    button.invoke()
    assert calls == [1]


def test_button_without_command_does_nothing(root):
    button = ctk.Button(root, "Go")
    button.invoke()


def test_disabled_button_does_not_invoke(root):
    calls = []
    button = ctk.Button(root, "Go", command=lambda: calls.append(1))
    button.pack()
    button.configure(state="disabled")
    button.invoke()
    assert calls == []
    button.configure(state="normal")
    button.invoke()
    assert calls == [1]


def test_button_click_runs_the_command(root):
    calls = []
    button = ctk.Button(root, "Go", command=lambda: calls.append(1))
    button.pack()
    settle(root)
    button.event_generate("<ButtonPress-1>", x=3, y=3)
    button.event_generate("<ButtonRelease-1>", x=3, y=3)
    settle(root)
    assert calls == [1]


def test_button_release_outside_does_not_click(root):
    calls = []
    button = ctk.Button(root, "Go", command=lambda: calls.append(1))
    button.pack()
    settle(root)
    button.event_generate("<ButtonPress-1>", x=3, y=3)
    button.event_generate("<ButtonRelease-1>", x=-50, y=-50)
    settle(root)
    assert calls == []


def test_button_text_is_configurable(root):
    button = ctk.Button(root, "One")
    button.pack()
    button.configure(text="Two")
    assert button.text == "Two"
    button.configure(text=3)
    assert button.text == "3"


def test_button_color_options_are_remembered(root):
    button = ctk.Button(root, "x", default_bg="#112233", hover_fg="#ffffff")
    assert button.cget("default_bg") == "#112233"
    assert button.cget("hover_fg") == "#ffffff"
    assert button.cget("press_bg") is None


def test_button_size_follows_text_and_padding(root):
    small = ctk.Button(root, "a")
    big = ctk.Button(root, "a long button text")
    padded = ctk.Button(root, "a", padx=40, pady=20)
    assert big.requested_size()[0] > small.requested_size()[0]
    assert padded.requested_size()[0] > small.requested_size()[0]
    assert padded.requested_size()[1] > small.requested_size()[1]


def test_button_with_theme_dictionary(root):
    button = ctk.Button(root, "x", theme={"accent": "#ff0000"})
    button.pack()
    settle(root)
    assert button.colors["accent"] == "#ff0000"


def test_button_follows_the_application_theme(root):
    button = ctk.Button(root, "x")
    button.pack()
    assert button.colors["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]
    ctk.set_theme(ctk.CANVAS_COLOR_THEMES["red"])
    assert button.colors["accent"] == ctk.CANVAS_COLOR_THEMES["red"]["accent"]
    ctk.reset_theme()
    assert button.colors["accent"] == ctk.CANVAS_COLOR_THEMES["blue"]["accent"]


def test_button_uses_the_button_radius_key(root):
    button = ctk.Button(root, "x")
    assert button.corner(button.radius, "button_radius") == 15
    ctk.set_theme({"button_radius": 3})
    assert button.corner(button.radius, "button_radius") == 3
    own = ctk.Button(root, "x", radius=1)
    assert own.corner(own.radius, "button_radius") == 1


# ---- Checkbutton / Radiobutton / Toggle -------------------------------------------
def test_checkbutton_toggles_its_variable(root):
    variable = tk.BooleanVar(root, False)
    check = ctk.Checkbutton(root, "Check", variable=variable)
    check.pack()
    assert not check.is_selected()
    check.toggle()
    assert variable.get() is True and check.is_selected()
    check.deselect()
    assert variable.get() is False
    check.select()
    assert variable.get() is True


def test_checkbutton_values_and_command(root):
    variable = tk.StringVar(root, "no")
    calls = []
    check = ctk.Checkbutton(
        root,
        "Check",
        variable=variable,
        onvalue="yes",
        offvalue="no",
        command=lambda: calls.append(variable.get()),
    )
    check.pack()
    check.invoke()
    check.invoke()
    assert calls == ["yes", "no"]


def test_checkbutton_toggle_and_select_do_not_run_the_command(root):
    calls = []
    check = ctk.Checkbutton(root, "Check", command=lambda: calls.append(1))
    check.pack()
    check.toggle()
    check.select()
    check.deselect()
    assert calls == []


def test_disabled_checkbutton_ignores_invoke(root):
    variable = tk.BooleanVar(root, False)
    check = ctk.Checkbutton(root, "Check", variable=variable)
    check.pack()
    check.configure(state="disabled")
    check.invoke()
    assert variable.get() is False


def test_checkbutton_follows_its_variable(root):
    variable = tk.BooleanVar(root, False)
    check = ctk.Checkbutton(root, "Check", variable=variable)
    check.pack()
    variable.set(True)
    settle(root)
    assert check.is_selected()


def test_checkbutton_without_a_variable_still_toggles(root):
    check = ctk.Checkbutton(root, "Check")
    check.pack()
    check.toggle()
    assert check.is_selected()
    check.toggle()
    assert not check.is_selected()


def test_radiobuttons_share_a_variable(root):
    variable = tk.StringVar(root, "a")
    first = ctk.Radiobutton(root, "A", variable=variable, value="a")
    second = ctk.Radiobutton(root, "B", variable=variable, value="b")
    first.pack()
    second.pack()
    assert first.is_selected() and not second.is_selected()
    second.activate()
    assert variable.get() == "b"
    settle(root)
    assert second.is_selected() and not first.is_selected()


def test_radiobutton_command(root):
    variable = tk.IntVar(root, 0)
    calls = []
    radio = ctk.Radiobutton(
        root, "One", variable=variable, value=1, command=lambda: calls.append(1)
    )
    radio.pack()
    radio.invoke()
    assert variable.get() == 1 and calls == [1]


def test_toggle_switches_its_variable(root):
    variable = tk.IntVar(root, 0)
    calls = []
    toggle = ctk.Toggle(
        root, "Switch", variable=variable, command=lambda: calls.append(variable.get())
    )
    toggle.pack()
    settle(root)
    toggle.event_generate("<ButtonPress-1>", x=3, y=3)
    toggle.event_generate("<ButtonRelease-1>", x=3, y=3)
    settle(root)
    assert variable.get() == 1
    assert calls == [1]


def test_toggle_track_width_follows_the_indicator_size(root):
    small = ctk.Toggle(root, "a", indicator_size=16)
    big = ctk.Toggle(root, "a", indicator_size=40)
    assert big.track_width() > small.track_width()


# ---- Separator / ColorDisplay -------------------------------------------------------
def test_separator_orientations(root):
    horizontal = ctk.Separator(root)
    vertical = ctk.Separator(root, orient="vertical")
    horizontal.pack(fill="x")
    vertical.pack(fill="y")
    settle(root)
    assert horizontal.winfo_height() == 1 + 4
    assert vertical.winfo_width() == 1 + 4
    assert ctk.Separator(root, thickness=3).winfo_reqheight() == 3 + 4


def test_color_display_color_and_configure(root):
    display = ctk.ColorDisplay(root, color="#336699", size=30)
    display.pack()
    settle(root)
    assert display.cget("color") == "#336699"
    display.configure(color="#ff0000")
    assert display.cget("color") == "#ff0000"
    assert display.winfo_reqwidth() == 30 and display.winfo_reqheight() == 30


def test_color_display_accepts_color_names(root):
    display = ctk.ColorDisplay(root, color="red")
    display.pack()
    settle(root)
    assert display.cget("color") == "red"


def test_color_display_highlight_option(root):
    display = ctk.ColorDisplay(root, color="#000000", highlight="#ffffff")
    display.pack()
    settle(root)
    display.configure(highlight=None)
    assert display.cget("highlight") is None


def test_button_color_options_follow_reset_theme_and_reset_full_theme(root):
    button = ctk.Button(root, "x", default_bg="#112233", hover_fg="#ffffff")
    button.configure(default_bg="#445566", press_bg="#778899")
    button.reset_theme()
    assert button.cget("default_bg") == "#112233"
    assert button.cget("hover_fg") == "#ffffff"
    assert button.cget("press_bg") is None
    button.reset_full_theme()
    assert button.cget("default_bg") is None and button.cget("hover_fg") is None
    button.configure(default_bg="#000001")
    button.reset_theme()  # nothing to go back to but the defaults now
    assert button.cget("default_bg") is None
