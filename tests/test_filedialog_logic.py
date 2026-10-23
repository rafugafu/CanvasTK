"""The file dialog's functions that need no window (no display)."""

import os
import time

import pytest

from canvastk import filedialog as fd


@pytest.fixture
def folder(tmp_path):
    """A folder with files, folders, and hidden things in it."""
    (tmp_path / "alpha.txt").write_text("a" * 10)
    (tmp_path / "Beta.PY").write_text("b" * 2000)
    (tmp_path / "gamma.png").write_text("")
    (tmp_path / ".hidden.txt").write_text("h")
    (tmp_path / "docs").mkdir()
    (tmp_path / "Data").mkdir()
    (tmp_path / ".config").mkdir()
    return tmp_path


def names(entries):
    return [entry["name"] for entry in entries]


# ---- parse_filetypes / name_matches ----------------------------------------------
def test_parse_filetypes_normalizes_patterns():
    parsed = fd.parse_filetypes(
        [("Images", "*.png .jpg gif"), ("All", "*.*"), ("Python", ("*.py", "*.pyw"))]
    )
    assert parsed == [
        ("Images", ["*.png", "*.jpg", "*.gif"]),
        ("All", ["*"]),
        ("Python", ["*.py", "*.pyw"]),
    ]


def test_parse_filetypes_defaults_and_ignores_extra_items():
    assert fd.parse_filetypes(None) == [("All files", ["*"])]
    assert fd.parse_filetypes([]) == [("All files", ["*"])]
    assert fd.parse_filetypes([("Text", "*.txt", "TEXT")]) == [("Text", ["*.txt"])]
    assert fd.parse_filetypes([("Nothing", "")]) == [("Nothing", ["*"])]


def test_parse_filetypes_keeps_glob_characters():
    assert fd.parse_filetypes([("x", "data?.csv [ab]*")]) == [
        ("x", ["data?.csv", "[ab]*"])
    ]


def test_name_matches_ignores_case():
    assert fd.name_matches("Photo.PNG", ["*.png"])
    assert fd.name_matches("a.txt", ["*.py", "*.txt"])
    assert not fd.name_matches("a.txt", ["*.py"])
    assert fd.name_matches("anything", ["*"])


