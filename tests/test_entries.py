"""Entry, Textbox, Combobox, and Spinbox: canvas wrappers around native tk widgets."""

import tkinter as tk

import pytest

import canvastk as ctk

from conftest import settle


# ---- the wrapping ----------------------------------------------------------------
def test_entry_wraps_a_real_tk_entry(root):
    entry = ctk.Entry(root)
    entry.pack()
    assert isinstance(entry.inner, tk.Entry)
    assert isinstance(entry, tk.Frame)
    assert entry.chrome.master is entry


def test_textbox_wraps_a_real_tk_text(root):
    textbox = ctk.Textbox(root)
    textbox.pack()
    assert isinstance(textbox.inner, tk.Text)


def test_entry_forwards_native_methods(root):
    entry = ctk.Entry(root)
    entry.pack()
    entry.insert(0, "hello")
    assert entry.get() == "hello"
    entry.delete(0, "end")
    assert entry.get() == ""
    entry.insert(0, "abc")
    entry.icursor(1)
    assert entry.index("insert") == 1
    entry.selection_range(0, 2)
    assert entry.selection_get() == "ab"
    entry.selection_clear()


def test_textbox_forwards_native_methods(root):
    textbox = ctk.Textbox(root)
    textbox.pack()
    textbox.insert("1.0", "one\ntwo\nthree")
    assert textbox.get("1.0", "end-1c") == "one\ntwo\nthree"
    assert textbox.index("end-1c") == "3.5"
    textbox.tag_configure("x", foreground="red")
    textbox.tag_add("x", "1.0", "1.3")
    assert textbox.tag_ranges("x")
    textbox.see("end")
    textbox.edit_modified(False)
    settle(root)
    assert (
        textbox.bbox("1.0") is not None
    )  # forwarded to the text widget, not the frame
    textbox.delete("1.0", "end")
    assert textbox.get("1.0", "end-1c") == ""


def test_textbox_selection_clear_and_image_names_are_forwarded(root):
    textbox = ctk.Textbox(root)
    textbox.pack()
    textbox.insert("1.0", "text")
    textbox.tag_add("sel", "1.0", "1.2")
    textbox.selection_clear()
    assert not textbox.tag_ranges("sel")
    assert not textbox.image_names()


def test_focus_goes_to_the_inner_widget(root):
    entry = ctk.Entry(root)
    entry.pack()
    settle(root)
    entry.focus_force()
    root.update()
    assert root.focus_get() is entry.inner


def test_bind_goes_to_the_inner_widget_but_frame_events_stay(root):
    entry = ctk.Entry(root)
    entry.pack()
    seen = []
    entry.bind("<KeyPress-a>", lambda e: seen.append("a"))
    entry.bind("<Configure>", lambda e: seen.append("configure"))
    assert entry.inner.bind("<KeyPress-a>")
    assert not tk.Frame.bind(entry, "<KeyPress-a>")
    assert tk.Frame.bind(entry, "<Configure>")
    settle(root)
    entry.focus_force()
    root.update()
    entry.event_generate("<KeyPress-a>")
    assert "a" in seen


def test_unbind_removes_from_the_same_widget(root):
    entry = ctk.Entry(root)
    entry.pack()
    funcid = entry.bind("<KeyPress-b>", lambda e: None)
    entry.unbind("<KeyPress-b>", funcid)
    assert not entry.inner.bind("<KeyPress-b>")


def test_cget_reports_inner_options(root):
    entry = ctk.Entry(root, width=17)
    assert int(entry.cget("width")) == 17
    textbox = ctk.Textbox(root, wrap="word")
    assert textbox.cget("wrap") == "word"


def test_configure_passes_native_options_to_the_inner_widget(root):
    entry = ctk.Entry(root)
    entry.configure(width=21, justify="right")
    assert int(entry.inner.cget("width")) == 21
    assert entry.inner.cget("justify") == "right"


# ---- Entry -------------------------------------------------------------------------
def test_entry_textvariable_is_two_way(root):
    variable = tk.StringVar(root, "start")
    entry = ctk.Entry(root, textvariable=variable)
    entry.pack()
    assert entry.get() == "start"
    entry.delete(0, "end")
    entry.insert(0, "typed")
    assert variable.get() == "typed"
    variable.set("set")
    assert entry.get() == "set"


