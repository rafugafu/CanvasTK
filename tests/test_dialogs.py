"""The message boxes, the file dialogs, and the color picker (drop-in versions of the
tkinter ones). The dialogs are modal, so a scheduled callback plays the user.
"""

import tkinter as tk

import pytest

import canvastk as ctk
from canvastk import colorchooser, filedialog, messagebox

from conftest import settle


def dialogs_of(root):
    return [w for w in root.winfo_children() if isinstance(w, ctk.Toplevel)]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def find(dialog, kind, text=None):
    for widget in descendants(dialog):
        if isinstance(widget, kind) and (text is None or widget.text == text):
            return widget
    raise AssertionError(f"no {kind.__name__} {text!r} in the dialog")


def play(root, action, delay=150):
    """Run action(dialog) once the (only) dialog is open; close it if the action did
    not, so that a broken test cannot hang.
    """
    seen = []

    def run():
        found = dialogs_of(root)
        if not found:
            root.after(50, run)
            return
        seen.append(found[0])
        try:
            action(found[0])
        finally:
            for dialog in dialogs_of(root):
                try:
                    dialog.destroy()
                except tk.TclError:
                    pass

    root.after(delay, run)
    return seen


def press(text):
    return lambda dialog: find(dialog, ctk.Button, text).invoke()


# ---- message boxes -----------------------------------------------------------------
@pytest.mark.parametrize(
    "function, button, expected",
    [
        (messagebox.showinfo, "Ok", "ok"),
        (messagebox.showwarning, "Ok", "ok"),
        (messagebox.showerror, "Ok", "ok"),
        (messagebox.askquestion, "Yes", "yes"),
        (messagebox.askquestion, "No", "no"),
        (messagebox.askokcancel, "Ok", True),
        (messagebox.askokcancel, "Cancel", False),
        (messagebox.askyesno, "Yes", True),
        (messagebox.askyesno, "No", False),
        (messagebox.askyesnocancel, "Yes", True),
        (messagebox.askyesnocancel, "No", False),
        (messagebox.askyesnocancel, "Cancel", None),
        (messagebox.askretrycancel, "Retry", True),
        (messagebox.askretrycancel, "Cancel", False),
    ],
)
def test_message_box_return_values(root, function, button, expected):
    play(root, press(button))
    assert function("Title", "Message", parent=root) == expected
    assert dialogs_of(root) == []


def test_message_box_shows_title_message_and_detail(root):
    def check(dialog):
        assert dialog.title() == "A title"
        texts = [w.text for w in descendants(dialog) if isinstance(w, ctk.Label)]
        assert "The message" in texts and "More detail" in texts
        find(dialog, ctk.Button, "Ok").invoke()

    play(root, check)
    messagebox.showinfo("A title", "The message", detail="More detail", parent=root)


def test_message_box_message_may_be_a_number(root):
    def check(dialog):
        assert any(
            w.text == "42" for w in descendants(dialog) if isinstance(w, ctk.Label)
        )
        find(dialog, ctk.Button, "Ok").invoke()

    play(root, check)
    messagebox.showinfo("T", 42, parent=root)


def test_escape_answers_like_cancel_and_return_like_the_default(root):
    play(root, lambda d: d.event_generate("<Escape>"))
    assert messagebox.askokcancel("T", "m", parent=root) is False
    play(root, lambda d: d.event_generate("<Return>"))
    assert messagebox.askokcancel("T", "m", parent=root) is True
    play(root, lambda d: d.event_generate("<Return>"))
    assert messagebox.askyesno("T", "m", parent=root, default="no") is False


def test_closing_the_window_answers_like_cancel(root):
    play(root, lambda d: d.destroy())
    assert messagebox.askyesnocancel("T", "m", parent=root) is None


def test_custom_buttons_return_their_label(root):
    play(root, press("Maybe"))
    answer = messagebox.askquestion(
        "T", "m", parent=root, buttons=["Sure", "Maybe", "Never"]
    )
    assert answer == "Maybe"


