"""Panedwindow and GridPanedwindow: panes, sashes, dragging panes, and docking."""

import tkinter as tk

import pytest

import canvastk as ctk
from canvastk import containers

from conftest import settle


def make_panes(master, count, **options):
    return [ctk.Frame(master, **options) for _ in range(count)]


# ---- Panedwindow -------------------------------------------------------------------
@pytest.fixture
def paned(root):
    window = ctk.Panedwindow(root, orient="horizontal")
    window.pack(fill="both", expand=True)
    window.frames = make_panes(window, 3)
    for frame in window.frames:
        ctk.Label(frame, "pane").pack()
        window.add(frame, weight=1)
    settle(root)
    return window


def test_panes_are_listed_in_order(paned):
    assert paned.panes() == paned.frames


def test_panes_fill_the_widget_without_overlapping(paned):
    frames = paned.frames
    assert frames[0].winfo_x() == 0
    for before, after in zip(frames, frames[1:]):
        assert after.winfo_x() >= before.winfo_x() + before.winfo_width()
    last = frames[-1]
    assert last.winfo_x() + last.winfo_width() == pytest.approx(
        paned.winfo_width(), abs=1
    )
    assert all(f.winfo_height() == paned.winfo_height() for f in frames)


def test_vertical_orientation_stacks_the_panes(root):
    window = ctk.Panedwindow(root, orient="vertical")
    window.pack(fill="both", expand=True)
    frames = make_panes(window, 2)
    for frame in frames:
        window.add(frame, weight=1)
    settle(root)
    assert frames[1].winfo_y() > frames[0].winfo_y()
    assert frames[0].winfo_width() == window.winfo_width()


def test_insert_and_forget(paned):
    extra = ctk.Frame(paned)
    paned.insert(1, extra)
    assert paned.panes()[1] is extra
    paned.forget(extra)
    assert paned.panes() == paned.frames
    assert extra.winfo_exists()
    paned.remove(0)
    assert paned.panes() == paned.frames[1:]


def test_sashes_are_between_the_panes(paned):
    assert len(paned._sashes) == 2
    paned.forget(paned.frames[0])
    assert len(paned._sashes) == 1
    paned.forget(paned.frames[1])
    assert paned._sashes == []


def test_weights_share_the_extra_space(root):
    window = ctk.Panedwindow(root)
    window.pack(fill="both", expand=True)
    fixed, growing = make_panes(window, 2)
    window.add(fixed, weight=0)
    window.add(growing, weight=1)
    settle(root)
    before = fixed.winfo_width()
    root.geometry("900x500+0+0")
    settle(root)
    assert fixed.winfo_width() == before
    assert growing.winfo_width() > 200


def test_paneconfigure_changes_the_weight(paned):
    paned.paneconfigure(paned.frames[0], weight=5)
    assert paned._panes[0]["weight"] == 5
    paned.pane(1, weight=2)
    assert paned._panes[1]["weight"] == 2


def test_sashpos_reads_and_sets_the_position(paned):
    position = paned.sashpos(0)
    paned.sashpos(0, position + 40)
    settle(paned)
    assert paned.sashpos(0) == pytest.approx(position + 40, abs=2)
    assert paned.frames[0].winfo_width() == pytest.approx(position + 40, abs=2)


def test_panes_cannot_be_dragged_smaller_than_the_minimum(paned):
    paned.sashpos(0, 0)
    settle(paned)
    assert paned.frames[0].winfo_width() >= ctk.Panedwindow.MINIMUM_PANE_SIZE - 1
    paned.sashpos(0, 100000)
    settle(paned)
    assert paned.frames[1].winfo_width() >= ctk.Panedwindow.MINIMUM_PANE_SIZE - 1


