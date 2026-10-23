"""Listbox: items, selection, scrolling, and the keyboard and mouse."""

import tkinter as tk

import pytest

import canvastk as ctk

from conftest import settle


@pytest.fixture
def listbox(root):
    box = ctk.Listbox(root, ["zero", "one", "two", "three", "four"], height=5)
    box.pack()
    settle(root)
    return box


def test_contents_size_and_get(listbox):
    assert listbox.size() == 5
    assert listbox.get(0) == "zero"
    assert listbox.get("end") == "four"
    assert listbox.get(1, 3) == ("one", "two", "three")
    assert listbox.get(0, "end") == ("zero", "one", "two", "three", "four")


def test_items_need_not_be_strings(root):
    box = ctk.Listbox(root, [1, 2.5, None])
    box.pack()
    settle(root)
    assert box.get(0) == 1
    box.selection_set(0, "end")
    box.configure(selectmode="extended")
    box.selection_set(0, "end")
    assert box.selection_get() == "1\n2.5\nNone"


def test_insert_and_delete(listbox):
    listbox.insert("end", "five", "six")
    assert listbox.size() == 7 and listbox.get("end") == "six"
    listbox.insert(0, "first")
    assert listbox.get(0) == "first" and listbox.get(1) == "zero"
    listbox.delete(0)
    assert listbox.get(0) == "zero"
    listbox.delete(1, 3)
    assert listbox.get(0, "end") == ("zero", "four", "five", "six")
    listbox.delete(0, "end")
    assert listbox.size() == 0


def test_delete_out_of_range_is_ignored(listbox):
    listbox.delete(50)
    assert listbox.size() == 5
    listbox.delete(3, 99)
    assert listbox.size() == 3


def test_index(listbox):
    assert listbox.index(2) == 2
    assert listbox.index("end") == 5


def test_browse_selection_keeps_one_row(listbox):
    listbox.selection_set(1)
    listbox.selection_set(3)
    assert listbox.curselection() == (3,)
    assert listbox.selection_includes(3)
    assert not listbox.selection_includes(1)


def test_extended_selection_keeps_ranges(root):
    box = ctk.Listbox(root, list("abcdef"), selectmode="extended")
    box.pack()
    box.selection_set(1, 3)
    box.selection_set(5)
    assert box.curselection() == (1, 2, 3, 5)
    box.selection_clear(2, 3)
    assert box.curselection() == (1, 5)
    box.selection_clear(0, "end")
    assert box.curselection() == ()


def test_selection_get_returns_the_selected_text(listbox):
    listbox.selection_set(2)
    assert listbox.selection_get() == "two"


def test_selection_get_without_a_selection_raises(listbox):
    with pytest.raises(tk.TclError):
        listbox.selection_get()


def test_selection_moves_with_inserted_rows(root):
    box = ctk.Listbox(root, list("abc"), selectmode="extended")
    box.selection_set(1)
    box.insert(0, "new")
    assert box.curselection() == (2,)
    box.delete(0)
    assert box.curselection() == (1,)


def test_deleting_the_selected_row_unselects_it(root):
    box = ctk.Listbox(root, list("abc"), selectmode="extended")
    box.selection_set(1)
    box.delete(1)
    assert box.curselection() == ()


def test_one_item_tuple_works_as_an_index(listbox):
    listbox.selection_set(2)
    assert listbox.get(listbox.curselection()) == "two"
    with pytest.raises(tk.TclError):
        listbox.get((1, 2))


def test_nearest_is_clamped(listbox):
    assert listbox.nearest(-100) == 0
    assert listbox.nearest(10_000) == 4


def test_click_selects_a_row_and_generates_the_event(listbox):
    seen = []
    listbox.bind("<<ListboxSelect>>", lambda e: seen.append(listbox.curselection()))
    row_height = listbox._row_height()
    y = listbox.EDGE + row_height * 2 + row_height // 2
    listbox.event_generate("<ButtonPress-1>", x=20, y=y)
    listbox.event_generate("<ButtonRelease-1>", x=20, y=y)
    settle(listbox)
    assert listbox.curselection() == (2,)
    assert seen and seen[-1] == (2,)


