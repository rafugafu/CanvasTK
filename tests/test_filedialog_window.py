"""The file dialog window driven directly (built, but not shown modally)."""

import os
import time
import tkinter as tk

import pytest

import canvastk as ctk
from canvastk import filedialog as fd

from conftest import settle


class Key:
    """A bare key event for the handlers that read keysym / char."""

    def __init__(self, keysym="a", char="a", x_root=0, y_root=0):
        self.keysym, self.char = keysym, char
        self.x_root, self.y_root = x_root, y_root
        self.state = 0


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "alpha.txt").write_text("a" * 10)
    (tmp_path / "alpine.md").write_text("md")
    (tmp_path / "Beta.py").write_text("b" * 3000)
    (tmp_path / ".secret").write_text("s")
    (tmp_path / ".config").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "inner.txt").write_text("inner")
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def make_dialog(root, tree, monkeypatch):
    built = []
    messages = []

    def make(mode="open", **options):
        options.setdefault("initialdir", str(tree))
        dialog = fd._FileDialog(mode, parent=root, **options)
        monkeypatch.setattr(
            dialog, "_message", lambda title, text: messages.append((title, text))
        )
        dialog.answers = []
        monkeypatch.setattr(
            dialog, "_confirm", lambda title, text: dialog.answers.pop(0)
        )
        dialog._build(root)
        settle(dialog.window)
        dialog.messages = messages
        built.append(dialog)
        return dialog

    yield make
    for dialog in built:
        try:
            dialog.window.destroy()
        except Exception:
            pass


def shown_names(dialog):
    return [dialog.file_list.get(i)["name"] for i in range(dialog.file_list.size())]


# ---- the list and the navigation ---------------------------------------------------------
def test_dialog_lists_the_start_folder_without_hidden_entries(make_dialog):
    dialog = make_dialog()
    assert shown_names(dialog) == ["data", "docs", "alpha.txt", "alpine.md", "Beta.py"]
    assert dialog.directory == dialog.start_directory


def test_hidden_option_and_control_h(make_dialog):
    dialog = make_dialog()
    dialog.show_hidden.set(True)
    dialog.refresh()
    assert ".secret" in shown_names(dialog) and ".config" in shown_names(dialog)
    dialog._toggle_hidden()
    assert ".secret" not in shown_names(dialog)


def test_navigate_history_back_forward_up(make_dialog, tree):
    dialog = make_dialog()
    dialog.navigate(str(tree / "docs"))
    assert shown_names(dialog) == ["inner.txt"]
    dialog.go_back()
    assert dialog.directory == str(tree)
    dialog.go_forward()
    assert dialog.directory == str(tree / "docs")
    dialog.go_up()
    assert dialog.directory == str(tree)
    assert dialog.file_list.curselection() != ()  # the folder we came from
    assert dialog.file_list.get(dialog.file_list.curselection()[0])["name"] == "docs"


def test_back_and_forward_buttons_follow_the_history(make_dialog, tree):
    dialog = make_dialog()
    assert dialog.back_button.cget("state") == "disabled"
    dialog.navigate(str(tree / "docs"))
    assert dialog.back_button.cget("state") == "normal"
    assert dialog.forward_button.cget("state") == "disabled"
    dialog.go_back()
    assert dialog.forward_button.cget("state") == "normal"


def test_navigating_to_an_unreadable_folder_reports_and_stays(make_dialog, tree):
    dialog = make_dialog()
    assert dialog.navigate(str(tree / "missing")) is False
    assert dialog.messages and dialog.messages[0][0] == "Cannot open folder"
    assert dialog.directory == str(tree)


def test_sort_by_column_and_reverse(make_dialog):
    dialog = make_dialog()
    dialog.sort_by("size")
    files = [n for n in shown_names(dialog) if "." in n]
    assert files == ["alpine.md", "alpha.txt", "Beta.py"]
    dialog.sort_by("size")
    assert dialog.sort_descending
    files = [n for n in shown_names(dialog) if "." in n]
    assert files == ["Beta.py", "alpha.txt", "alpine.md"]
    dialog.sort_by("name")
    assert not dialog.sort_descending and shown_names(dialog)[0] == "data"