def test_dragging_a_sash_with_the_mouse(paned):
    sash = paned._sashes[0]
    before = paned.frames[0].winfo_width()
    x = sash.winfo_rootx() + 3
    y = sash.winfo_rooty() + 20
    sash.event_generate("<ButtonPress-1>", x=3, y=20, rootx=x, rooty=y)
    sash.event_generate("<B1-Motion>", x=33, y=20, rootx=x + 30, rooty=y)
    sash.event_generate("<ButtonRelease-1>", x=33, y=20, rootx=x + 30, rooty=y)
    settle(paned)
    assert paned.frames[0].winfo_width() > before


def test_panedwindow_asks_for_the_size_its_panes_need(root):
    window = ctk.Panedwindow(root)
    window.pack()
    frame = ctk.Frame(window)
    ctk.Label(frame, "a wide enough label for the pane").pack()
    window.add(frame)
    settle(root, 5)
    assert window.winfo_reqwidth() >= frame.winfo_reqwidth()


def test_panedwindow_color_options(root):
    window = ctk.Panedwindow(root, sash_color="#101010", grip_active_color="#202020")
    assert window.cget("sash_color") == "#101010"
    window.configure(sash_color="#303030")
    assert window.cget("sash_color") == "#303030"


# ---- dragging the panes of a Panedwindow ----------------------------------------------
def test_panedwindow_is_not_draggable_by_default(paned):
    assert paned.draggable is False


def test_move_reorders_panes_and_the_sizes_stay_with_the_places(root):
    window = ctk.Panedwindow(root)
    window.pack(fill="both", expand=True)
    first, second, third = make_panes(window, 3)
    for frame in (first, second, third):
        window.add(frame, weight=1)
    settle(root)
    window.sashpos(0, 100)
    sizes = [r["size"] for r in window._panes]
    window.move(first, "end")
    assert window.panes() == [second, third, first]
    assert [r["size"] for r in window._panes] == sizes
    window.move(2, 0)
    assert window.panes() == [first, second, third]


def test_dragging_a_pane_by_its_frame_moves_it(root):
    window = ctk.Panedwindow(root, draggable=True)
    window.pack(fill="both", expand=True)
    frames = make_panes(window, 3)
    for frame in frames:
        window.add(frame, weight=1)
    settle(root)
    events = []
    window.bind("<<PanedwindowPaneMoved>>", lambda e: events.append(1))
    start_x = frames[0].winfo_rootx() + 10
    target_x = frames[2].winfo_rootx() + 10
    y = frames[0].winfo_rooty() + 20
    frames[0].event_generate("<ButtonPress-1>", x=10, y=20, rootx=start_x, rooty=y)
    for x in range(start_x, target_x + 1, 10):
        frames[0].event_generate("<B1-Motion>", x=10, y=20, rootx=x, rooty=y)
    frames[0].event_generate("<ButtonRelease-1>", x=10, y=20, rootx=target_x, rooty=y)
    settle(root)
    assert window.panes()[-1] is frames[0]
    assert events == [1]


def test_a_short_press_is_not_a_drag(root):
    window = ctk.Panedwindow(root, draggable=True)
    window.pack(fill="both", expand=True)
    frames = make_panes(window, 2)
    for frame in frames:
        window.add(frame, weight=1)
    settle(root)
    x = frames[0].winfo_rootx() + 10
    y = frames[0].winfo_rooty() + 20
    frames[0].event_generate("<ButtonPress-1>", x=10, y=20, rootx=x, rooty=y)
    frames[0].event_generate("<B1-Motion>", x=12, y=20, rootx=x + 2, rooty=y)
    frames[0].event_generate("<ButtonRelease-1>", x=12, y=20, rootx=x + 2, rooty=y)
    assert window.panes() == frames


def test_a_press_on_a_child_of_a_frame_handle_pane_does_nothing(root):
    window = ctk.Panedwindow(root, draggable=True)
    window.pack(fill="both", expand=True)
    frame = ctk.Frame(window)
    label = ctk.Label(frame, "inside")
    label.pack()
    window.add(frame)
    assert window._pressed_pane(label) is None  # the default handle is 'frame'
    assert window._pressed_pane(frame) is frame


