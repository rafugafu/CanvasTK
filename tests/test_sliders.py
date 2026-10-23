"""Scale, Progressbar, Meter, and Scrollbar."""

import tkinter as tk

import pytest

import canvastk as ctk

from conftest import settle


# ---- Scale -----------------------------------------------------------------------
def test_scale_starts_at_from_and_has_its_own_variable(root):
    scale = ctk.Scale(root, from_=10, to=20)
    scale.pack()
    assert scale.get() == 10
    assert isinstance(scale.variable, tk.DoubleVar)


def test_scale_default_value(root):
    scale = ctk.Scale(root, from_=0, to=100, value=40)
    assert scale.get() == 40


def test_scale_default_value_is_clamped_and_snapped(root):
    assert ctk.Scale(root, from_=0, to=10, value=50).get() == 10
    assert ctk.Scale(root, from_=0, to=10, value=-5).get() == 0
    assert ctk.Scale(root, from_=0, to=10, resolution=2, value=5.2).get() == 6


def test_scale_set_clamps_and_snaps(root):
    scale = ctk.Scale(root, from_=0, to=10, resolution=0.5)
    scale.set(3.3)
    assert scale.get() == 3.5
    scale.set(99)
    assert scale.get() == 10
    scale.set(-1)
    assert scale.get() == 0


def test_scale_with_a_reversed_range(root):
    scale = ctk.Scale(root, from_=10, to=0)
    scale.set(7)
    assert scale.get() == 7
    scale.set(20)
    assert scale.get() == 10


def test_scale_command_runs_only_on_real_changes(root):
    seen = []
    scale = ctk.Scale(root, from_=0, to=10, command=seen.append)
    scale.set(4)
    scale.set(4)
    scale.set(6)
    assert seen == [4, 6]


def test_scale_uses_a_given_variable(root):
    variable = tk.DoubleVar(root, 3)
    scale = ctk.Scale(root, from_=0, to=10, variable=variable)
    assert scale.get() == 3
    scale.set(8)
    assert variable.get() == 8
    variable.set(2)
    assert scale.get() == 2


def test_scale_keys(root):
    scale = ctk.Scale(root, from_=0, to=100, resolution=5)
    scale.pack()
    settle(root)
    scale.focus_force()
    root.update()
    scale.event_generate("<Right>")
    scale.event_generate("<Right>")
    scale.event_generate("<Left>")
    assert scale.get() == 5
    scale.event_generate("<End>")
    assert scale.get() == 100
    scale.event_generate("<Home>")
    assert scale.get() == 0


def test_scale_click_sets_the_value_from_the_pointer(root):
    scale = ctk.Scale(root, from_=0, to=100, length=210)
    scale.pack()
    settle(root)
    scale.event_generate("<ButtonPress-1>", x=scale.winfo_width() - 5, y=14)
    scale.event_generate("<ButtonRelease-1>", x=scale.winfo_width() - 5, y=14)
    assert scale.get() > 90
    scale.event_generate("<ButtonPress-1>", x=5, y=14)
    scale.event_generate("<ButtonRelease-1>", x=5, y=14)
    assert scale.get() < 10


def test_disabled_scale_ignores_keys(root):
    scale = ctk.Scale(root, from_=0, to=100)
    scale.pack()
    settle(root)
    scale.configure(state="disabled")
    scale._nudge(1)
    assert scale.get() == 0


def test_scale_vertical_length(root):
    scale = ctk.Scale(root, orient="vertical", length=200)
    assert scale.winfo_reqheight() == 200


def test_scale_range_can_be_changed_later(root):
    scale = ctk.Scale(root, from_=0, to=10)
    scale.configure(to=50)
    scale.set(40)
    assert scale.get() == 40


# ---- Progressbar -----------------------------------------------------------------
def test_progressbar_value_and_step(root):
    bar = ctk.Progressbar(root, maximum=10)
    bar.pack()
    assert bar.value == 0
    bar.value = 4
    assert bar.value == 4
    bar.step(3)
    assert bar.value == 7
    bar.step(5)
    assert bar.value == 2  # wraps around at the maximum


def test_progressbar_configure_value(root):
    bar = ctk.Progressbar(root)
    bar.configure(value=33)
    assert bar.value == 33


def test_progressbar_variable_is_two_way(root):
    variable = tk.DoubleVar(root, 25)
    bar = ctk.Progressbar(root, variable=variable)
    assert bar.value == 25
    bar.value = 60
    assert variable.get() == 60
    variable.set(10)
    assert bar.value == 10


def test_progressbar_indeterminate_animation(root):
    bar = ctk.Progressbar(root)
    bar.pack()
    bar.start()
    assert bar.mode == "indeterminate"
    settle(root)
    assert bar._animation_id is not None
    bar.stop()
    assert bar._animation_id is None