def test_arrow_keys_move_the_selection(listbox):
    listbox.activate(1)
    listbox.focus_force()
    listbox.update()
    listbox.event_generate("<Down>")
    assert listbox.curselection() == (2,)
    listbox.event_generate("<Up>")
    listbox.event_generate("<Up>")
    assert listbox.curselection() == (0,)


def test_disabled_listbox_ignores_clicks(listbox):
    listbox.configure(state="disabled")
    row_height = listbox._row_height()
    listbox.event_generate("<ButtonPress-1>", x=20, y=listbox.EDGE + row_height // 2)
    listbox.event_generate("<ButtonRelease-1>", x=20, y=listbox.EDGE + row_height // 2)
    assert listbox.curselection() == ()


def test_scrolling_and_see(root):
    box = ctk.Listbox(root, [str(n) for n in range(100)], height=5)
    box.pack()
    settle(root)
    first, last = box.yview()
    assert first == 0 and 0 < last < 0.2
    box.yview_scroll(10, "units")
    assert box.yview()[0] == pytest.approx(0.10)
    box.yview_moveto(0.5)
    assert box.yview()[0] == pytest.approx(0.5)
    box.yview_moveto(5)
    assert box.yview()[1] == 1.0
    box.see(0)
    assert box.yview()[0] == 0
    box.see(60)
    first, last = box.yview()
    assert first * 100 <= 60 < last * 100


def test_yview_scroll_pages(root):
    box = ctk.Listbox(root, [str(n) for n in range(100)], height=5)
    box.pack()
    settle(root)
    visible = box._visible_rows()
    box.yview_scroll(1, "pages")
    assert box._top == visible


def test_yscrollcommand_is_called(root):
    seen = []
    box = ctk.Listbox(
        root,
        [str(n) for n in range(50)],
        height=5,
        yscrollcommand=lambda *a: seen.append(a),
    )
    box.pack()
    settle(root)
    assert seen


def test_scrolled_listbox_shows_its_bar_only_when_needed(root):
    short = ctk.Listbox(root, ["a", "b"], scrolled=True)
    long = ctk.Listbox(root, [str(n) for n in range(200)], scrolled=True, height=5)
    for box in (short, long):
        box.pack()
    settle(root)
    assert not short._bar_visible()
    assert long._bar_visible()


def test_scrollbar_width_option(root):
    box = ctk.Listbox(
        root, [str(n) for n in range(100)], scrolled=True, scrollbar_width=18
    )
    box.pack()
    settle(root)
    assert box.bar_width == 18
    box.configure(scrollbar_width=24)
    assert box.bar_width == 24


def test_listbox_size_follows_width_and_height(root):
    small = ctk.Listbox(root, ["a"], width=10, height=3)
    big = ctk.Listbox(root, ["a"], width=40, height=12)
    assert big.requested_size()[0] > small.requested_size()[0]
    assert big.requested_size()[1] > small.requested_size()[1]


def test_listbox_radius_keys(root):
    box = ctk.Listbox(root, ["a"])
    assert box.corner(box.radius, "radius") == 8
    assert box.corner(box.row_radius, "row_radius") == 5
    ctk.set_theme({"row_radius": 1})
    assert box.corner(box.row_radius, "row_radius") == 1


# ---- the mouse: selection modes, the built-in scroll bar ---------------------------------
def row_y(box, row):
    return box.EDGE + box._row_height() * (row - box._top) + box._row_height() // 2


def click(box, row, state=0):
    box.event_generate("<ButtonPress-1>", x=20, y=row_y(box, row), state=state)
    box.event_generate("<ButtonRelease-1>", x=20, y=row_y(box, row), state=state)


def test_extended_mode_shift_click_selects_a_range_and_control_click_toggles(root):
    box = ctk.Listbox(root, list("abcdefgh"), selectmode="extended", height=8)
    box.pack()
    settle(root)
    click(box, 1)
    click(box, 4, state=0x1)  # Shift
    assert box.curselection() == (1, 2, 3, 4)
    click(box, 6, state=0x4)  # Control
    assert box.curselection() == (1, 2, 3, 4, 6)
    click(box, 2, state=0x4)
    assert box.curselection() == (1, 3, 4, 6)
    click(box, 0)
    assert box.curselection() == (0,)


def test_multiple_mode_toggles_rows(root):
    box = ctk.Listbox(root, list("abcd"), selectmode="multiple")
    box.pack()
    settle(root)
    click(box, 0)
    click(box, 2)
    assert box.curselection() == (0, 2)
    click(box, 0)
    assert box.curselection() == (2,)


def test_dragging_in_browse_and_extended_modes(root):
    box = ctk.Listbox(root, list("abcdefgh"), height=8)
    box.pack()
    settle(root)
    box.event_generate("<ButtonPress-1>", x=20, y=row_y(box, 1))
    box.event_generate("<B1-Motion>", x=20, y=row_y(box, 4))
    assert box.curselection() == (4,)
    extended = ctk.Listbox(root, list("abcdefgh"), selectmode="extended", height=8)
    extended.pack()
    settle(root)
    extended.event_generate("<ButtonPress-1>", x=20, y=row_y(extended, 1))
    extended.event_generate("<B1-Motion>", x=20, y=row_y(extended, 4))
    assert extended.curselection() == (1, 2, 3, 4)


def test_motion_hovers_a_row_and_leaving_clears_it(root):
    box = ctk.Listbox(root, list("abcd"))
    box.pack()
    settle(root)
    box.event_generate("<Motion>", x=20, y=row_y(box, 2))
    assert box._hover_row == 2
    box.event_generate("<Leave>")
    assert box._hover_row is None


def test_builtin_scrollbar_thumb_drag_and_paging(root):
    box = ctk.Listbox(root, [str(n) for n in range(100)], scrolled=True, height=5)
    box.pack()
    settle(root)
    x = box.winfo_width() - 6
    top, height = box._bar_thumb()
    box.event_generate("<Motion>", x=x, y=top + 2)
    assert box._bar_hover
    box.event_generate("<ButtonPress-1>", x=x, y=int(top + 2))
    assert box._bar_drag_offset is not None
    box.event_generate("<B1-Motion>", x=x, y=int(top + 2 + 60))
    assert box._top > 0
    box.event_generate("<ButtonRelease-1>", x=x, y=int(top + 62))
    assert box._bar_drag_offset is None
    before = box._top
    box.event_generate("<ButtonPress-1>", x=x, y=box.winfo_height() - 4)  # below it
    box.event_generate("<ButtonRelease-1>", x=x, y=box.winfo_height() - 4)
    assert box._top > before


def test_keys_page_home_and_end(root):
    box = ctk.Listbox(root, [str(n) for n in range(60)], height=5)
    box.pack()
    settle(root)
    box.focus_force()
    root.update()
    box.event_generate("<End>")
    assert box.curselection() == (59,)
    box.event_generate("<Home>")
    assert box.curselection() == (0,)
    box.event_generate("<Next>")
    assert box.curselection()[0] == box._visible_rows()


def test_control_arrows_move_without_selecting_in_extended_mode(root):
    box = ctk.Listbox(root, list("abcdef"), selectmode="extended")
    box.pack()
    settle(root)
    box.focus_force()
    root.update()
    box.selection_set(0)
    box.activate(0)
    box.event_generate("<Control-Down>")
    assert box.curselection() == (0,)
    assert box._active == 1


def test_wheel_scrolls_the_list(root):
    box = ctk.Listbox(root, [str(n) for n in range(100)], height=5)
    box.pack()
    settle(root)
    box.event_generate("<Button-5>", x=20, y=20)
    settle(root)
    assert box._top > 0
    box.event_generate("<Button-4>", x=20, y=20)


def test_index_words_active_and_anchor(root):
    box = ctk.Listbox(root, list("abc"))
    box.activate(1)
    assert box.index("active") == 1
    box.selection_anchor(2)
    assert box.index("anchor") == 2
    assert box.get("active") == "b"
    box.insert("end")  # nothing to insert
    assert box.size() == 3
