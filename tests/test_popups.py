"""OptionMenu, Menu, MenuBar, Tooltip, and the rules for popups (one at a time, closing
on any interaction with something else)."""

import tkinter as tk

import pytest

import canvastk as ctk
from canvastk import popups

from conftest import settle


def open_popups():
    return list(popups._OPEN_POPUPS)


@pytest.fixture(autouse=True)
def no_popups_left_over():
    yield
    for popup in list(popups._OPEN_POPUPS):
        try:
            popup.close()
        except tk.TclError:
            pass
    popups._OPEN_POPUPS.clear()


def simple_menu(root, calls=None):
    calls = calls if calls is not None else []
    menu = ctk.Menu(root)
    menu.add_command(label="One", command=lambda: calls.append("one"))
    menu.add_separator()
    menu.add_command(label="Two", command=lambda: calls.append("two"), state="disabled")
    return menu, calls


# ---- Menu ------------------------------------------------------------------------
def test_menu_entries_and_index(root):
    menu = ctk.Menu(root)
    menu.add_command(label="A")
    menu.add_separator()
    menu.add_checkbutton(label="B")
    menu.add_radiobutton(label="C")
    menu.add_cascade(label="D", menu=ctk.Menu(root))
    assert [e["kind"] for e in menu.entries] == [
        "command",
        "separator",
        "check",
        "radio",
        "cascade",
    ]
    assert menu.index("end") == 4
    assert menu.index("C") == 3
    assert menu.index(1) == 1
    with pytest.raises(ValueError):
        menu.index("missing")


def test_menu_insert_delete_and_configure(root):
    menu = ctk.Menu(root)
    menu.add_command(label="A")
    menu.add_command(label="C")
    menu.insert_command(1, label="B")
    assert [e["label"] for e in menu.entries] == ["A", "B", "C"]
    menu.insert_separator(0)
    assert menu.entries[0]["kind"] == "separator"
    menu.delete(0)
    menu.entryconfigure("B", label="B2", accelerator="Ctrl+B")
    assert menu.entrycget("B2", "accelerator") == "Ctrl+B"
    menu.delete(0, "end")
    assert menu.entries == []


def test_menu_invoke_runs_commands(root):
    menu, calls = simple_menu(root)
    menu.invoke(0)
    assert calls == ["one"]
    menu.invoke("Two")  # disabled
    menu.invoke(1)  # a separator
    assert calls == ["one"]
    menu.entryconfigure("Two", state="normal")
    menu.invoke("Two")
    assert calls == ["one", "two"]


def test_menu_check_and_radio_entries_use_their_variables(root):
    check_variable = tk.BooleanVar(root, False)
    radio_variable = tk.StringVar(root, "a")
    seen = []
    menu = ctk.Menu(root)
    menu.add_checkbutton(
        label="Check", variable=check_variable, command=lambda: seen.append("check")
    )
    menu.add_radiobutton(label="Radio A", variable=radio_variable, value="a")
    menu.add_radiobutton(label="Radio B", variable=radio_variable, value="b")
    menu.invoke(0)
    assert check_variable.get() is True
    menu.invoke(0)
    assert check_variable.get() is False
    menu.invoke(2)
    assert radio_variable.get() == "b"
    assert seen == ["check", "check"]
    snapshot = menu._snapshot()
    assert [item["checked"] for item in snapshot] == [False, False, True]


def test_menu_post_opens_one_popup_and_unpost_closes_it(root):
    menu, _ = simple_menu(root)
    menu.post(100, 100, owner=root)
    settle(root)
    assert len(open_popups()) == 1
    assert [e["label"] for e in open_popups()[0].entries] == ["One", "", "Two"]
    menu.unpost()
    assert open_popups() == []


def test_posting_a_menu_closes_the_open_one(root):
    first, _ = simple_menu(root)
    second, _ = simple_menu(root)
    first.post(100, 100, owner=root)
    settle(root)
    second.post(200, 100, owner=root)
    settle(root)
    assert len(open_popups()) == 1
    assert first._popup is None
    assert second._popup is open_popups()[0]


def test_menu_post_on_close_callback(root):
    closed = []
    menu, _ = simple_menu(root)
    menu.post(50, 50, owner=root, on_close=lambda: closed.append(1))
    settle(root)
    menu.unpost()
    assert closed == [1]