def test_handle_all_picks_up_children(root):
    window = ctk.Panedwindow(root, draggable=True)
    frame = ctk.Frame(window)
    label = ctk.Label(frame, "inside")
    window.add(frame, handle="all")
    assert window._pressed_pane(label) is frame
    assert window._pressed_pane(frame) is frame


def test_handle_can_be_a_widget(root):
    window = ctk.Panedwindow(root, draggable=True)
    frame = ctk.Frame(window)
    title = ctk.Label(frame, "title")
    body = ctk.Label(frame, "body")
    window.add(frame, handle=title)
    assert window._pressed_pane(title) is frame
    assert window._pressed_pane(body) is None
    assert window._pressed_pane(frame) is None


def test_handle_can_be_a_list_with_frame_and_widgets(root):
    window = ctk.Panedwindow(root, draggable=True)
    frame = ctk.Frame(window)
    title = ctk.Label(frame, "title")
    body = ctk.Label(frame, "body")
    window.add(frame, handle=["frame", title])
    assert window._pressed_pane(title) is frame
    assert window._pressed_pane(frame) is frame
    assert window._pressed_pane(body) is None
    assert window.pane_handle(frame) == ("frame", title)


def test_a_widget_inside_a_handle_widget_counts_too(root):
    window = ctk.Panedwindow(root, draggable=True)
    frame = ctk.Frame(window)
    bar = ctk.Frame(frame)
    icon = ctk.Label(bar, "i")
    window.add(frame, handle=bar)
    assert window._pressed_pane(icon) is frame


def test_pane_handle_getter_setter_and_validation(root):
    window = ctk.Panedwindow(root)
    frame = ctk.Frame(window)
    window.add(frame)
    assert window.pane_handle(frame) == "frame"
    assert window.pane_handle(0, "all") == "all"
    window.paneconfigure(frame, handle="frame")
    assert window.pane_handle(frame) == "frame"
    with pytest.raises(ValueError):
        window.pane_handle(frame, "nothing")
    with pytest.raises(ValueError):
        window.pane_handle(frame, [])
    with pytest.raises(ValueError):
        window.add(ctk.Frame(window), handle=42)


def test_forgetting_a_pane_forgets_its_handle(root):
    window = ctk.Panedwindow(root)
    frame = ctk.Frame(window)
    window.add(frame, handle="all")
    window.forget(frame)
    assert str(frame) not in window._pane_handles


def test_sashes_are_never_handles(root):
    window = ctk.Panedwindow(root, draggable=True)
    first, second = make_panes(window, 2)
    window.add(first, handle="all")
    window.add(second, handle="all")
    assert window._pressed_pane(window._sashes[0]) is None


def test_draggable_can_be_changed_later(root):
    window = ctk.Panedwindow(root)
    window.configure(draggable=True)
    assert window.draggable is True
    assert window.cget("draggable") is True


def test_destroying_the_panedwindow_removes_the_window_bindings(root):
    before = root.bind("<ButtonPress-1>")
    window = ctk.Panedwindow(root, draggable=True)
    assert root.bind("<ButtonPress-1>") != before
    window.destroy()
    assert root.bind("<ButtonPress-1>").strip() == before.strip()


# ---- GridPanedwindow -----------------------------------------------------------------
@pytest.fixture
def grid(root):
    window = ctk.GridPanedwindow(root)
    window.pack(fill="both", expand=True)
    window.a, window.b, window.c = make_panes(window, 3)
    window.add(window.a)
    window.split(window.a, window.b, "horizontal")
    window.split(window.b, window.c, "vertical")
    settle(root)
    return window


def rect(widget):
    return (
        widget.winfo_x(),
        widget.winfo_y(),
        widget.winfo_width(),
        widget.winfo_height(),
    )


def test_grid_layout_of_a_split_in_both_directions(grid):
    ax, ay, aw, ah = rect(grid.a)
    bx, by, bw, bh = rect(grid.b)
    cx, cy, cw, ch = rect(grid.c)
    assert (ax, ay) == (0, 0) and ah == grid.winfo_height()
    assert bx >= aw and by == 0
    assert cx == bx and cy >= bh and cw == bw
    assert cy + ch == grid.winfo_height()