def test_places_sidebar_navigates(make_dialog, tree):
    dialog = make_dialog()
    dialog.places = [("Tree", str(tree / "docs"))] + dialog.places
    dialog.places_list.insert(0, "Tree")
    dialog.places_list.selection_set(0)
    dialog._on_place_selected()
    assert dialog.directory == str(tree / "docs")
    assert dialog.places_list.curselection() == (0,)


def test_selecting_a_file_fills_the_name_field(make_dialog):
    dialog = make_dialog()
    dialog.file_list.selection_set(shown_names(dialog).index("Beta.py"))
    dialog._on_selection_changed()
    assert dialog.name_entry.get() == "Beta.py"
    dialog.file_list.selection_set(shown_names(dialog).index("docs"))
    dialog._on_selection_changed()  # only a folder: leaves the name alone
    assert dialog.name_entry.get() == "Beta.py"


def test_selecting_several_files_quotes_names_with_spaces(make_dialog, tree):
    (tree / "with space.txt").write_text("x")
    dialog = make_dialog(multiple=True)
    names = shown_names(dialog)
    dialog.file_list.configure(selectmode="extended")
    dialog.file_list.selection_set(names.index("alpha.txt"))
    dialog.file_list.selection_set(names.index("with space.txt"))
    dialog._on_selection_changed()
    assert dialog.name_entry.get() == 'alpha.txt "with space.txt"'


def test_double_click_opens_folders_and_accepts_files(make_dialog, tree):
    dialog = make_dialog()
    dialog._on_double_click(None)  # nothing selected
    dialog.file_list.selection_set(shown_names(dialog).index("docs"))
    dialog._on_double_click(None)
    assert dialog.directory == str(tree / "docs")
    dialog.file_list.selection_set(0)
    dialog._on_double_click(None)
    assert dialog.result == str(tree / "docs" / "inner.txt")


def test_type_ahead_jumps_to_a_name(make_dialog):
    dialog = make_dialog()
    dialog._type_ahead(Key(char="b"))
    assert shown_names(dialog)[dialog.file_list.curselection()[0]] == "Beta.py"
    dialog._type_ahead(Key(char=" "))  # ignored
    dialog._type_ahead(Key(char=""))
    dialog._typed_at = time.monotonic() - 5  # a pause starts a new word
    dialog._type_ahead(Key(char="d"))
    assert shown_names(dialog)[dialog.file_list.curselection()[0]] == "data"
    dialog._type_ahead(Key(char="o"))
    assert shown_names(dialog)[dialog.file_list.curselection()[0]] == "docs"


# ---- the path field -----------------------------------------------------------------------
def test_editing_the_path_and_going_there(make_dialog, tree):
    dialog = make_dialog()
    dialog._focus_path()
    settle(dialog.window)
    assert dialog.path_entry.winfo_ismapped()
    assert dialog.path_entry.get() == str(tree)
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree / "docs"))
    dialog._on_path_return(None)
    assert dialog.directory == str(tree / "docs")
    assert not dialog.path_entry.winfo_ismapped()


def test_path_to_a_file_opens_its_folder_and_selects_it(make_dialog, tree):
    dialog = make_dialog()
    dialog._focus_path()
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree / "docs" / "inner.txt"))
    dialog._go_to_typed_path()
    assert dialog.directory == str(tree / "docs")
    assert dialog.file_list.curselection() == (0,)


def test_a_missing_path_is_reported(make_dialog, tree):
    dialog = make_dialog()
    dialog._focus_path()
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree / "nowhere"))
    dialog._go_to_typed_path()
    assert dialog.messages[0][0] == "Not found"