def test_choosing_an_entry_runs_it_and_closes_the_menu(root):
    menu, calls = simple_menu(root)
    menu.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._activate(0)
    assert calls == ["one"]
    assert open_popups() == []


def test_disabled_entries_cannot_be_chosen(root):
    menu, calls = simple_menu(root)
    menu.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._activate(2)
    assert calls == []
    assert open_popups() == [popup]


def test_cascade_opens_a_submenu_and_closing_the_top_closes_both(root):
    inner = ctk.Menu(root)
    inner.add_command(label="Deep")
    outer = ctk.Menu(root)
    outer.add_cascade(label="More", menu=inner)
    outer.post(100, 100, owner=root)
    settle(root)
    top = open_popups()[0]
    top._open_cascade(0, True)
    settle(root)
    assert top.child_popup is not None
    assert top.contains(str(top.child_popup))
    assert len(open_popups()) == 1  # only the top popup is registered
    top.close()
    assert top.child_popup is None
    assert open_popups() == []


def test_menu_theme_methods(root):
    menu = ctk.Menu(root, theme={"surface": "#112233"})
    assert menu.colors["surface"] == "#112233"
    menu.set_theme({"surface": "#445566"})
    assert menu.colors["surface"] == "#445566"
    menu.reset_theme()
    assert menu.colors["surface"] == "#112233"  # back to the theme it was created with
    menu.reset_full_theme()
    assert menu.colors["surface"] == ctk.CANVAS_LIGHT_PALETTE["surface"]


def test_menu_popup_uses_the_window_theme_of_its_owner(root):
    top = ctk.Toplevel(root, theme={"surface": "#abcdef"})
    settle(top)
    menu, _ = simple_menu(root)
    menu.post(10, 10, owner=top)
    settle(root)
    assert open_popups()[0]._colors["surface"].lower() == "#abcdef"


# ---- popups close on interactions ---------------------------------------------------
def post_and_arm(root):
    menu, _ = simple_menu(root)
    menu.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    assert popup.armed
    return menu, popup


def test_popup_is_not_armed_until_the_opening_event_is_over(root):
    menu, _ = simple_menu(root)
    menu.post(100, 100, owner=root)
    popup = open_popups()[0]
    assert not popup.armed
    settle(root)
    assert popup.armed


def test_a_click_on_the_bare_window_closes_the_popup(root):
    _, popup = post_and_arm(root)
    root.event_generate("<ButtonPress-1>", x=5, y=5)
    settle(root)
    assert open_popups() == []


def test_a_click_on_another_widget_closes_the_popup(root):
    other = ctk.Label(root, "other")
    other.pack()
    settle(root)
    _, popup = post_and_arm(root)
    other.event_generate("<ButtonPress-1>", x=2, y=2)
    settle(root)
    assert open_popups() == []


def test_a_click_in_another_window_closes_the_popup(root):
    second = ctk.Toplevel(root)
    second.geometry("200x100+300+300")
    settle(second)
    _, popup = post_and_arm(root)
    second.event_generate("<ButtonPress-1>", x=5, y=5)
    settle(root)
    assert open_popups() == []


def test_a_click_in_the_popup_does_not_close_it(root):
    _, popup = post_and_arm(root)
    popup.canvas.event_generate("<ButtonPress-1>", x=3, y=3)
    settle(root)
    assert open_popups() == [popup]


def test_the_wheel_elsewhere_closes_the_popup(root):
    _, popup = post_and_arm(root)
    root.event_generate("<MouseWheel>", delta=120, x=5, y=5)
    settle(root)
    assert open_popups() == []


def test_a_widget_getting_the_focus_closes_the_popup(root):
    entry = ctk.Entry(root)
    entry.pack()
    settle(root)
    _, popup = post_and_arm(root)
    entry.inner.event_generate("<FocusIn>")
    settle(root)
    assert open_popups() == []


def test_a_whole_window_getting_the_focus_does_not_close_the_popup(root):
    _, popup = post_and_arm(root)
    root.event_generate("<FocusIn>")
    settle(root)
    assert open_popups() == [popup]