def test_entry_show_hides_the_characters(root):
    entry = ctk.Entry(root, show="•")
    entry.insert(0, "secret")
    assert entry.get() == "secret"
    assert entry.inner.cget("show") == "•"


def test_entry_set_text(root):
    entry = ctk.Entry(root)
    entry.set_text("replaced")
    assert entry.get() == "replaced"
    entry.set_text("again")
    assert entry.get() == "again"


def test_entry_state_disabled_and_readonly(root):
    entry = ctk.Entry(root)
    entry.pack()
    entry.insert(0, "x")
    entry.configure(state="disabled")
    assert entry.inner_state() == "disabled"
    entry.configure(state="readonly")
    assert entry.inner_state() == "readonly"
    entry.configure(state="normal")
    assert entry.inner_state() == "normal"


def test_entry_placeholder_shows_only_while_empty(root):
    entry = ctk.Entry(root, placeholder="Type here")
    entry.pack()
    settle(root)
    assert entry.placeholder_visible()
    entry.insert(0, "x")
    entry.event_generate("<KeyRelease>")
    settle(root)
    assert not entry.placeholder_visible()
    entry.delete(0, "end")
    entry.event_generate("<KeyRelease>")
    settle(root)
    assert entry.placeholder_visible()


def test_entry_placeholder_can_be_changed(root):
    entry = ctk.Entry(root)
    entry.pack()
    assert not entry.placeholder_visible()
    entry.configure(placeholder="hint")
    settle(root)
    assert entry.cget("placeholder") == "hint"
    assert entry.placeholder_visible()


def test_entry_color_options(root):
    entry = ctk.Entry(root, border_color="#ff0000", focus_color="#00ff00")
    assert entry.cget("border_color") == "#ff0000"
    assert entry.cget("focus_color") == "#00ff00"
    entry.configure(border_color=None)
    assert entry.cget("border_color") is None


def test_entry_native_color_aliases_become_color_parts(root):
    entry = ctk.Entry(root)
    entry.configure(fg="#123456")
    assert entry.cget("text_color") == "#123456"


def test_entry_fill_follows_the_theme(root):
    entry = ctk.Entry(root)
    entry.pack()
    settle(root)
    fill = entry.inner.cget("background").lower()
    ctk.set_theme({"surface": "#445566"})
    settle(root)
    assert entry.inner.cget("background").lower() != fill
    assert entry.inner.cget("background").lower() == "#445566"


def test_entry_follows_the_appearance_mode(root):
    entry = ctk.Entry(root)
    entry.pack()
    settle(root)
    light = entry.inner.cget("background").lower()
    ctk.set_appearance_mode("dark")
    settle(root)
    dark = entry.inner.cget("background").lower()
    assert light != dark


def test_entry_radius_uses_the_theme_key(root):
    entry = ctk.Entry(root)
    assert entry.corner(entry.radius, "radius") == 8
    ctk.set_theme({"radius": 2})
    assert entry.corner(entry.radius, "radius") == 2
    assert ctk.Entry(root, radius=0).corner(0, "radius") == 0


# ---- Textbox -----------------------------------------------------------------------
def test_textbox_default_wrap_is_char_and_default_size(root):
    textbox = ctk.Textbox(root)
    assert textbox.cget("wrap") == "char"
    assert int(textbox.cget("width")) == 80
    assert int(textbox.cget("height")) == 24


def test_textbox_wrap_option(root):
    for wrap in ("none", "word", "char"):
        assert ctk.Textbox(root, wrap=wrap).cget("wrap") == wrap


def test_textbox_state_and_readonly_text(root):
    textbox = ctk.Textbox(root, state="disabled")
    assert textbox.cget("state") == "disabled"
    textbox.configure(state="normal")
    textbox.insert("1.0", "ok")
    assert textbox.get("1.0", "end-1c") == "ok"


def test_textbox_scrolled_makes_scrollbars(root):
    plain = ctk.Textbox(root)
    vertical = ctk.Textbox(root, scrolled=True)
    horizontal = ctk.Textbox(root, scrolled=True, orient="horizontal")
    both = ctk.Textbox(root, scrolled=True, orient="both")
    assert plain.scrollbar is None and plain.horizontal_scrollbar is None
    assert vertical.scrollbar is not None and vertical.horizontal_scrollbar is None
    assert horizontal.scrollbar is None and horizontal.horizontal_scrollbar is not None
    assert both.scrollbar is not None and both.horizontal_scrollbar is not None