def test_panes_are_listed_in_layout_order(grid):
    assert grid.panes() == [grid.a, grid.b, grid.c]


def test_split_before_and_ratio(root):
    window = ctk.GridPanedwindow(root)
    window.pack(fill="both", expand=True)
    first, second = make_panes(window, 2)
    window.add(first)
    window.split(first, second, "horizontal", before=True, ratio=0.25)
    settle(root)
    assert window.panes() == [second, first]
    assert second.winfo_width() < first.winfo_width()


def test_add_appends_to_the_whole_layout(root):
    window = ctk.GridPanedwindow(root)
    window.pack(fill="both", expand=True)
    panes = make_panes(window, 4)
    window.add(panes[0])
    window.add(panes[1])
    window.add(panes[2], "vertical")
    window.add(panes[3], "vertical")
    settle(root)
    assert panes[1].winfo_x() > panes[0].winfo_x()
    assert panes[2].winfo_y() > panes[0].winfo_y()
    assert panes[3].winfo_y() > panes[2].winfo_y()
    assert panes[2].winfo_width() == window.winfo_width()


def test_split_of_an_unknown_pane_raises(grid):
    with pytest.raises(tk.TclError):
        grid.split(ctk.Frame(grid), ctk.Frame(grid))


def test_remove_gives_the_space_to_the_neighbors_and_collapses_splits(grid):
    grid.remove(grid.c)
    settle(grid)
    assert grid.panes() == [grid.a, grid.b]
    assert grid.b.winfo_height() == grid.winfo_height()
    assert grid.c.winfo_exists() and not grid.c.winfo_ismapped()
    grid.remove(grid.a)
    settle(grid)
    assert grid.panes() == [grid.b]
    assert isinstance(grid._pane_tree, containers._PaneLeaf)
    grid.remove(grid.b)
    assert grid._pane_tree is None and grid.panes() == []


def test_sashes_follow_the_splits(grid):
    splits = grid._splits()
    assert len(splits) == 2
    assert all(len(split.sashes) == len(split.children) - 1 for split in splits)
    grid.remove(grid.c)
    assert len(grid._splits()) == 1


def test_fractions_always_add_up_to_one(grid):
    for split in grid._splits():
        assert sum(split.fractions) == pytest.approx(1.0)
    grid.remove(grid.b)
    for split in grid._splits():
        assert sum(split.fractions) == pytest.approx(1.0)


def test_swap_exchanges_places_and_keeps_the_sizes(grid):
    a_rect, c_rect = rect(grid.a), rect(grid.c)
    grid.swap(grid.a, grid.c)
    settle(grid)
    assert rect(grid.c) == a_rect
    assert rect(grid.a) == c_rect
    assert grid.panes() == [grid.c, grid.b, grid.a]


def test_removing_a_pane_in_a_nested_same_direction_split_merges_it(root):
    window = ctk.GridPanedwindow(root)
    window.pack(fill="both", expand=True)
    a, b, c, d = make_panes(window, 4)
    window.add(a)
    window.split(a, b, "horizontal")
    window.split(b, c, "vertical")
    window.split(c, d, "horizontal")  # a | (b over (c | d))
    settle(root)
    window.remove(b)  # leaves a | (c | d): the inner row merges into the outer one
    settle(root)
    assert window.panes() == [a, c, d]
    root_split = window._pane_tree
    assert isinstance(root_split, containers._PaneSplit)
    assert len(root_split.children) == 3
    assert all(isinstance(child, containers._PaneLeaf) for child in root_split.children)
    assert sum(root_split.fractions) == pytest.approx(1.0)


def test_grid_sash_drag_changes_the_fractions(grid):
    split = grid._tree_root = grid._pane_tree
    before = list(split.fractions)
    sash = split.sashes[0]
    x = sash.winfo_rootx() + 3
    y = sash.winfo_rooty() + 10
    split.drag_sash(0, x + 40)
    settle(grid)
    assert split.fractions[0] > before[0]
    assert sum(split.fractions) == pytest.approx(1.0)