def test_progressbar_orientations(root):
    horizontal = ctk.Progressbar(root, length=150)
    vertical = ctk.Progressbar(root, orient="vertical", length=150)
    assert horizontal.winfo_reqwidth() == 150
    assert vertical.winfo_reqheight() == 150


# ---- Meter -----------------------------------------------------------------------
def test_meter_fraction_and_shown_value(root):
    meter = ctk.Meter(root, value=25, from_=0, to=100)
    meter.pack()
    assert meter.fraction() == 0.25
    assert meter.shown_value() == "25"


def test_meter_fraction_is_clamped(root):
    meter = ctk.Meter(root, value=500, from_=0, to=100)
    assert meter.fraction() == 1.0
    meter.value = -50
    assert meter.fraction() == 0.0


def test_meter_with_equal_range_has_no_fraction(root):
    assert ctk.Meter(root, from_=5, to=5, value=5).fraction() == 0.0


def test_meter_decimals_and_suffix(root):
    meter = ctk.Meter(root, value=2.345, decimals=1, suffix=" %")
    assert meter.shown_value() == "2.3 %"
    meter = ctk.Meter(root, value=2.345, step=0.01)
    assert meter.shown_value() == "2.35"
    meter = ctk.Meter(root, value=-0.0001, decimals=1)
    assert meter.shown_value() == "0.0"


def test_meter_variable_is_two_way(root):
    variable = tk.DoubleVar(root, 30)
    meter = ctk.Meter(root, variable=variable)
    assert meter.value == 30
    meter.value = 70
    assert variable.get() == 70


@pytest.mark.parametrize("shape", ["gauge", "circle", "semi"])
def test_meter_shapes_get_a_size(root, shape):
    meter = ctk.Meter(root, shape=shape, size=160)
    meter.pack()
    settle(root)
    assert meter.winfo_reqwidth() == 160
    assert meter.winfo_reqheight() > 0


def test_semi_meter_is_shorter_than_a_circle(root):
    circle = ctk.Meter(root, shape="circle", size=160)
    semi = ctk.Meter(root, shape="semi", size=160)
    assert semi.winfo_reqheight() < circle.winfo_reqheight()


def test_interactive_meter_keys_and_command(root):
    seen = []
    meter = ctk.Meter(root, value=50, interactive=True, step=5, command=seen.append)
    meter.pack()
    settle(root)
    meter.focus_force()
    root.update()
    meter.event_generate("<Right>")
    meter.event_generate("<Left>")
    meter.event_generate("<Left>")
    assert meter.value == 45
    assert seen and seen[-1] == 45


def test_non_interactive_meter_ignores_keys(root):
    meter = ctk.Meter(root, value=50, interactive=False)
    meter.pack()
    settle(root)
    meter.event_generate("<Right>")
    assert meter.value == 50


# ---- Scrollbar -------------------------------------------------------------------
def test_scrollbar_set_and_get(root):
    bar = ctk.Scrollbar(root)
    bar.pack(fill="y")
    assert bar.get() == (0.0, 1.0)
    bar.set("0.25", "0.5")
    assert bar.get() == (0.25, 0.5)


def test_scrollbar_connects_to_a_listbox(root):
    listbox = ctk.Listbox(root, [str(n) for n in range(100)], height=5)
    bar = ctk.Scrollbar(root, command=listbox.yview)
    listbox.configure(yscrollcommand=bar.set)
    listbox.pack(side="left")
    bar.pack(side="left", fill="y")
    settle(root)
    first, last = bar.get()
    assert first == 0 and 0 < last < 1
    listbox.yview_moveto(0.5)
    settle(root)
    assert bar.get()[0] > 0.3


def test_scrollbar_page_click_sends_a_scroll(root):
    sent = []
    bar = ctk.Scrollbar(root, command=lambda *args: sent.append(args))
    bar.pack(fill="y")
    root.update()
    bar.set(0.0, 0.2)
    settle(root)
    bar.event_generate("<ButtonPress-1>", x=5, y=bar.winfo_height() - 5)
    bar.event_generate("<ButtonRelease-1>", x=5, y=bar.winfo_height() - 5)
    assert sent


def test_scrollbar_thickness_sets_the_size(root):
    vertical = ctk.Scrollbar(root, thickness=20)
    horizontal = ctk.Scrollbar(root, orient="horizontal", thickness=20)
    assert vertical.winfo_reqwidth() == 20
    assert horizontal.winfo_reqheight() == 20
    vertical.configure(thickness=30)
    assert vertical.winfo_reqwidth() == 30


def test_scrollbar_uses_the_scrollbar_radius_key(root):
    bar = ctk.Scrollbar(root)
    assert bar.corner(bar.radius, "scrollbar_radius") == 99
    ctk.set_theme({"scrollbar_radius": 2})
    assert bar.corner(bar.radius, "scrollbar_radius") == 2