def test_textbox_rejects_a_bad_orient(root):
    with pytest.raises(ValueError):
        ctk.Textbox(root, orient="diagonal")


def test_textbox_user_scroll_commands_work_with_scrolled(root):
    seen = []
    textbox = ctk.Textbox(
        root, scrolled=True, yscrollcommand=lambda *a: seen.append(a), height=3
    )
    textbox.pack()
    textbox.insert("1.0", "\n".join(str(n) for n in range(50)))
    settle(root)
    assert seen
    assert textbox.scrollbar.get()[1] < 1


def test_textbox_scrollbar_width(root):
    textbox = ctk.Textbox(root, scrolled=True, scrollbar_width=20)
    assert textbox.scrollbar.winfo_reqwidth() == 20
    textbox.configure(scrollbar_width=26)
    assert textbox.scrollbar.winfo_reqwidth() == 26


def test_textbox_placeholder(root):
    textbox = ctk.Textbox(root, placeholder="Write...")
    textbox.pack()
    settle(root)
    assert textbox.placeholder_visible()
    textbox.insert("1.0", "x")
    textbox.event_generate("<KeyRelease>")
    settle(root)
    assert not textbox.placeholder_visible()


def test_textbox_replace(root):
    textbox = ctk.Textbox(root)
    textbox.pack()
    textbox.insert("1.0", "hello world")
    textbox.replace("1.0", "1.5", "bye")
    assert textbox.get("1.0", "end-1c") == "bye world"


def test_textbox_line_numbers_show_and_hide(root):
    textbox = ctk.Textbox(root, line_numbers=True)
    textbox.pack()
    textbox.insert("1.0", "a\nb\nc")
    settle(root)
    assert textbox._gutter is not None
    assert textbox._gutter.winfo_manager() == "pack"
    texts = [
        textbox._gutter.itemcget(item, "text")
        for item in textbox._gutter.find_all()
        if textbox._gutter.type(item) == "text"
    ]
    assert texts[:3] == ["1", "2", "3"]
    textbox.configure(line_numbers=False)
    settle(root)
    assert textbox._gutter.winfo_manager() == ""


def test_textbox_line_numbers_can_be_turned_on_later(root):
    textbox = ctk.Textbox(root)
    textbox.pack()
    textbox.insert("1.0", "x\ny")
    assert textbox._gutter is None
    textbox.configure(line_numbers=True)
    settle(root)
    assert textbox._gutter.winfo_manager() == "pack"


def test_textbox_line_numbers_follow_edits(root):
    textbox = ctk.Textbox(root, line_numbers=True)
    textbox.pack()
    textbox.insert("1.0", "a")
    settle(root)

    def numbers():
        gutter = textbox._gutter
        return [
            gutter.itemcget(item, "text")
            for item in gutter.find_all()
            if gutter.type(item) == "text"
        ]

    assert numbers() == ["1"]
    textbox.insert("end", "\nb\nc\nd")
    settle(root)
    assert numbers()[:4] == ["1", "2", "3", "4"]
    textbox.delete("2.0", "end")
    settle(root)
    assert numbers() == ["1"]


def test_textbox_wrapped_lines_are_numbered_once(root):
    textbox = ctk.Textbox(root, line_numbers=True, wrap="char", width=10, height=10)
    textbox.pack()
    textbox.insert("1.0", "x" * 100 + "\nsecond")
    settle(root)
    gutter = textbox._gutter
    numbers = [
        gutter.itemcget(item, "text")
        for item in gutter.find_all()
        if gutter.type(item) == "text"
    ]
    assert numbers == ["1", "2"]


def test_textbox_line_number_justify_is_checked(root):
    for justify in ("left", "center", "right"):
        ctk.Textbox(root, line_numbers=True, line_number_justify=justify)
    with pytest.raises(ValueError):
        ctk.Textbox(root, line_number_justify="middle")
    textbox = ctk.Textbox(root)
    with pytest.raises(ValueError):
        textbox.configure(line_number_justify="nowhere")