def test_moving_the_owner_window_closes_the_popup(root):
    _, popup = post_and_arm(root)
    root.geometry("640x420+30+40")
    settle(root)
    assert open_popups() == []


def test_escape_closes_the_popup(root):
    _, popup = post_and_arm(root)
    popup._escape()
    assert open_popups() == []


def test_closed_popups_are_forgotten_and_unbound(root):
    _, popup = post_and_arm(root)
    popup.close()
    assert open_popups() == []
    assert popup._outside_binding is None
    popup.close()  # closing twice is harmless


def test_closing_before_it_is_armed_cancels_the_arming(root):
    menu, _ = simple_menu(root)
    menu.post(100, 100, owner=root)
    popup = open_popups()[0]
    popup.close()
    settle(root)  # the idle callback must not run on the destroyed popup


# ---- OptionMenu ---------------------------------------------------------------------
def test_optionmenu_default_and_choices(root):
    menu = ctk.OptionMenu(root, None, "b", "a", "b", "c")
    menu.pack()
    assert menu.values == ["a", "b", "c"]
    assert menu.variable.get() == "b"


def test_optionmenu_adds_a_default_that_is_not_a_choice(root):
    menu = ctk.OptionMenu(root, None, "x", "a", "b")
    assert menu.values == ["x", "a", "b"]


def test_optionmenu_values_keyword(root):
    menu = ctk.OptionMenu(root, None, "a", values=["a", "b", "c"])
    assert menu.values == ["a", "b", "c"]
    mixed = ctk.OptionMenu(root, None, "a", "a", values=["b"])
    assert mixed.values == ["a", "b"]


def test_optionmenu_values_can_change_later(root):
    menu = ctk.OptionMenu(root, None, "a", "a")
    menu.configure(values=["p", "q"])
    assert menu.values == ["p", "q"]


def test_optionmenu_with_a_variable(root):
    variable = tk.StringVar(root, "two")
    menu = ctk.OptionMenu(root, variable, None, "one", "two")
    assert menu.variable is variable
    menu.pick("one")
    assert variable.get() == "one"
    variable.set("two")
    settle(root)


def test_optionmenu_pick_runs_the_command(root):
    picked = []
    menu = ctk.OptionMenu(root, None, "a", "a", "b", command=picked.append)
    menu.pick("b")
    assert menu.variable.get() == "b" and picked == ["b"]


def test_optionmenu_opens_marks_the_current_value_and_picks(root):
    menu = ctk.OptionMenu(root, None, "b", "a", "b", "c")
    menu.pack()
    settle(root)
    menu.open_dropdown()
    settle(root)
    popup = menu._dropdown
    assert popup is not None and open_popups() == [popup]
    assert [e["current"] for e in popup.entries] == [False, True, False]
    popup._activate(2)
    assert menu.variable.get() == "c"
    assert menu._dropdown is None


def test_optionmenu_toggle_opens_and_closes(root):
    menu = ctk.OptionMenu(root, None, "a", "a", "b")
    menu.pack()
    settle(root)
    menu.toggle_dropdown()
    assert menu._dropdown is not None
    menu.toggle_dropdown()
    assert menu._dropdown is None


def test_clicking_the_widget_again_closes_its_list_and_does_not_reopen(root):
    menu = ctk.OptionMenu(root, None, "a", "a", "b")
    menu.pack()
    settle(root)
    menu.toggle_dropdown()
    settle(root)
    menu.event_generate("<ButtonPress-1>", x=5, y=5)  # the click that closes it
    menu.event_generate("<ButtonRelease-1>", x=5, y=5)
    settle(root)
    assert menu._dropdown is None


def test_opening_another_dropdown_closes_the_first(root):
    first = ctk.OptionMenu(root, None, "a", "a", "b")
    second = ctk.OptionMenu(root, None, "x", "x", "y")
    first.pack()
    second.pack()
    settle(root)
    first.open_dropdown()
    settle(root)
    second.open_dropdown()
    settle(root)
    assert first._dropdown is None
    assert second._dropdown is not None
    assert len(open_popups()) == 1


def test_disabled_optionmenu_does_not_open(root):
    menu = ctk.OptionMenu(root, None, "a", "a", state="disabled")
    menu.pack()
    settle(root)
    menu.open_dropdown()
    assert menu._dropdown is None