def test_junctions_are_found_where_sashes_meet(grid):
    settle(grid)
    assert grid._junctions
    junction = grid._junctions[0]
    assert junction["partners"]


def test_grid_color_options_and_theme(root):
    window = ctk.GridPanedwindow(root, sash_color="#101010")
    assert window.cget("sash_color") == "#101010"
    window.set_theme({"separator": "#ff0000"})
    window.reset_theme()
    assert window.cget("sash_color") == "#101010"


# ---- dragging panes of a GridPanedwindow: zones and docking -------------------------------
@pytest.fixture
def docking(root):
    """A | (B over C), draggable, with every pane a plain frame."""
    window = ctk.GridPanedwindow(root, draggable=True)
    window.pack(fill="both", expand=True)
    window.a, window.b, window.c = make_panes(window, 3)
    window.add(window.a)
    window.split(window.a, window.b, "horizontal")
    window.split(window.b, window.c, "vertical")
    settle(root)
    return window


def center_of(widget):
    return (
        widget.winfo_rootx() + widget.winfo_width() // 2,
        widget.winfo_rooty() + widget.winfo_height() // 2,
    )


def test_drop_zone_in_the_middle_of_a_pane_is_a_swap(docking):
    x, y = center_of(docking.b)
    target, side, rect_ = docking._drop_zone(docking.c, x, y)
    assert target is docking.b and side == "center"


def test_drop_zone_near_a_side_of_a_pane(docking):
    left = docking.b.winfo_rootx() + 5
    _, y = center_of(docking.b)
    target, side, _ = docking._drop_zone(docking.c, left, y)
    assert target is docking.b and side == "left"
    right = docking.b.winfo_rootx() + docking.b.winfo_width() - 5
    assert docking._drop_zone(docking.c, right, y)[1] == "right"
    x, _ = center_of(docking.b)
    top = docking.b.winfo_rooty() + 5
    assert docking._drop_zone(docking.c, x, top)[1] == "top"


def test_drop_zone_near_the_border_docks_along_the_whole_side(docking):
    y = docking.winfo_rooty() + docking.winfo_height() // 2
    x = docking.winfo_rootx() + 3
    target, side, rect_ = docking._drop_zone(docking.c, x, y)
    assert target is None and side == "left"
    assert rect_[3] == docking.winfo_height()
    x, _ = center_of(docking.a)
    bottom = docking.winfo_rooty() + docking.winfo_height() - 3
    target, side, rect_ = docking._drop_zone(docking.c, x, bottom)
    assert target is None and side == "bottom"
    assert rect_[2] == docking.winfo_width()


def test_no_drop_zone_over_the_dragged_pane_or_outside(docking):
    x, y = center_of(docking.c)
    assert docking._drop_zone(docking.c, x, y) is None
    assert docking._drop_zone(docking.c, -500, -500) is None


def test_no_drop_zone_with_a_single_pane(root):
    window = ctk.GridPanedwindow(root)
    window.pack(fill="both", expand=True)
    only = ctk.Frame(window)
    window.add(only)
    settle(root)
    assert window._drop_zone(only, *center_of(only)) is None


def test_dropping_in_the_middle_swaps(docking):
    x, y = center_of(docking.a)
    assert docking._drop_pane(docking.c, x, y) is True
    settle(docking)
    assert docking.panes() == [docking.c, docking.b, docking.a]


def test_dropping_c_on_the_bottom_border_docks_it_under_everything(docking):
    x, _ = center_of(docking.a)
    bottom = docking.winfo_rooty() + docking.winfo_height() - 3
    assert docking._drop_pane(docking.c, x, bottom) is True
    settle(docking)
    a, b, c = (rect(f) for f in (docking.a, docking.b, docking.c))
    assert c[0] == 0 and c[2] == docking.winfo_width()  # C is full width
    assert c[1] > a[1] and c[1] > b[1]  # below A and B
    assert a[0] < b[0]  # A | B on top
    assert docking.panes() == [docking.a, docking.b, docking.c]
    root_split = docking._pane_tree
    assert root_split.orient == "vertical" and len(root_split.children) == 2