def test_message_box_option_errors(root):
    with pytest.raises(TypeError):
        messagebox.showinfo("T", "m", bogus=1)
    with pytest.raises(TypeError):
        messagebox.showinfo("T", "m", type="nonsense")
    with pytest.raises(TypeError):
        messagebox.showinfo("T", "m", icon="nonsense")


def test_message_box_is_modal_transient_and_centered(root):
    def check(dialog):
        assert str(dialog.transient()) == str(root)
        assert dialog.grab_current() is not None
        mid = dialog.winfo_rootx() + dialog.winfo_width() // 2
        assert abs(mid - (root.winfo_rootx() + root.winfo_width() // 2)) < 40
        find(dialog, ctk.Button, "Ok").invoke()

    play(root, check)
    messagebox.showinfo("T", "m", parent=root)


def test_message_box_follows_the_theme_of_its_parent(root):
    root.set_theme({"window": "#123456"})

    def check(dialog):
        assert dialog.cget("bg").lower() == "#123456"
        find(dialog, ctk.Button, "Ok").invoke()

    play(root, check)
    messagebox.showinfo("T", "m", parent=root)


def test_message_box_of_a_cut_off_window_uses_the_defaults(root):
    top = ctk.Toplevel(root, theme={})
    settle(top)
    root.set_theme({"window": "#123456"})

    def check(dialog):
        assert dialog.cget("bg").lower() == ctk.CANVAS_LIGHT_PALETTE["window"].lower()
        find(dialog, ctk.Button, "Ok").invoke()

    seen = []

    def run():
        found = [d for d in descendants(top) if isinstance(d, ctk.Toplevel)]
        if not found:
            top.after(50, run)
            return
        check(found[0])

    top.after(150, run)
    messagebox.showinfo("T", "m", parent=top)


def test_message_box_long_text_wraps_and_is_not_clipped(root):
    def check(dialog):
        settle(dialog)
        label = max(
            (w for w in descendants(dialog) if isinstance(w, ctk.Label)),
            key=lambda w: len(w.text),
        )
        assert label.winfo_height() >= label.requested_size()[1] - 2
        button = find(dialog, ctk.Button, "Ok")
        assert button.winfo_rooty() + button.winfo_height() <= (
            dialog.winfo_rooty() + dialog.winfo_height() + 1
        )
        button.invoke()

    play(root, check)
    messagebox.showinfo("T", "word " * 120, parent=root)


def test_message_box_without_a_parent_uses_the_default_root(root):
    play(root, press("Ok"))
    assert messagebox.showinfo("T", "m") == "ok"


def test_the_dialog_is_raised_above_its_parent(root):
    raised = []
    original = messagebox._raise_window
    messagebox._raise_window = lambda window: (raised.append(window), original(window))
    try:
        play(root, press("Ok"))
        messagebox.showinfo("T", "m", parent=root)
    finally:
        messagebox._raise_window = original
    assert len(raised) == 1


def test_a_dialog_without_a_parent_belongs_to_the_focused_window(root):
    other = ctk.Toplevel(root)
    settle(other)
    entry = ctk.Entry(other)
    entry.pack()
    settle(other)
    entry.focus_force()
    other.update()
    assert messagebox._parent_toplevel(None) is other
    assert messagebox._parent_toplevel(root) is root
    assert messagebox._parent_toplevel(entry) is other


# ---- file dialogs -------------------------------------------------------------------
@pytest.fixture
def files(tmp_path):
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "script.py").write_text("print(1)")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "inner.txt").write_text("inner")
    return tmp_path


def type_name(dialog, text):
    entry = [
        w for w in descendants(dialog) if type(w) is ctk.Entry and w.winfo_ismapped()
    ][-1]
    entry.delete(0, "end")
    entry.insert(0, text)
    return entry


def test_open_dialog_returns_the_typed_file(root, files):
    def action(dialog):
        entry = type_name(dialog, "notes.txt")
        entry.inner.event_generate("<Return>")

    play(root, action)
    result = filedialog.askopenfilename(parent=root, initialdir=str(files))
    assert result == str(files / "notes.txt")