def test_textbox_line_number_colors(root):
    textbox = ctk.Textbox(
        root,
        line_numbers=True,
        line_number_color="#111111",
        line_number_current_color="#222222",
        line_number_fill_color="#333333",
    )
    assert textbox.cget("line_number_color") == "#111111"
    assert textbox.cget("line_number_current_color") == "#222222"
    assert textbox.cget("line_number_fill_color") == "#333333"


def test_textbox_text_widget_commands_still_work_with_line_numbers(root):
    """The Tcl-level wrapper of the text widget must pass Tk's errors through."""
    textbox = ctk.Textbox(root, line_numbers=True)
    textbox.pack()
    textbox.insert("1.0", "abc")
    settle(root)
    with pytest.raises(tk.TclError):
        textbox.get("sel.first", "sel.last")
    with pytest.raises(tk.TclError):
        textbox.index("bogus")
    textbox.tag_add("sel", "1.0", "1.2")
    assert textbox.get("sel.first", "sel.last") == "ab"
    textbox.tag_remove("sel", "1.0", "end")
    textbox.event_generate("<Escape>")


def test_textbox_changed_event_is_generated_with_line_numbers(root):
    textbox = ctk.Textbox(root, line_numbers=True)
    textbox.pack()
    settle(root)
    seen = []
    tk.Frame.bind(textbox.inner, "<<TextboxChanged>>", lambda e: seen.append(1))
    textbox.insert("1.0", "hello")
    settle(root)
    assert seen


def test_textbox_height_follows_height_option(root):
    short = ctk.Textbox(root, height=3, width=20)
    tall = ctk.Textbox(root, height=12, width=20)
    for box in (short, tall):
        box.pack()
    settle(root)
    assert tall.inner.winfo_reqheight() > short.inner.winfo_reqheight()


# ---- Combobox ----------------------------------------------------------------------
def test_combobox_values_set_and_current(root):
    combo = ctk.Combobox(root, values=["a", "b", "c"])
    combo.pack()
    assert combo.current() == -1
    combo.current(1)
    assert combo.get() == "b" and combo.current() == 1
    combo.set("zzz")
    assert combo.current() == -1
    combo.set(5)
    assert combo.get() == "5"


def test_combobox_default(root):
    combo = ctk.Combobox(root, values=["a", "b"], default="b")
    assert combo.get() == "b"
    other = ctk.Combobox(root, values=["a"], default="not in the list")
    assert other.get() == "not in the list"


def test_combobox_default_works_when_readonly_and_disabled(root):
    readonly = ctk.Combobox(root, values=["a", "b"], state="readonly", default="a")
    assert readonly.get() == "a" and readonly.inner_state() == "readonly"
    disabled = ctk.Combobox(root, values=["a", "b"], state="disabled", default="b")
    assert disabled.get() == "b" and disabled.inner_state() == "disabled"


def test_combobox_default_does_not_call_the_command(root):
    calls = []
    ctk.Combobox(root, values=["a"], default="a", command=calls.append)
    assert calls == []


def test_combobox_pick_runs_command_and_event(root):
    picked, events = [], []
    combo = ctk.Combobox(root, values=["a", "b"], command=picked.append)
    combo.pack()
    combo.inner.bind("<<ComboboxSelected>>", lambda e: events.append(1))
    settle(root)
    combo.pick("b")
    assert combo.get() == "b" and picked == ["b"]
    settle(root)
    assert events == [1]


def test_combobox_values_can_change_later(root):
    combo = ctk.Combobox(root, values=["a"])
    combo.pack()
    combo.configure(values=["x", "y", "z"])
    assert combo.values == ["x", "y", "z"]
    combo.current(2)
    assert combo.get() == "z"


def test_combobox_dropdown_opens_and_closes(root):
    combo = ctk.Combobox(root, values=["a", "b", "c"], state="readonly")
    combo.pack()
    settle(root)
    combo.open_dropdown()
    settle(root)
    assert combo._dropdown is not None
    combo._dropdown.close()
    settle(root)
    assert combo._dropdown is None


def test_combobox_postcommand_runs_before_opening(root):
    order = []
    combo = ctk.Combobox(
        root, values=["a"], postcommand=lambda: order.append("post"), state="readonly"
    )
    combo.pack()
    settle(root)
    combo.open_dropdown()
    order.append("opened")
    assert order == ["post", "opened"]
    combo._dropdown.close()