def test_optionmenu_placeholder(root):
    menu = ctk.OptionMenu(root, None, None, "a", placeholder="Choose")
    menu.pack()
    assert menu.showing_placeholder()
    menu.pick("a")
    assert not menu.showing_placeholder()


def test_optionmenu_solid_uses_the_button_colors_and_can_change(root):
    menu = ctk.OptionMenu(root, None, "a", "a", solid=True)
    assert menu.solid
    menu.configure(solid=False)
    assert not menu.solid
    menu.configure(solid=True)
    assert menu.solid


def test_optionmenu_is_wide_enough_for_the_longest_value(root):
    short = ctk.OptionMenu(root, None, "a", "a", "b")
    long = ctk.OptionMenu(root, None, "a", "a", "a very very long value indeed")
    assert long.requested_size()[0] > short.requested_size()[0]


def test_dropdown_popup_height_is_limited(root):
    menu = ctk.OptionMenu(
        root, None, "0", values=[str(n) for n in range(100)], popup_max_height=150
    )
    menu.pack()
    settle(root)
    menu.open_dropdown()
    popup = menu._dropdown
    assert popup.height <= 150 and popup._scrolling
    popup.close()


def test_popup_colors_options(root):
    menu = ctk.OptionMenu(root, None, "a", "a", popup_fill_color="#101112")
    menu.pack()
    settle(root)
    menu.open_dropdown()
    assert menu._dropdown._colors["surface"].lower() == "#101112"
    menu._dropdown.close()


def test_the_tab_style_key_does_not_break_the_popup_colors(root):
    """Every text value of the theme used to be resolved as a color."""
    menu = ctk.OptionMenu(root, None, "a", "a", "b")
    menu.pack()
    settle(root)
    menu.open_dropdown()
    assert menu._dropdown._colors["tab_style"] == "segmented"
    menu._dropdown.close()


# ---- MenuBar ------------------------------------------------------------------------
def test_menubar_opens_a_cascade_menu(root):
    file_menu, calls = simple_menu(root)
    bar_menu = ctk.Menu(root)
    bar_menu.add_cascade(label="File", menu=file_menu)
    bar_menu.add_cascade(label="Edit", menu=ctk.Menu(root))
    bar = ctk.MenuBar(root, bar_menu)
    bar.pack(fill="x")
    settle(root)
    assert [left for left, _, _ in bar._boxes] == sorted(l for l, _, _ in bar._boxes)
    assert len(bar._boxes) == 2
    bar._open(0)
    settle(root)
    assert bar._open_index == 0
    assert len(open_popups()) == 1
    bar._close()
    assert bar._open_index is None and open_popups() == []


def test_menubar_switches_menus_without_two_popups(root):
    first, _ = simple_menu(root)
    second, _ = simple_menu(root)
    bar_menu = ctk.Menu(root)
    bar_menu.add_cascade(label="One", menu=first)
    bar_menu.add_cascade(label="Two", menu=second)
    bar = ctk.MenuBar(root, bar_menu)
    bar.pack(fill="x")
    settle(root)
    bar._open(0)
    settle(root)
    bar._open(1)
    settle(root)
    assert bar._open_index == 1
    assert len(open_popups()) == 1


def test_menubar_ignores_disabled_cascades(root):
    bar_menu = ctk.Menu(root)
    bar_menu.add_cascade(label="Off", menu=ctk.Menu(root), state="disabled")
    bar = ctk.MenuBar(root, bar_menu)
    bar.pack(fill="x")
    settle(root)
    bar._open(0)
    assert bar._open_index is None


# ---- Tooltip ------------------------------------------------------------------------
def test_tooltip_text_is_converted_and_can_be_multiline(root):
    label = ctk.Label(root, "x")
    label.pack()
    assert ctk.Tooltip(label, 5).text == "5"
    assert ctk.Tooltip(label, "two\nlines").text == "two\nlines"


def test_tooltip_theme_methods(root):
    label = ctk.Label(root, "x")
    tip = ctk.Tooltip(label, "hi", theme={"tooltip": "#123456"})
    assert tip._theme_overrides["tooltip"] == "#123456"
    tip.set_theme({"tooltip": "#654321"})
    assert tip._theme_overrides["tooltip"] == "#654321"
    tip.reset_full_theme()
    assert tip._theme_overrides == {}