def test_path_escape_stops_editing(make_dialog):
    dialog = make_dialog()
    dialog._focus_path()
    dialog._on_path_escape(None)
    assert not dialog.path_entry.winfo_ismapped()


def test_path_typing_suggests_folders(make_dialog, tree):
    dialog = make_dialog()
    dialog._focus_path()
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree) + os.sep + "do")
    dialog._on_path_typed(Key())
    assert dialog.path_completion.visible()
    assert dialog.path_entry.get().endswith("docs" + os.sep)
    dialog._on_path_tab(None)
    assert not dialog.path_completion.visible()


def test_path_typing_with_several_matches_shows_a_dropdown(make_dialog, tree):
    (tree / "docs2").mkdir()
    dialog = make_dialog()
    dialog._focus_path()
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree) + os.sep + "do")
    dialog._on_path_typed(Key())
    assert dialog.path_dropdown.visible()
    assert [e["name"] for e in dialog.path_dropdown.list.get(0, "end")] == [
        "docs",
        "docs2",
    ]
    dialog._move_in_dropdown(dialog.path_dropdown, 1)
    assert dialog.path_dropdown.highlighted()["name"] == "docs"
    dialog._on_path_return(None)  # takes the highlighted folder and enters it
    assert dialog.directory == str(tree / "docs")
    assert not dialog.path_dropdown.visible()


def test_path_escape_hides_the_dropdown_first(make_dialog, tree):
    (tree / "docs2").mkdir()
    dialog = make_dialog()
    dialog._focus_path()
    dialog.path_entry.delete(0, "end")
    dialog.path_entry.insert(0, str(tree) + os.sep + "do")
    dialog._on_path_typed(Key())
    dialog._on_path_escape(None)
    assert not dialog.path_dropdown.visible()
    assert dialog.path_entry.winfo_ismapped()  # still editing


# ---- the Name field -----------------------------------------------------------------------
def type_into_name(dialog, text, keysym="a"):
    dialog.name_entry.delete(0, "end")
    dialog.name_entry.insert(0, text)
    dialog._on_name_typed(Key(keysym=keysym))


def test_typing_narrows_the_list_and_suggests_the_rest(make_dialog):
    dialog = make_dialog()
    type_into_name(dialog, "Be")
    assert shown_names(dialog) == ["Beta.py"]
    assert dialog.name_entry.get() == "Beta.py"
    assert dialog.name_completion.visible()


def test_backspace_does_not_suggest(make_dialog):
    dialog = make_dialog()
    type_into_name(dialog, "Bet", keysym="BackSpace")
    assert not dialog.name_completion.visible()
    assert dialog.name_entry.get() == "Bet"


def test_several_matches_show_a_dropdown_and_tab_takes_the_highlighted(make_dialog):
    dialog = make_dialog()
    type_into_name(dialog, "al")
    assert dialog.name_dropdown.visible()
    dialog._move_in_dropdown(dialog.name_dropdown, 1)
    assert dialog._on_name_tab(None) == "break"
    assert dialog.name_entry.get() == "alpha.txt"
    assert not dialog.name_dropdown.visible()


def test_return_with_a_suggestion_keeps_it_then_return_accepts(make_dialog, tree):
    dialog = make_dialog()
    type_into_name(dialog, "Be")
    dialog._on_name_return(None)  # accepts the suggestion
    assert dialog.name_entry.get() == "Beta.py"
    assert dialog.result == ""
    dialog._on_name_return(None)  # accepts the dialog
    assert dialog.result == str(tree / "Beta.py")


def test_escape_hides_the_suggestion_then_lets_the_dialog_cancel(make_dialog):
    dialog = make_dialog()
    type_into_name(dialog, "Be")
    assert dialog._on_name_escape(None) == "break"
    assert dialog.name_entry.get() == "Be"
    assert dialog._on_name_escape(None) is None