def test_dropping_beside_a_pane_splits_it(docking):
    left = docking.a.winfo_rootx() + 5
    _, y = center_of(docking.a)
    assert docking._drop_pane(docking.c, left, y) is True
    settle(docking)
    assert docking.panes()[0] is docking.c
    assert rect(docking.c)[0] < rect(docking.a)[0]
    assert rect(docking.c)[3] == rect(docking.a)[3]


def test_dropping_above_a_pane_in_another_column_makes_a_new_row(docking):
    x, _ = center_of(docking.a)
    top = docking.a.winfo_rooty() + 5
    assert docking._drop_pane(docking.c, x, top) is True
    settle(docking)
    assert rect(docking.c)[1] < rect(docking.a)[1]
    assert docking.panes()[0] is docking.c


def test_dropping_nowhere_changes_nothing(docking):
    before = docking.panes()
    assert docking._drop_pane(docking.c, -300, -300) is False
    assert docking.panes() == before


def test_dock_share_is_half_or_equal(docking):
    leaf = docking._leaf_of(docking.c)
    assert docking._dock_share("vertical", leaf) == 0.5
    assert docking._dock_share("horizontal", leaf) == pytest.approx(1 / 3)
    four = ctk.Frame(docking)
    docking.add(four)  # root is now a horizontal row of three
    settle(docking)
    assert docking._dock_share("horizontal") == pytest.approx(1 / 4)


def test_drag_over_shows_an_outline_and_drop_hides_it(docking):
    x, y = center_of(docking.a)
    docking._drag_over(docking.c, x, y)
    settle(docking)
    assert any(edge.winfo_manager() == "place" for edge in docking._drop_outline)
    docking._end_pane_drag()
    assert all(edge.winfo_manager() == "" for edge in docking._drop_outline)


def test_the_whole_drag_with_the_mouse_docks_the_pane(docking):
    c = docking.c
    start_x, start_y = center_of(c)
    x_target, _ = center_of(docking.a)
    y_target = docking.winfo_rooty() + docking.winfo_height() - 3
    events = []
    docking.bind("<<PanedwindowPaneMoved>>", lambda e: events.append(1))
    c.event_generate("<ButtonPress-1>", x=5, y=5, rootx=start_x, rooty=start_y)
    for step in range(1, 11):
        x = start_x + (x_target - start_x) * step // 10
        y = start_y + (y_target - start_y) * step // 10
        c.event_generate("<B1-Motion>", x=5, y=5, rootx=x, rooty=y)
        settle(docking, 1)
    c.event_generate("<ButtonRelease-1>", x=5, y=5, rootx=x_target, rooty=y_target)
    settle(docking)
    assert rect(c)[2] == docking.winfo_width()
    assert events == [1]
    assert all(edge.winfo_manager() == "" for edge in docking._drop_outline)


def test_grid_handles_work_like_the_panedwindows(root):
    window = ctk.GridPanedwindow(root, draggable=True)
    first, second = make_panes(window, 2)
    title = ctk.Label(second, "title")
    window.add(first, handle="all")
    window.split(first, second, handle=[title, "frame"])
    assert window.pane_handle(first) == "all"
    assert window.pane_handle(second) == (title, "frame")
    assert window._pressed_pane(title) is second
    window.remove(first)
    assert str(first) not in window._pane_handles
    with pytest.raises(ValueError):
        window.add(ctk.Frame(window), handle="bogus")


def test_a_draggable_grid_can_be_turned_off_later(docking):
    docking.configure(draggable=False)
    docking._pane_drag = None
    docking._on_pane_press(
        type("E", (), {"widget": docking.a, "x_root": 1, "y_root": 1})()
    )
    assert docking._pane_drag is None