def test_tooltip_colors_options(root):
    label = ctk.Label(root, "x")
    tip = ctk.Tooltip(label, "hi", fill_color="#111111", text_color="#eeeeee")
    assert tip._theme_overrides["tooltip"] == "#111111"
    assert tip._theme_overrides["text"] == "#eeeeee"


# ---- keyboard and mouse inside a popup -------------------------------------------------------
def numbered_popup(root, count=5, **kwargs):
    seen = []
    menu = ctk.Menu(root)
    for number in range(count):
        menu.add_command(
            label=f"Item {number}", command=lambda n=number: seen.append(n)
        )
    menu.post(100, 100, owner=root)
    settle(root)
    return menu, open_popups()[0], seen


def test_arrow_keys_move_the_hover_and_return_chooses(root):
    _, popup, seen = numbered_popup(root)
    popup.focus_force()
    root.update()
    popup.event_generate("<Down>")
    popup.event_generate("<Down>")
    assert popup._hover == 1
    popup.event_generate("<Up>")
    assert popup._hover == 0
    popup.event_generate("<End>")
    assert popup._hover == 4
    popup.event_generate("<Home>")
    assert popup._hover == 0
    popup.event_generate("<Down>")
    popup.event_generate("<Return>")
    assert seen == [1]
    assert open_popups() == []


def test_hover_skips_separators_and_disabled_entries(root):
    menu = ctk.Menu(root)
    menu.add_command(label="A")
    menu.add_separator()
    menu.add_command(label="B", state="disabled")
    menu.add_command(label="C")
    menu.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._move(1)
    assert popup._hover == 0
    popup._move(1)
    assert popup._hover == 3


def test_motion_hovers_and_leave_clears(root):
    _, popup, _ = numbered_popup(root)
    y = popup.VERTICAL_PADDING + popup._row_height * 2 + 3
    popup.canvas.event_generate("<Motion>", x=10, y=y)
    assert popup._hover == 2
    popup.canvas.event_generate("<Leave>")
    assert popup._hover is None


def test_click_on_an_entry_chooses_it(root):
    _, popup, seen = numbered_popup(root)
    y = popup.VERTICAL_PADDING + popup._row_height * 3 + 3
    popup.canvas.event_generate("<ButtonPress-1>", x=10, y=y)
    popup.canvas.event_generate("<ButtonRelease-1>", x=10, y=y)
    assert seen == [3]


def test_scrolling_popup_thumb_wheel_and_paging(root):
    menu = ctk.Menu(root, tearoff=0)
    for number in range(80):
        menu.add_command(label=f"Item {number}")
    menu.post(100, 20, owner=root)
    settle(root)
    popup = open_popups()[0]
    assert popup._scrolling
    popup.canvas.event_generate("<Button-5>", x=10, y=20)
    assert popup._top > 0
    popup.canvas.event_generate("<Button-4>", x=10, y=20)
    x = popup.width - 4
    top, height = popup._scroll_thumb()
    popup.canvas.event_generate("<ButtonPress-1>", x=x, y=int(top + 2))
    assert popup._scroll_drag_offset is not None
    popup.canvas.event_generate("<B1-Motion>", x=x, y=int(top + 40))
    assert popup._top > 0
    popup.canvas.event_generate("<ButtonRelease-1>", x=x, y=int(top + 40))
    assert popup._scroll_drag_offset is None
    before = popup._top
    popup.canvas.event_generate("<ButtonPress-1>", x=x, y=popup.height - 4)
    popup.canvas.event_generate("<ButtonRelease-1>", x=x, y=popup.height - 4)
    assert popup._top > before


def test_right_and_left_arrows_open_and_close_a_submenu(root):
    inner = ctk.Menu(root)
    inner.add_command(label="Deep")
    outer = ctk.Menu(root)
    outer.add_cascade(label="More", menu=inner)
    outer.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup.focus_force()
    root.update()
    popup.event_generate("<Down>")
    popup.event_generate("<Right>")
    settle(root)
    child = popup.child_popup
    assert child is not None and child.parent_popup is popup
    child.focus_force()
    root.update()
    child.event_generate("<Left>")
    settle(root)
    assert popup.child_popup is None and open_popups() == [popup]