def test_disabled_combobox_does_not_open(root):
    combo = ctk.Combobox(root, values=["a"], state="disabled")
    combo.pack()
    settle(root)
    combo.open_dropdown()
    assert combo._dropdown is None


def test_combobox_without_values_does_not_open(root):
    combo = ctk.Combobox(root)
    combo.pack()
    settle(root)
    combo.open_dropdown()
    assert combo._dropdown is None


def test_combobox_dropdown_marks_the_current_value(root):
    combo = ctk.Combobox(root, values=["a", "b", "c"], default="b", state="readonly")
    combo.pack()
    settle(root)
    combo.open_dropdown()
    entries = combo._dropdown.entries
    assert [e["current"] for e in entries] == [False, True, False]
    combo._dropdown.close()


def test_combobox_dropdown_height_is_limited(root):
    combo = ctk.Combobox(
        root, values=[str(n) for n in range(100)], popup_max_height=120
    )
    combo.pack()
    settle(root)
    combo.open_dropdown()
    popup = combo._dropdown
    assert popup.height <= 120
    assert popup._scrolling
    popup.close()


# ---- Spinbox -----------------------------------------------------------------------
def test_spinbox_starts_at_from(root):
    spin = ctk.Spinbox(root, from_=3, to=9)
    spin.pack()
    assert spin.get() == "3"


def test_spinbox_steps_and_clamps(root):
    spin = ctk.Spinbox(root, from_=0, to=3)
    spin.pack()
    for _ in range(5):
        spin.step(1)
    assert spin.get() == "3"
    for _ in range(9):
        spin.step(-1)
    assert spin.get() == "0"


def test_spinbox_wrap(root):
    spin = ctk.Spinbox(root, from_=0, to=2, wrap=True)
    spin.pack()
    spin.step(-1)
    assert spin.get() == "2"
    spin.step(1)
    assert spin.get() == "0"


def test_spinbox_increment_and_decimals(root):
    spin = ctk.Spinbox(root, from_=0, to=1, increment=0.25)
    spin.pack()
    spin.step(1)
    assert spin.get() == "0.25"
    spin.step(1)
    assert spin.get() == "0.50"


def test_spinbox_values(root):
    spin = ctk.Spinbox(root, values=["low", "mid", "high"])
    spin.pack()
    assert spin.get() == "low"
    spin.step(1)
    spin.step(1)
    spin.step(1)
    assert spin.get() == "high"
    spin.step(-1)
    assert spin.get() == "mid"


def test_spinbox_command_runs_per_step(root):
    calls = []
    spin = ctk.Spinbox(root, command=lambda: calls.append(spin.get()))
    spin.pack()
    spin.step(1)
    spin.step(1)
    assert calls == ["1", "2"]


def test_spinbox_keys(root):
    spin = ctk.Spinbox(root, from_=0, to=10)
    spin.pack()
    settle(root)
    spin.focus_force()
    root.update()
    spin.inner.event_generate("<Up>")
    spin.inner.event_generate("<Up>")
    spin.inner.event_generate("<Down>")
    assert spin.get() == "1"


def test_spinbox_disabled_does_not_step(root):
    spin = ctk.Spinbox(root, from_=0, to=10, state="disabled")
    spin.pack()
    spin.step(1)
    assert spin.get() == "0"


def test_spinbox_validation_allows_only_numbers(root):
    spin = ctk.Spinbox(root, from_=0, to=100)
    assert spin._allows_typing("12")
    assert spin._allows_typing("")
    assert not spin._allows_typing("1a")
    assert not spin._allows_typing("-1")
    negative = ctk.Spinbox(root, from_=-5, to=5)
    assert negative._allows_typing("-3")
    decimal = ctk.Spinbox(root, from_=0, to=1, increment=0.1)
    assert decimal._allows_typing("0.5")
    assert not decimal._allows_typing("0.55")


def test_spinbox_values_validation(root):
    spin = ctk.Spinbox(root, values=["alpha", "beta"])
    assert spin._allows_typing("al")
    assert not spin._allows_typing("gamma")


def test_spinbox_normalizes_on_focus_out(root):
    spin = ctk.Spinbox(root, from_=0, to=10)
    spin.pack()
    spin.set_text("999")
    spin._normalize()
    assert spin.get() == "10"
    spin.set_text("")
    spin._normalize()
    assert spin.get() == "0"