# ---- sizes and times -------------------------------------------------------------
@pytest.mark.parametrize(
    "size, text",
    [
        (0, "0 B"),
        (812, "812 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (4300, "4.2 KB"),
        (1024**2, "1.0 MB"),
        (int(1.5 * 1024**3), "1.5 GB"),
        (1024**4 * 3, "3.0 TB"),
        (1024**5, "1024.0 TB"),
    ],
)
def test_human_size(size, text):
    assert fd.human_size(size) == text


def test_format_modified():
    assert fd.format_modified(0) == ""
    assert fd.format_modified(None) == ""
    stamp = time.mktime((2024, 3, 9, 14, 5, 0, 0, 0, -1))
    assert fd.format_modified(stamp) == "2024-03-09 14:05"


# ---- list_directory --------------------------------------------------------------
def test_list_directory_hides_hidden_files(folder):
    entries, error = fd.list_directory(str(folder))
    assert error is None
    assert set(names(entries)) == {"alpha.txt", "Beta.PY", "gamma.png", "docs", "Data"}


def test_list_directory_shows_hidden_files_on_request(folder):
    entries, _ = fd.list_directory(str(folder), show_hidden=True)
    assert {".hidden.txt", ".config"} <= set(names(entries))


def test_list_directory_filters_files_but_not_folders(folder):
    entries, _ = fd.list_directory(str(folder), patterns=["*.txt"])
    assert set(names(entries)) == {"alpha.txt", "docs", "Data"}


def test_list_directory_directories_only(folder):
    entries, _ = fd.list_directory(str(folder), directories_only=True)
    assert set(names(entries)) == {"docs", "Data"}
    assert all(entry["is_dir"] for entry in entries)


def test_list_directory_entry_fields(folder):
    entries, _ = fd.list_directory(str(folder))
    by_name = {entry["name"]: entry for entry in entries}
    assert by_name["alpha.txt"]["size"] == 10
    assert by_name["docs"]["size"] == 0
    assert by_name["alpha.txt"]["path"] == str(folder / "alpha.txt")
    assert by_name["alpha.txt"]["mtime"] > 0
    assert not by_name["alpha.txt"]["is_dir"]


def test_list_directory_reports_an_error(tmp_path):
    entries, error = fd.list_directory(str(tmp_path / "missing"))
    assert entries == []
    assert isinstance(error, OSError)


# ---- sort_entries ----------------------------------------------------------------
def test_sort_by_name_puts_folders_first_ignoring_case(folder):
    entries, _ = fd.list_directory(str(folder))
    assert names(fd.sort_entries(entries)) == [
        "Data",
        "docs",
        "alpha.txt",
        "Beta.PY",
        "gamma.png",
    ]


def test_sort_descending_reverses_each_group(folder):
    entries, _ = fd.list_directory(str(folder))
    assert names(fd.sort_entries(entries, "name", True)) == [
        "docs",
        "Data",
        "gamma.png",
        "Beta.PY",
        "alpha.txt",
    ]


def test_sort_by_size(folder):
    entries, _ = fd.list_directory(str(folder))
    files = [e for e in fd.sort_entries(entries, "size") if not e["is_dir"]]
    assert names(files) == ["gamma.png", "alpha.txt", "Beta.PY"]


def test_sort_by_mtime(folder):
    entries, _ = fd.list_directory(str(folder))
    for entry, stamp in zip(entries, range(1000, 1000 + len(entries))):
        entry["mtime"] = stamp
    ordered = fd.sort_entries(entries, "mtime")
    folders = [e for e in ordered if e["is_dir"]]
    files = [e for e in ordered if not e["is_dir"]]
    assert ordered == folders + files
    assert [e["mtime"] for e in files] == sorted(e["mtime"] for e in files)


# ---- paths -----------------------------------------------------------------------
def test_resolve_path_relative_absolute_and_home(tmp_path):
    assert fd.resolve_path("sub/file", str(tmp_path)) == str(tmp_path / "sub" / "file")
    assert fd.resolve_path("/etc", str(tmp_path)) == "/etc"
    assert fd.resolve_path("../x", str(tmp_path / "a")) == str(tmp_path / "x")
    assert fd.resolve_path("~", "/tmp") == os.path.expanduser("~")
    assert fd.resolve_path("  name  ", str(tmp_path)) == str(tmp_path / "name")


def test_resolve_path_expands_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("CANVASTK_TEST_FOLDER", "inner")
    assert fd.resolve_path("$CANVASTK_TEST_FOLDER/f", str(tmp_path)) == str(
        tmp_path / "inner" / "f"
    )


def test_with_default_extension():
    assert fd.with_default_extension("notes", ".txt") == "notes.txt"
    assert fd.with_default_extension("notes", "txt") == "notes.txt"
    assert fd.with_default_extension("notes.md", ".txt") == "notes.md"
    assert fd.with_default_extension("notes", "") == "notes"
    assert fd.with_default_extension("notes", None) == "notes"
    assert fd.with_default_extension("", ".txt") == ""


def test_path_segments():
    assert fd.path_segments("/home/me/Docs") == [
        ("/", "/"),
        ("home", "/home"),
        ("me", "/home/me"),
        ("Docs", "/home/me/Docs"),
    ]
    assert fd.path_segments("/") == [("/", "/")]


def test_split_typed_names():
    assert fd.split_typed_names("  a b.txt  ", False) == ["a b.txt"]
    assert fd.split_typed_names('"a b.txt" c.txt', True) == ["a b.txt", "c.txt"]
    assert fd.split_typed_names("a.txt b.txt", True) == ["a.txt", "b.txt"]
    assert fd.split_typed_names("", True) == []
    assert fd.split_typed_names('"unbalanced', True) == ['"unbalanced']


def test_quote_names_is_the_inverse():
    names_ = ["a b.txt", "c.txt"]
    assert fd.quote_names(names_) == '"a b.txt" c.txt'
    assert fd.split_typed_names(fd.quote_names(names_), True) == names_


def test_filter_entries_matches_a_part_of_the_name(folder):
    entries, _ = fd.list_directory(str(folder))
    assert set(names(fd.filter_entries(entries, "A"))) == {
        "alpha.txt",
        "Beta.PY",
        "gamma.png",
        "Data",
    }
    assert fd.filter_entries(entries, "") == entries
    assert fd.filter_entries(entries, "zzz") == []


def test_default_places_start_with_home_and_end_with_the_root():
    places = fd.default_places()
    assert places[0] == ("Home", os.path.expanduser("~"))
    if os.name != "nt":
        assert places[-1] == ("File System", os.sep)


# ---- completion ------------------------------------------------------------------
def test_complete_name():
    assert fd.complete_name(["report.txt", "readme.md"], "re") == "re"
    assert fd.complete_name(["report.txt", "reply.md"], "rep") == "rep"
    assert fd.complete_name(["report.txt", "reports.txt"], "rep") == "report"
    assert fd.complete_name(["Report.txt"], "rep") == "report.txt"
    assert fd.complete_name(["abc"], "x") == "x"


def test_completion_candidates_for_a_plain_name(folder):
    head, matches = fd.completion_candidates("a", str(folder), directories_only=False)
    assert head == ""
    assert names(matches) == ["alpha.txt"]


def test_completion_candidates_are_sorted_with_folders_first(folder):
    head, matches = fd.completion_candidates("d", str(folder), directories_only=False)
    assert names(matches) == ["Data", "docs"]


def test_completion_candidates_directories_only(folder):
    _, matches = fd.completion_candidates("a", str(folder), directories_only=True)
    assert matches == []
    _, matches = fd.completion_candidates("d", str(folder), directories_only=True)
    assert names(matches) == ["Data", "docs"]


def test_completion_candidates_after_a_separator(folder):
    head, matches = fd.completion_candidates(
        "sub/", str(folder), directories_only=False
    )
    assert head == "sub/" and matches == []
    head, matches = fd.completion_candidates(
        str(folder) + os.sep + "al", "/", directories_only=False
    )
    assert head == str(folder) + os.sep
    assert names(matches) == ["alpha.txt"]


def test_completion_hides_hidden_names_unless_a_dot_is_typed(folder):
    _, matches = fd.completion_candidates("", str(folder), directories_only=False)
    assert matches == []  # nothing typed after the last separator
    _, matches = fd.completion_candidates(
        str(folder) + os.sep + ".", "/", directories_only=False
    )
    assert set(names(matches)) == {".hidden.txt", ".config"}
    _, matches = fd.completion_candidates(
        str(folder) + os.sep + ".c", "/", directories_only=False
    )
    assert names(matches) == [".config"]


def test_completion_with_show_hidden_includes_hidden_names(folder):
    _, matches = fd.completion_candidates(
        "c", str(folder), show_hidden=False, directories_only=False
    )
    assert matches == []
    _, matches = fd.completion_candidates(
        ".c", str(folder), show_hidden=True, directories_only=False
    )
    assert names(matches) == [".config"]


def test_completion_tail_adds_a_separator_for_a_single_folder(folder):
    _, matches = fd.completion_candidates("do", str(folder), directories_only=True)
    assert fd.completion_tail("do", matches) == "cs" + os.sep
    _, matches = fd.completion_candidates("al", str(folder), directories_only=False)
    assert fd.completion_tail("al", matches) == "pha.txt"
    assert fd.completion_tail("zz", []) == ""


def test_completion_tail_of_several_matches_is_their_common_start(tmp_path):
    for name in ("report1.txt", "report2.txt"):
        (tmp_path / name).write_text("")
    _, matches = fd.completion_candidates("r", str(tmp_path), directories_only=False)
    assert fd.completion_tail("r", matches) == "eport"


def test_complete_path(folder):
    assert fd.complete_path("do", str(folder)) == "docs" + os.sep
    assert fd.complete_path("zz", str(folder)) == "zz"
    assert fd.complete_path("al", str(folder), directories_only=False) == "alpha.txt"
    assert fd.complete_path("", str(folder)) == ""