def test_open_dialog_returns_the_selected_file(root, files):
    def action(dialog):
        file_list = next(
            w for w in descendants(dialog) if isinstance(w, filedialog._FileList)
        )
        names = [file_list.get(i)["name"] for i in range(file_list.size())]
        file_list.selection_set(names.index("script.py"))
        find(dialog, ctk.Button, "Open").invoke()

    play(root, action)
    result = filedialog.askopenfilename(parent=root, initialdir=str(files))
    assert result == str(files / "script.py")


def test_open_dialog_starts_in_the_given_folder_and_lists_it(root, files):
    def action(dialog):
        lists = [w for w in descendants(dialog) if isinstance(w, ctk.Listbox)]
        shown = set()
        for box in lists:
            for index in range(box.size()):
                item = box.get(index)
                if isinstance(item, dict):
                    shown.add(item["name"])
        assert {"notes.txt", "script.py", "docs"} <= shown
        find(dialog, ctk.Button, "Cancel").invoke()

    play(root, action)
    assert filedialog.askopenfilename(parent=root, initialdir=str(files)) == ""


def test_open_dialog_filters_by_file_type(root, files):
    def action(dialog):
        names = set()
        for box in (w for w in descendants(dialog) if isinstance(w, ctk.Listbox)):
            for index in range(box.size()):
                item = box.get(index)
                if isinstance(item, dict):
                    names.add(item["name"])
        assert "script.py" in names and "notes.txt" not in names
        find(dialog, ctk.Button, "Cancel").invoke()

    play(root, action)
    filedialog.askopenfilename(
        parent=root,
        initialdir=str(files),
        filetypes=[("Python", "*.py"), ("All", "*")],
    )


def test_open_dialog_cancel_returns_an_empty_string(root, files):
    play(root, press("Cancel"))
    assert filedialog.askopenfilename(parent=root, initialdir=str(files)) == ""
    play(root, press("Cancel"))
    assert filedialog.askopenfilenames(parent=root, initialdir=str(files)) == ()


def test_open_multiple_files(root, files):
    def action(dialog):
        entry = type_name(dialog, '"notes.txt" script.py')
        entry.inner.event_generate("<Return>")

    play(root, action)
    result = filedialog.askopenfilenames(parent=root, initialdir=str(files))
    assert result == (str(files / "notes.txt"), str(files / "script.py"))


def test_save_dialog_adds_the_default_extension(root, files):
    def action(dialog):
        entry = type_name(dialog, "fresh")
        entry.inner.event_generate("<Return>")

    play(root, action)
    result = filedialog.asksaveasfilename(
        parent=root, initialdir=str(files), defaultextension=".txt"
    )
    assert result == str(files / "fresh.txt")


def test_directory_dialog_returns_the_chosen_folder(root, files):
    def action(dialog):
        entry = type_name(dialog, "docs")
        entry.inner.event_generate("<Return>")

    play(root, action)
    result = filedialog.askdirectory(parent=root, initialdir=str(files))
    assert result == str(files / "docs")


def test_file_dialog_starts_with_the_name_entry_focused(root, files):
    focused = []

    def action(dialog):
        focused.append(dialog.focus_get())
        find(dialog, ctk.Button, "Cancel").invoke()

    play(root, action, delay=300)
    filedialog.askopenfilename(parent=root, initialdir=str(files))
    assert focused and isinstance(focused[0], tk.Entry)


def test_open_file_returns_a_file_object(root, files):
    def action(dialog):
        type_name(dialog, "notes.txt").inner.event_generate("<Return>")

    play(root, action)
    handle = filedialog.askopenfile(parent=root, initialdir=str(files))
    try:
        assert handle.read() == "notes"
    finally:
        handle.close()


def test_file_dialog_rejects_unknown_options(root):
    with pytest.raises(TypeError):
        filedialog.askopenfilename(parent=root, bogus=1)