def test_tab_without_a_suggestion_moves_on(make_dialog):
    dialog = make_dialog()
    assert dialog._on_name_tab(None) is None


def test_a_dot_shows_and_completes_hidden_names(make_dialog):
    dialog = make_dialog()
    type_into_name(dialog, ".")
    assert ".secret" in shown_names(dialog) and ".config" in shown_names(dialog)
    assert dialog.typing_hidden
    type_into_name(dialog, ".se")
    assert dialog.name_entry.get() == ".secret"
    type_into_name(dialog, "")
    assert not dialog.typing_hidden and ".secret" not in shown_names(dialog)


def test_typing_a_path_does_not_narrow_the_list(make_dialog, tree):
    dialog = make_dialog()
    type_into_name(dialog, "docs" + os.sep + "in")
    assert len(shown_names(dialog)) == 5
    assert dialog.name_entry.get() == "docs" + os.sep + "inner.txt"
    type_into_name(dialog, "docs" + os.sep + ".")
    assert not dialog.typing_hidden


def test_picking_a_folder_suggestion_enters_it(make_dialog, tree):
    dialog = make_dialog()
    type_into_name(dialog, "do")
    dialog._pick_name_suggestion(
        {"name": "docs", "path": str(tree / "docs"), "is_dir": True}, ""
    )
    assert dialog.directory == str(tree / "docs")
    assert dialog.name_entry.get() == ""


def test_picking_a_file_suggestion_fills_the_name(make_dialog, tree):
    dialog = make_dialog()
    dialog._pick_name_suggestion(
        {"name": "Beta.py", "path": str(tree / "Beta.py"), "is_dir": False}, ""
    )
    assert dialog.name_entry.get() == "Beta.py"
    assert shown_names(dialog) == ["Beta.py"]


# ---- accepting ------------------------------------------------------------------------------
def test_open_without_a_choice_complains(make_dialog):
    dialog = make_dialog()
    dialog.accept()
    assert dialog.messages[0][0] == "Nothing selected"


def test_open_a_missing_file_complains(make_dialog):
    dialog = make_dialog()
    dialog.name_entry.insert(0, "ghost.txt")
    dialog.accept()
    assert dialog.messages[0][0] == "File not found" and dialog.result == ""


def test_open_a_typed_folder_enters_it(make_dialog, tree):
    dialog = make_dialog()
    dialog.name_entry.insert(0, "docs")
    dialog.accept()
    assert dialog.directory == str(tree / "docs") and dialog.name_entry.get() == ""


def test_open_a_selected_folder_enters_it(make_dialog, tree):
    dialog = make_dialog()
    dialog.file_list.selection_set(shown_names(dialog).index("data"))
    dialog.accept()
    assert dialog.directory == str(tree / "data")


def test_open_multiple_returns_a_tuple(make_dialog, tree):
    dialog = make_dialog(multiple=True)
    dialog.name_entry.insert(0, "alpha.txt Beta.py")
    dialog.accept()
    assert dialog.result == (str(tree / "alpha.txt"), str(tree / "Beta.py"))


def test_save_needs_a_name_and_a_folder(make_dialog, tree):
    dialog = make_dialog("save")
    dialog.accept()
    assert dialog.messages[-1][0] == "No file name"
    dialog.name_entry.insert(0, "missing" + os.sep + "file.txt")
    dialog.accept()
    assert dialog.messages[-1][0] == "Folder not found"


def test_save_enters_a_typed_folder(make_dialog, tree):
    dialog = make_dialog("save")
    dialog.name_entry.insert(0, "docs")
    dialog.accept()
    assert dialog.directory == str(tree / "docs")


def test_save_asks_before_overwriting(make_dialog, tree):
    dialog = make_dialog("save")
    dialog.answers = [False, True]
    dialog.name_entry.insert(0, "alpha.txt")
    dialog.accept()
    assert dialog.result == ""
    dialog.accept()
    assert dialog.result == str(tree / "alpha.txt")


