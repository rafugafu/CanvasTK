"""Frame, ScrolledFrame, Foldable, LabelFrame, and Notebook."""

import tkinter as tk

import pytest

import canvastk as ctk

from conftest import settle


def size_of(widget):
    settle(widget)
    return widget.winfo_width(), widget.winfo_height()


# ---- Frame ------------------------------------------------------------------------------
def test_frame_is_a_tk_frame_and_holds_widgets(root):
    frame = ctk.Frame(root)
    frame.pack()
    label = ctk.Label(frame, "inside")
    label.pack()
    settle(root)
    assert isinstance(frame, tk.Frame)
    assert label.master is frame
    assert frame.winfo_reqwidth() >= label.winfo_reqwidth()


def test_frame_fixed_background(root):
    frame = ctk.Frame(root, bg="#445566")
    frame.pack()
    ctk.set_appearance_mode("dark")
    settle(root)
    assert frame.cget("bg").lower() == "#445566"
    child = ctk.Frame(frame)
    assert child.cget("bg").lower() == "#445566"  # inner frames blend into it


def test_frame_inside_a_plain_tk_frame_measures_the_color(root):
    plain = tk.Frame(root, bg="#102030")
    plain.pack()
    inner = ctk.Frame(plain)
    assert inner.cget("bg").lower() == "#102030"