def test_classes_like_tkinter(root, files):
    play(root, press("Cancel"))
    assert filedialog.Open(root, initialdir=str(files)).show() == ""
    play(root, press("Cancel"))
    assert filedialog.SaveAs(root, initialdir=str(files)).show() == ""
    play(root, press("Cancel"))
    assert filedialog.Directory(root, initialdir=str(files)).show() == ""


def test_file_dialog_follows_its_parents_theme(root, files):
    root.set_theme({"window": "#123456"})

    def action(dialog):
        assert dialog.cget("bg").lower() == "#123456"
        find(dialog, ctk.Button, "Cancel").invoke()

    play(root, action)
    filedialog.askopenfilename(parent=root, initialdir=str(files))


# ---- the color picker -----------------------------------------------------------------
def test_askcolor_returns_the_initial_color_on_ok(root):
    play(root, press("OK"))
    rgb, hex_code = colorchooser.askcolor("#3a7bd5", parent=root)
    assert hex_code == "#3a7bd5" and rgb == (58, 123, 213)


def test_askcolor_cancel(root):
    play(root, press("Cancel"))
    assert colorchooser.askcolor("#3a7bd5", parent=root) == (None, None)


def test_askcolor_accepts_names_tuples_and_numbers_text(root):
    play(root, press("OK"))
    assert colorchooser.askcolor("red", parent=root)[1] == "#ff0000"
    play(root, press("OK"))
    assert colorchooser.askcolor((0, 128, 255), parent=root)[1] == "#0080ff"
    play(root, press("OK"))
    assert colorchooser.askcolor("1, 2, 3", parent=root)[1] == "#010203"


def test_askcolor_default_is_white(root):
    play(root, press("OK"))
    assert colorchooser.askcolor(parent=root)[1] == "#ffffff"


def test_askcolor_rejects_unknown_colors(root):
    with pytest.raises(ValueError):
        colorchooser.askcolor("not a color", parent=root)


def test_askcolor_hex_field_changes_the_result(root):
    def action(dialog):
        entry = next(w for w in descendants(dialog) if isinstance(w, ctk.Entry))
        entry.delete(0, "end")
        entry.insert(0, "#102030")
        entry.focus_force()
        dialog.update()
        entry.inner.event_generate("<KeyRelease>", keysym="0")
        dialog.update()
        find(dialog, ctk.Button, "OK").invoke()

    play(root, action)
    assert colorchooser.askcolor("#ffffff", parent=root)[1] == "#102030"


def test_askcolor_square_marker_starts_at_the_color(root):
    seen = []

    def action(dialog):
        settle(dialog)
        square = next(
            w for w in descendants(dialog) if isinstance(w, colorchooser._ColorSquare)
        )
        seen.append((square.saturation, square.value))
        find(dialog, ctk.Button, "Cancel").invoke()

    play(root, action, delay=300)
    colorchooser.askcolor("#3a7bd5", parent=root)
    saturation, value = seen[0]
    assert saturation == pytest.approx(0.728, abs=0.01)
    assert value == pytest.approx(0.835, abs=0.01)


def test_chooser_class_and_color_option(root):
    play(root, press("OK"))
    assert colorchooser.Chooser(root, color="#010203").show()[1] == "#010203"
    with pytest.raises(TypeError):
        colorchooser.Chooser(root, bogus=1).show()


def test_recent_colors_are_remembered(root):
    colorchooser._COLOR_PICKER_RECENT_COLORS.clear()
    play(root, press("OK"))
    colorchooser.askcolor("#0a0b0c", parent=root)
    assert colorchooser._COLOR_PICKER_RECENT_COLORS[0] == "#0a0b0c"
    play(root, press("OK"))
    colorchooser.askcolor("#0d0e0f", parent=root)
    assert colorchooser._COLOR_PICKER_RECENT_COLORS[:2] == ["#0d0e0f", "#0a0b0c"]
    colorchooser._COLOR_PICKER_RECENT_COLORS.clear()