def test_save_without_confirmation_overwrites_directly(make_dialog, tree):
    dialog = make_dialog("save", confirmoverwrite=False)
    dialog.name_entry.insert(0, "alpha.txt")
    dialog.accept()
    assert dialog.result == str(tree / "alpha.txt")


def test_save_adds_the_default_extension(make_dialog, tree):
    dialog = make_dialog("save", defaultextension="log")
    dialog.name_entry.insert(0, "fresh")
    dialog.accept()
    assert dialog.result == str(tree / "fresh.log")


def test_directory_mode_picks_typed_selected_or_current(make_dialog, tree):
    dialog = make_dialog("directory")
    assert shown_names(dialog) == ["data", "docs"]
    dialog.accept()
    assert dialog.result == str(tree)
    dialog = make_dialog("directory")
    dialog.file_list.selection_set(shown_names(dialog).index("docs"))
    dialog._on_selection_changed()
    dialog.accept()
    assert dialog.result == str(tree / "docs")
    dialog = make_dialog("directory", mustexist=True)
    dialog.name_entry.insert(0, "nowhere")
    dialog.accept()
    assert dialog.messages[0][0] == "Folder not found"


def test_cancel_leaves_the_result_empty(make_dialog):
    dialog = make_dialog()
    dialog.cancel()
    assert dialog.result == ""


def test_the_chosen_filter_is_reported_through_typevariable(make_dialog, root):
    variable = tk.StringVar(root)
    dialog = make_dialog(
        filetypes=[("Python", "*.py"), ("Text", "*.txt")], typevariable=variable
    )
    dialog.type_box.current(1)
    dialog.refresh()
    assert shown_names(dialog) == ["data", "docs", "alpha.txt"]
    dialog.name_entry.insert(0, "alpha.txt")
    dialog.accept()
    assert variable.get() == "Text"


def test_new_folder_makes_and_selects_it(make_dialog, tree, monkeypatch):
    dialog = make_dialog("save")
    monkeypatch.setattr(fd, "_ask_new_folder_name", lambda window: "fresh")
    dialog.new_folder()
    assert (tree / "fresh").is_dir()
    assert "fresh" in shown_names(dialog)


def test_new_folder_errors_and_empty_names(make_dialog, tree, monkeypatch):
    dialog = make_dialog("save")
    monkeypatch.setattr(fd, "_ask_new_folder_name", lambda window: "  ")
    dialog.new_folder()
    monkeypatch.setattr(fd, "_ask_new_folder_name", lambda window: "docs")
    dialog.new_folder()  # exists already
    assert dialog.messages[0][0] == "Cannot create folder"


def test_context_menu_entries(make_dialog, root):
    from canvastk import popups

    dialog = make_dialog("save")
    dialog._show_context_menu(Key(x_root=50, y_root=50))
    settle(root)
    popup = popups._OPEN_POPUPS[0]
    assert [e["label"] for e in popup.entries] == [
        "New folder",
        "Refresh",
        "Show hidden files",
    ]
    popup.close()
    opening = make_dialog("open")
    opening._show_context_menu(Key(x_root=50, y_root=50))
    settle(root)
    popup = popups._OPEN_POPUPS[0]
    assert [e["label"] for e in popup.entries] == ["Refresh", "Show hidden files"]
    popup.close()


def test_keyboard_shortcuts_of_the_window(make_dialog, tree):
    dialog = make_dialog()
    dialog.navigate(str(tree / "docs"))
    window = dialog.window
    window.focus_force()
    window.update()
    window.event_generate("<Alt-Left>")
    assert dialog.directory == str(tree)
    window.event_generate("<Alt-Right>")
    assert dialog.directory == str(tree / "docs")
    window.event_generate("<Alt-Up>")
    assert dialog.directory == str(tree)
    window.event_generate("<F5>")
    window.event_generate("<Control-l>")
    settle(window)
    assert dialog.path_entry.winfo_ismapped()