# ---- ScrolledFrame -----------------------------------------------------------------------
def test_scrolled_frame_content_is_the_frame_itself(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    label = ctk.Label(scrolled, "inside")
    label.pack()
    settle(root)
    assert label.master is scrolled
    assert scrolled.outer.winfo_ismapped()


def test_scrolled_frame_geometry_goes_to_the_outer_container(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    settle(root)
    assert scrolled.outer.winfo_manager() == "pack"
    assert scrolled.pack_info()["fill"] == "both"


def test_scrolled_frame_scrolls_tall_content(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    for number in range(60):
        ctk.Label(scrolled, f"line {number}").pack(anchor="w")
    settle(root)
    first, last = scrolled.viewport.yview()
    assert first == 0 and last < 1
    scrolled.viewport.yview_moveto(0.5)
    assert scrolled.viewport.yview()[0] > 0.3


def test_scrolled_frame_content_keeps_its_natural_size(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    for number in range(60):
        ctk.Label(scrolled, f"line {number}").pack(anchor="w")
    settle(root)
    assert scrolled.winfo_height() > scrolled.outer.winfo_height()


def test_scrolled_frame_short_content_does_not_scroll(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    ctk.Label(scrolled, "one").pack()
    settle(root)
    assert scrolled.viewport.yview() == (0.0, 1.0)


def test_scrolled_frame_orient_is_checked(root):
    for orient in ("vertical", "horizontal", "both"):
        ctk.ScrolledFrame(root, orient=orient)
    with pytest.raises(ValueError):
        ctk.ScrolledFrame(root, orient="sideways")


def test_scrolled_frame_destroy_removes_the_outer_container(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack()
    outer = scrolled.outer
    scrolled.destroy()
    assert not outer.winfo_exists()


def test_scrolled_frame_wheel_scrolls_the_frame_under_the_pointer(root):
    scrolled = ctk.ScrolledFrame(root)
    scrolled.pack(fill="both", expand=True)
    for number in range(80):
        ctk.Label(scrolled, f"line {number}").pack(anchor="w")
    settle(root)
    before = scrolled.viewport.yview()[0]
    x = scrolled.viewport.winfo_rootx() + 20
    y = scrolled.viewport.winfo_rooty() + 20
    scrolled.viewport.event_generate("<Button-5>", rootx=x, rooty=y, x=20, y=20)
    settle(root)
    assert scrolled.viewport.yview()[0] > before


def test_nested_scrolled_frames_scroll_the_inner_then_the_outer(root):
    outer = ctk.ScrolledFrame(root)
    outer.pack(fill="both", expand=True)
    inner = ctk.ScrolledFrame(outer)
    inner.pack(fill="x")
    inner.outer.configure(height=100)
    for number in range(40):
        ctk.Label(inner, f"inner {number}").pack(anchor="w")
    for number in range(40):
        ctk.Label(outer, f"outer {number}").pack(anchor="w")
    settle(root)
    assert inner.viewport.yview()[1] < 1


# ---- Foldable ------------------------------------------------------------------------------
def test_foldable_starts_open_unless_told_otherwise(root):
    default = ctk.Foldable(root, "Default")
    folded = ctk.Foldable(root, "Closed", expanded=False)
    assert default.is_expanded()
    assert not folded.is_expanded()


def test_foldable_expand_collapse_toggle_and_event(root):
    calls, events = [], []
    foldable = ctk.Foldable(root, "T", expanded=False, command=calls.append)
    foldable.pack()
    foldable.bind("<<FoldableToggled>>", lambda e: events.append(1))
    settle(root)
    foldable.expand()
    settle(root)
    assert foldable.is_expanded() and calls == [True]
    foldable.expand()
    assert calls == [True]  # no change, no call
    foldable.collapse()
    settle(root)
    assert calls == [True, False]
    foldable.toggle()
    settle(root)
    assert foldable.is_expanded()
    assert len(events) == 3  # also the one of the very first expand


def test_foldable_quiet_changes(root):
    calls = []
    foldable = ctk.Foldable(root, "T", expanded=False, command=calls.append)
    foldable.expand(notify=False)
    foldable.collapse(notify=False)
    assert calls == []


def test_foldable_shows_and_hides_its_contents(root):
    foldable = ctk.Foldable(root, "T", expanded=False)
    foldable.pack(fill="x")
    label = ctk.Label(foldable, "content")
    label.pack()
    settle(root)
    assert not label.winfo_viewable()
    foldable.expand()
    settle(root)
    assert label.winfo_viewable()
    foldable.collapse()
    settle(root)
    assert not label.winfo_viewable()


def test_foldable_text_font_and_state(root):
    foldable = ctk.Foldable(root, "Title")
    assert foldable.text == "Title"
    foldable.text = "New"
    assert foldable.text == "New"
    foldable.text = 5
    assert foldable.text == "5"
    foldable.font = ("TkDefaultFont", 14)
    assert foldable.font is not None
    assert foldable.state == "normal"
    foldable.state = "disabled"
    assert foldable.state == "disabled"
    with pytest.raises(ValueError):
        ctk.Foldable(root, "x", state="broken")


def test_foldable_scrolled_limits_its_height(root):
    foldable = ctk.Foldable(root, "T", scrolled=True, max_height=120, expanded=True)
    foldable.pack(fill="x")
    for number in range(50):
        ctk.Label(foldable, f"line {number}").pack(anchor="w")
    settle(root)
    assert foldable.viewport.winfo_height() <= 130
    assert foldable.viewport.yview()[1] < 1


def test_foldable_scrolled_orient_is_checked(root):
    with pytest.raises(ValueError):
        ctk.Foldable(root, "x", scrolled=True, orient="diagonal")


def test_foldable_destroy_removes_everything(root):
    foldable = ctk.Foldable(root, "T")
    foldable.pack()
    outer = foldable.outer
    foldable.destroy()
    assert not outer.winfo_exists()


# ---- LabelFrame ----------------------------------------------------------------------------
def test_labelframe_text_and_font(root):
    box = ctk.LabelFrame(root, "Group")
    box.pack()
    assert box.text == "Group"
    box.text = "Other"
    assert box.text == "Other"
    box.text = 3
    assert box.text == "3"
    box.font = ("TkDefaultFont", 12)


def test_labelframe_holds_children_and_is_big_enough(root):
    box = ctk.LabelFrame(root, "Group", padding=10)
    box.pack()
    label = ctk.Label(box, "a fairly long label inside the box")
    label.pack()
    settle(root)
    assert box.outer.winfo_reqwidth() >= label.winfo_reqwidth()
    assert box.outer.winfo_reqheight() > label.winfo_reqheight()


def test_labelframe_without_text_has_no_title_gap(root):
    titled = ctk.LabelFrame(root, "Group")
    untitled = ctk.LabelFrame(root, "")
    for box in (titled, untitled):
        box.pack()
        ctk.Label(box, "x").pack()
    settle(root)
    assert titled.outer.winfo_reqheight() >= untitled.outer.winfo_reqheight()


def test_labelframe_scrolled(root):
    box = ctk.LabelFrame(root, "G", scrolled=True, max_height=100)
    box.pack(fill="x")
    for number in range(50):
        ctk.Label(box, f"line {number}").pack(anchor="w")
    settle(root)
    assert box.viewport.yview()[1] < 1


def test_labelframe_destroy(root):
    box = ctk.LabelFrame(root, "G")
    box.pack()
    outer = box.outer
    box.destroy()
    assert not outer.winfo_exists()


# ---- Notebook ------------------------------------------------------------------------------
@pytest.fixture
def notebook(root):
    book = ctk.Notebook(root)
    book.pack(fill="both", expand=True)
    pages = [ctk.Frame(book) for _ in range(3)]
    for number, page in enumerate(pages):
        ctk.Label(page, f"page {number}").pack()
        book.add(page, text=f"Tab {number}")
    settle(root)
    book.pages = pages
    return book


def test_first_added_tab_is_selected_and_shown(notebook):
    pages = notebook.pages
    assert notebook.select() is pages[0]
    assert pages[0].winfo_ismapped()
    assert not pages[1].winfo_ismapped()
    assert notebook.tabs() == pages


def test_select_changes_the_page_and_generates_the_event(notebook):
    events = []
    notebook.bind("<<NotebookTabChanged>>", lambda e: events.append(notebook.select()))
    settle(notebook)
    notebook.select(2)
    settle(notebook)
    assert notebook.select() is notebook.pages[2]
    assert notebook.pages[2].winfo_ismapped()
    assert not notebook.pages[0].winfo_ismapped()
    assert events == [notebook.pages[2]]


def test_select_by_page_and_by_name(notebook):
    notebook.select(notebook.pages[1])
    assert notebook.select() is notebook.pages[1]
    notebook.select(str(notebook.pages[2]))
    assert notebook.select() is notebook.pages[2]
    notebook.select("current")
    assert notebook.index("current") == 2


def test_selecting_the_same_tab_generates_no_event(notebook):
    events = []
    notebook.bind("<<NotebookTabChanged>>", lambda e: events.append(1))
    settle(notebook)
    notebook.select(0)
    settle(notebook)
    assert events == []


def test_unknown_tab_raises(notebook):
    with pytest.raises(tk.TclError):
        notebook.select(ctk.Frame(notebook))


def test_insert_puts_a_tab_in_the_middle(notebook, root):
    extra = ctk.Frame(notebook)
    notebook.insert(1, extra, text="Between")
    assert notebook.tabs()[1] is extra
    assert notebook.index(extra) == 1
    assert notebook.select() is notebook.pages[0]  # the selection does not move


def test_tab_options(notebook):
    page = notebook.pages[1]
    assert notebook.tab(page, "text") == "Tab 1"
    notebook.tab(page, text="Renamed")
    assert notebook.tab(1, "text") == "Renamed"
    notebook.tab(page, text=12)
    assert notebook.tab(page, "text") == "12"
    assert notebook.tab(page)["state"] == "normal"
    notebook.tab(page, tooltip="Hint")
    assert notebook.tab(page, "tooltip") == "Hint"


def test_tab_text_can_be_a_number_when_added(root):
    book = ctk.Notebook(root)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text=7)
    assert book.tab(page, "text") == "7"


def test_disabled_tab_cannot_be_selected(notebook):
    notebook.tab(1, state="disabled")
    notebook.select(1)
    assert notebook.select() is notebook.pages[0]


def test_disabling_the_selected_tab_selects_a_neighbor(notebook):
    notebook.tab(0, state="disabled")
    assert notebook.select() is notebook.pages[1]


def test_hide_and_show_a_tab(notebook):
    notebook.hide(1)
    settle(notebook)
    assert notebook.tab(1, "state") == "hidden"
    assert len(notebook._tab_boxes) == 2
    notebook.tab(1, state="normal")
    settle(notebook)
    assert len(notebook._tab_boxes) == 3


def test_forget_keeps_the_page_and_selects_another(notebook):
    page = notebook.pages[0]
    notebook.forget(page)
    assert page.winfo_exists() and not page.winfo_ismapped()
    assert notebook.select() is notebook.pages[1]
    assert len(notebook.tabs()) == 2


def test_forgetting_the_only_tab_leaves_nothing_selected(root):
    book = ctk.Notebook(root)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="x")
    book.forget(page)
    assert book.select() is None


def test_closable_tabs_and_close_tab(notebook):
    events = []
    notebook.bind("<<NotebookTabClosed>>", lambda e: events.append(1))
    settle(notebook)
    assert not notebook.is_closable(0)
    notebook.configure(closable=True)
    assert notebook.is_closable(0)
    page = notebook.pages[1]
    notebook.close_tab(page)
    settle(notebook)
    assert not page.winfo_exists()  # destroyed with its tab
    assert len(notebook.tabs()) == 2
    assert events == [1]


def test_a_tab_can_override_closable(root):
    book = ctk.Notebook(root, closable=True)
    book.pack()
    keep, close = ctk.Frame(book), ctk.Frame(book)
    book.add(keep, text="a", closable=False)
    book.add(close, text="b")
    assert not book.is_closable(keep)
    assert book.is_closable(close)


def test_disabled_tabs_have_no_close_button(root):
    book = ctk.Notebook(root, closable=True)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="a", state="disabled")
    assert not book.is_closable(page)


def test_on_close_can_veto(root):
    answers = []
    book = ctk.Notebook(root, on_close=lambda page: answers.append(page) or False)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="a")
    book.close_tab(page)
    assert answers == [page]
    assert book.tabs() == [page] and page.winfo_exists()


def test_destroy_on_close_can_be_turned_off(root):
    book = ctk.Notebook(root, destroy_on_close=False)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="a")
    book.close_tab(page)
    assert page.winfo_exists() and book.tabs() == []


def test_move_reorders_tabs_and_keeps_the_selection(notebook):
    selected = notebook.select()
    notebook.move(notebook.pages[0], "end")
    assert notebook.tabs() == [notebook.pages[1], notebook.pages[2], notebook.pages[0]]
    assert notebook.select() is selected
    notebook.move(2, 0)
    assert notebook.tabs()[0] is notebook.pages[0]


def test_dragging_a_tab_reorders_it_and_generates_the_event(root):
    book = ctk.Notebook(root, draggable=True)
    book.pack(fill="both", expand=True)
    pages = [ctk.Frame(book) for _ in range(3)]
    for number, page in enumerate(pages):
        book.add(page, text=f"Tab {number}")
    settle(root)
    events = []
    book.bind("<<NotebookTabMoved>>", lambda e: events.append(1))
    first = book._tab_boxes[0]
    last = book._tab_boxes[-1]
    y = book.tab_height // 2
    start = int((first[0] + first[1]) // 2)
    end = int((last[0] + last[1]) // 2) + 20
    book.chrome.event_generate("<ButtonPress-1>", x=start, y=y)
    for x in range(start, end, 6):
        book.chrome.event_generate("<B1-Motion>", x=x, y=y)
        settle(root, 1)
    book.chrome.event_generate("<ButtonRelease-1>", x=end, y=y)
    settle(root)
    assert book.tabs()[-1] is pages[0]
    assert events == [1]


def test_dragging_does_nothing_unless_draggable(notebook):
    first = int(notebook._tab_boxes[0][0])
    y = notebook.tab_height // 2
    notebook.chrome.event_generate("<ButtonPress-1>", x=first + 10, y=y)
    for x in range(first + 10, first + 200, 10):
        notebook.chrome.event_generate("<B1-Motion>", x=x, y=y)
    notebook.chrome.event_generate("<ButtonRelease-1>", x=first + 200, y=y)
    assert notebook.tabs() == notebook.pages


def test_clicking_a_tab_selects_it(notebook):
    box = notebook._tab_boxes[1]
    y = notebook.tab_height // 2
    notebook.chrome.event_generate("<ButtonPress-1>", x=(box[0] + box[1]) // 2, y=y)
    notebook.chrome.event_generate("<ButtonRelease-1>", x=(box[0] + box[1]) // 2, y=y)
    settle(notebook)
    assert notebook.select() is notebook.pages[1]


def test_control_tab_traversal(notebook, root):
    notebook.enable_traversal()
    settle(root)
    root.focus_force()  # key events go to the window that has the focus
    root.update()
    root.event_generate("<Control-Tab>")
    assert notebook.select() is notebook.pages[1]
    root.event_generate("<Control-Tab>")
    root.event_generate("<Control-Tab>")
    assert notebook.select() is notebook.pages[0]  # wraps around


def test_control_shift_tab_selects_the_previous_tab(notebook, root):
    notebook.enable_traversal()
    notebook.select(1)
    settle(root)
    root.focus_force()
    root.update()
    root.event_generate("<Control-Shift-Tab>")
    assert notebook.select() is notebook.pages[0]


def test_arrow_keys_select_neighbors(notebook, root):
    notebook.focus_force()
    root.update()
    notebook.event_generate("<Right>")
    assert notebook.select() is notebook.pages[1]
    notebook.event_generate("<Left>")
    assert notebook.select() is notebook.pages[0]


def test_many_tabs_scroll_with_arrows(root):
    book = ctk.Notebook(root)
    book.pack(fill="x")
    root.geometry("300x300+0+0")
    for number in range(20):
        book.add(ctk.Frame(book), text=f"A long tab name {number}")
    settle(root)
    assert book._max_tab_offset > 0
    assert len(book._arrow_boxes) == 2
    book._scroll_tabs(40)
    assert book._tab_offset > 0


def test_pages_are_placed_below_the_tabs_inside_the_notebook(notebook):
    page = notebook.pages[0]
    assert page.winfo_y() >= notebook.tab_height
    assert page.winfo_width() <= notebook.winfo_width()
    assert page.winfo_height() < notebook.winfo_height()


def test_page_frames_use_the_window_color(root):
    book = ctk.Notebook(root)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="x")
    assert page.cget("bg").lower() == ctk.CANVAS_LIGHT_PALETTE["window"].lower()
    colored = ctk.Notebook(root, page_color="#112233")
    colored.pack()
    colored_page = ctk.Frame(colored)
    colored.add(colored_page, text="x")
    assert colored_page.cget("bg").lower() == "#112233"


# ---- Notebook styles ------------------------------------------------------------------------
def test_default_style_is_the_tab_style_key(root):
    book = ctk.Notebook(root)
    assert book.style == "segmented"
    ctk.set_theme({"tab_style": "classic"})
    assert book.style == "classic"


def test_own_style_wins_over_the_theme_key(root):
    book = ctk.Notebook(root, style="underline")
    ctk.set_theme({"tab_style": "classic"})
    assert book.style == "underline"
    book.configure(style=None)
    assert book.style == "classic"


@pytest.mark.parametrize("style", ["segmented", "classic", "underline"])
def test_every_style_can_be_used_and_switched_to(root, style):
    book = ctk.Notebook(root)
    book.pack(fill="both", expand=True)
    for number in range(3):
        book.add(ctk.Frame(book), text=f"T{number}", tooltip="hint")
    settle(root)
    book.configure(style=style)
    settle(root)
    assert book.style == style
    assert len(book._tab_boxes) == 3
    assert book.cget("style") == style


def test_bad_styles_are_rejected(root):
    with pytest.raises(ValueError):
        ctk.Notebook(root, style="round")
    book = ctk.Notebook(root)
    with pytest.raises(ValueError):
        book.configure(style="round")


def test_a_bad_tab_style_in_the_theme_is_reported(root):
    ctk.Notebook(root)
    with pytest.raises(ValueError):
        ctk.set_theme({"tab_style": "bogus"})
    ctk.reset_theme()


def test_underline_tabs_are_lower_and_the_page_moves_up(root):
    book = ctk.Notebook(root)
    book.pack(fill="both", expand=True)
    page = ctk.Frame(book)
    book.add(page, text="x")
    settle(root)
    segmented_height, segmented_top = book.tab_height, page.winfo_y()
    book.configure(style="underline")
    settle(root)
    assert book.tab_height < segmented_height
    assert page.winfo_y() < segmented_top


def test_switching_between_styles_restores_the_height(root):
    book = ctk.Notebook(root)
    original = book.tab_height
    book.configure(style="underline")
    book.configure(style="segmented")
    assert book.tab_height == original


def test_the_tab_style_key_changes_a_notebook_without_its_own_style(root):
    book = ctk.Notebook(root)
    book.pack(fill="both", expand=True)
    page = ctk.Frame(book)
    book.add(page, text="x")
    settle(root)
    segmented_top = page.winfo_y()
    ctk.set_theme({"tab_style": "underline"})
    settle(root)
    assert book.style == "underline"
    assert book.tab_height == book._height_of_tabs()
    assert page.winfo_y() < segmented_top
    ctk.reset_theme()
    settle(root)
    assert page.winfo_y() == segmented_top


def test_tab_radius_option_and_theme_key(root):
    book = ctk.Notebook(root)
    assert book.corner(book.tab_radius, "tab_radius") == 10
    ctk.set_theme({"tab_radius": 3})
    assert book.corner(book.tab_radius, "tab_radius") == 3
    book.configure(tab_radius=0)
    assert book.corner(book.tab_radius, "tab_radius") == 0
    assert not hasattr(book, "segment_radius")


def test_segment_radius_is_gone():
    assert "segment_radius" not in ctk.Notebook._SETTABLE_OPTIONS
    assert "tab_radius" in ctk.Notebook._SETTABLE_OPTIONS


def test_notebook_color_options(root):
    book = ctk.Notebook(
        root,
        tab_color="#101010",
        selected_tab_color="#202020",
        underline_color="#303030",
    )
    assert book.cget("tab_color") == "#101010"
    assert book.cget("selected_tab_color") == "#202020"
    assert book.cget("underline_color") == "#303030"
    book.configure(tab_color=None)
    assert book.cget("tab_color") is None


def test_notebook_settable_options(root):
    book = ctk.Notebook(root)
    book.configure(padding=20, tab_padx=30, closable=True, draggable=True)
    assert book.cget("padding") == 20
    assert book.cget("tab_padx") == 30
    assert book.cget("closable") is True
    assert book.cget("draggable") is True


def test_notebook_font_change_changes_the_tab_height(root):
    book = ctk.Notebook(root)
    small = book.tab_height
    book.configure(font=("TkDefaultFont", 30))
    assert book.tab_height > small


def test_disabling_the_selected_tab_picks_the_next_then_the_previous(notebook):
    notebook.select(1)
    notebook.tab(1, state="disabled")
    assert notebook.select() is notebook.pages[2]
    notebook.tab(2, state="hidden")
    assert notebook.select() is notebook.pages[0]


def test_disabling_the_only_usable_tab_leaves_nothing_selected(root):
    book = ctk.Notebook(root)
    book.pack()
    page = ctk.Frame(book)
    book.add(page, text="x")
    settle(root)
    book.tab(page, state="disabled")
    assert book.select() is None
    assert not page.winfo_ismapped()


def test_shift_tab_keysym_of_x11_selects_the_previous_tab(notebook, root):
    notebook.enable_traversal()
    notebook.select(2)
    settle(root)
    root.focus_force()
    root.update()
    root.event_generate("<Control-ISO_Left_Tab>")
    assert notebook.select() is notebook.pages[1]