def test_escape_in_a_submenu_closes_only_the_submenu(root):
    inner = ctk.Menu(root)
    inner.add_command(label="Deep")
    outer = ctk.Menu(root)
    outer.add_cascade(label="More", menu=inner)
    outer.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._open_cascade(0, True)
    settle(root)
    popup.child_popup._escape()
    assert popup.child_popup is None and open_popups() == [popup]


def test_hovering_a_cascade_entry_opens_its_submenu_after_a_delay(root):
    inner = ctk.Menu(root)
    inner.add_command(label="Deep")
    outer = ctk.Menu(root)
    outer.add_cascade(label="More", menu=inner)
    outer.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._set_hover(0)
    root.after(400, root.quit)
    root.mainloop()
    assert popup.child_popup is not None


def test_check_and_radio_entries_draw_and_toggle_from_the_popup(root):
    variable = tk.BooleanVar(root, False)
    choice = tk.StringVar(root, "a")
    menu = ctk.Menu(root)
    menu.add_checkbutton(label="Check", variable=variable)
    menu.add_radiobutton(label="A", variable=choice, value="a")
    menu.add_radiobutton(label="B", variable=choice, value="b")
    menu.post(100, 100, owner=root)
    settle(root)
    popup = open_popups()[0]
    popup._activate(0)
    assert variable.get() is True
    menu.post(100, 100, owner=root)
    settle(root)
    open_popups()[0]._activate(2)
    assert choice.get() == "b"


def test_a_popup_too_far_right_or_down_flips_inside_the_screen(root):
    menu = ctk.Menu(root)
    for number in range(5):
        menu.add_command(label=f"Item {number}")
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    menu.post(width - 5, height - 5, owner=root, flip_y=height - 30)
    settle(root)
    popup = open_popups()[0]
    assert popup.winfo_rootx() + popup.width <= width
    assert popup.winfo_rooty() + popup.height <= height


def test_menubar_hover_switches_the_open_menu_and_click_toggles(root):
    first, _ = simple_menu(root)
    second, _ = simple_menu(root)
    bar_menu = ctk.Menu(root)
    bar_menu.add_cascade(label="One", menu=first)
    bar_menu.add_cascade(label="Two", menu=second)
    bar = ctk.MenuBar(root, bar_menu)
    bar.pack(fill="x")
    settle(root)
    first_box, second_box = bar._boxes
    bar.event_generate("<Motion>", x=int(first_box[0]) + 5, y=5)
    assert bar._hover_index == 0
    bar.event_generate("<ButtonPress-1>", x=int(first_box[0]) + 5, y=5)
    settle(root)
    assert bar._open_index == 0
    bar.event_generate("<Motion>", x=int(second_box[0]) + 5, y=5)
    settle(root)
    assert bar._open_index == 1 and len(open_popups()) == 1
    bar.event_generate("<Leave>")
    assert bar._hover_index is None


def test_menubar_set_menu_replaces_the_labels(root):
    bar_menu = ctk.Menu(root)
    bar_menu.add_cascade(label="One", menu=ctk.Menu(root))
    bar = ctk.MenuBar(root, bar_menu)
    bar.pack(fill="x")
    settle(root)
    assert len(bar._boxes) == 1
    other = ctk.Menu(root)
    other.add_cascade(label="A", menu=ctk.Menu(root))
    other.add_cascade(label="B", menu=ctk.Menu(root))
    bar.set_menu(other)
    settle(root)
    assert len(bar._boxes) == 2
    bar.set_menu(None)
    settle(root)
    assert bar._boxes == []


def test_tooltip_shows_after_the_delay_and_hides_on_leave(root):
    label = ctk.Label(root, "hover me")
    label.pack()
    settle(root)
    tip = ctk.Tooltip(label, "A hint\nover two lines", delay=20)
    label.event_generate("<Enter>", x=2, y=2)
    root.after(250, root.quit)
    root.mainloop()
    assert tip._window is not None
    label.event_generate("<Leave>")
    settle(root)
    assert tip._window is None
