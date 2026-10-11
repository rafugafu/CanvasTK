"""File dialogs with the same API as tkinter.filedialog, drawn with canvastk widgets.

    from canvastk import filedialog

    path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    paths = filedialog.askopenfilenames()
    path = filedialog.asksaveasfilename(defaultextension=".txt")
    folder = filedialog.askdirectory()
    handle = filedialog.askopenfile()      # an open file, or None

The functions, the Open / SaveAs / Directory classes, and the options (parent,
title, initialdir, initialfile, filetypes, defaultextension, multiple, mustexist,
confirmoverwrite, typevariable) behave like tkinter's. The dialog is modal, follows
the theme of the window it belongs to, and has places (Home, Desktop, mounted
drives...), back / forward / up, a path bar, sortable columns, a file type filter,
hidden files, new folders, type-ahead, an overwrite confirmation, and keyboard
shortcuts.

Everything that does not need a window (reading directories, sorting, matching
file types, default extensions, formatting) is in plain functions at the top.
"""

import fnmatch
import os
import shlex
import string
import time
import tkinter as tk

from ._core import (
    CanvasWidget,
    window_appearance_mode,
    window_theme,
    _CANVAS_CHROME_TAG,
)
from . import messagebox
from .messagebox import _make_modal, _parent_toplevel
from .buttons import Button, Checkbutton, Label
from .containers import Frame, Panedwindow
from .entries import Combobox, Entry
from .listbox import Listbox
from .popups import Menu
from .windows import Toplevel, Window

# The folder the last dialog ended in: the next dialog without an initialdir starts
# there (tkinter does the same).
_LAST_FILE_DIALOG_DIRECTORY = None


# =============================================================================
# Logic that needs no window
# =============================================================================


def parse_filetypes(filetypes):
    """Turn tkinter-style filetypes into a list of (label, [patterns]).

    Each entry is (label, patterns): patterns is a string such as "*.png *.jpg"
    or a sequence of patterns. A pattern may be a glob ("*.txt"), an extension
    (".txt" or "txt"), or "*" / "*.*" for everything. No filetypes means a single
    "All files" entry. A third tuple item (macOS types) is ignored.
    """
    parsed = []
    for entry in filetypes or ():
        label, patterns = entry[0], entry[1]
        if isinstance(patterns, str):
            patterns = patterns.split()
        normalized = []
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern:
                continue
            if pattern in ("*", "*.*"):
                normalized.append("*")
            elif pattern.startswith("."):
                normalized.append("*" + pattern)
            elif any(character in pattern for character in "*?["):
                normalized.append(pattern)
            else:
                normalized.append("*." + pattern)
        parsed.append((label, normalized or ["*"]))
    return parsed or [("All files", ["*"])]


def name_matches(name, patterns):
    """Whether a file name matches any of the glob patterns (ignoring case)."""
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in patterns)


def human_size(size):
    """A file size for people: '0 B', '812 B', '4.2 KB', '1.5 GB'..."""
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    return f"{int(value)} B" if unit == 0 else f"{value:.1f} {units[unit]}"


def format_modified(timestamp):
    """A modification time as 'YYYY-MM-DD HH:MM' (local time); '' if unknown."""
    if not timestamp:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))


def list_directory(
    directory, show_hidden=False, patterns=("*",), directories_only=False
):
    """Read a folder: returns (entries, error).

    Each entry is a dict: name, path, is_dir, size (0 for folders), and mtime.
    Hidden files (names starting with '.') are left out unless show_hidden.
    Files must match one of the patterns (folders always show); with
    directories_only, files are left out. If the folder cannot be read, the entries
    are empty and error is the OSError.
    """
    entries = []
    try:
        with os.scandir(directory) as items:
            for item in items:
                name = item.name
                if not show_hidden and name.startswith("."):
                    continue
                try:
                    is_dir = item.is_dir()
                except OSError:
                    is_dir = False
                if directories_only and not is_dir:
                    continue
                if not is_dir and not name_matches(name, patterns):
                    continue
                try:
                    info = item.stat()
                    size, mtime = info.st_size, info.st_mtime
                except OSError:  # for example, a broken link
                    size, mtime = 0, 0
                entries.append(
                    {
                        "name": name,
                        "path": item.path,
                        "is_dir": is_dir,
                        "size": 0 if is_dir else size,
                        "mtime": mtime,
                    }
                )
    except OSError as error:
        return [], error
    return entries, None


def sort_entries(entries, column="name", descending=False):
    """Sort directory entries by 'name', 'size', or 'mtime'; folders always first.

    Folders are ordered by name (or by time when sorting by time), files by the
    column, with the name as a tie-breaker. descending reverses each group.
    """
    by_name = lambda entry: entry["name"].lower()
    by_column = {
        "name": by_name,
        "size": lambda entry: (entry["size"], by_name(entry)),
        "mtime": lambda entry: (entry["mtime"], by_name(entry)),
    }[column]
    folder_key = by_column if column == "mtime" else by_name
    folders = sorted(
        (entry for entry in entries if entry["is_dir"]),
        key=folder_key,
        reverse=descending,
    )
    files = sorted(
        (entry for entry in entries if not entry["is_dir"]),
        key=by_column,
        reverse=descending,
    )
    return folders + files


def default_places():
    """The shortcuts of the sidebar as (label, path): home and its usual folders,
    mounted drives, and the file system root.
    """
    home = os.path.expanduser("~")
    places = [("Home", home)]
    for label in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
        path = os.path.join(home, label)
        if os.path.isdir(path):
            places.append((label, path))
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                places.append((drive, drive))
    else:
        user = os.path.basename(home)
        for base in (f"/media/{user}", f"/run/media/{user}", "/mnt"):
            if os.path.isdir(base):
                for name in sorted(os.listdir(base)):
                    path = os.path.join(base, name)
                    if os.path.isdir(path):
                        places.append((name, path))
        places.append(("File System", os.sep))
    return places


def resolve_path(text, directory):
    """What a typed path means: '~' and variables are expanded, a relative path is
    taken from `directory`, and the result is normalized. The result is always a full
    path (a relative `directory` is taken from the current folder).
    """
    text = os.path.expandvars(os.path.expanduser(text.strip()))
    return os.path.abspath(os.path.join(directory, text))


def with_default_extension(name, defaultextension):
    """`name` with the default extension added if it has none ('' / None = never)."""
    if not name or not defaultextension or os.path.splitext(name)[1]:
        return name
    if not defaultextension.startswith("."):
        defaultextension = "." + defaultextension
    return name + defaultextension


def filter_entries(entries, text):
    """The entries whose name contains `text` (ignoring case); all of them for no text."""
    text = text.lower()
    return [entry for entry in entries if text in entry["name"].lower()]


def complete_name(names, text):
    """`text` extended to the longest start shared by all the names that begin with
    it (ignoring case; the extra letters keep the case of the names). Returns `text`
    unchanged if no name begins with it or the names differ right after it.
    """
    matches = [name for name in names if name.lower().startswith(text.lower())]
    if not matches:
        return text
    common = os.path.commonprefix([name.lower() for name in matches])
    return text + matches[0][len(text) : len(common)]


def completion_candidates(
    text, directory, show_hidden=False, directories_only=True, patterns=("*",)
):
    """(head, matches) for a typed path: `head` is the text up to and including the
    last separator, and `matches` are the entries (sorted by name) of that folder
    whose names begin with the rest. Relative paths are taken from `directory`.
    Files are included unless directories_only, if they match the patterns.
    """
    head, separator, partial = text.rpartition(os.sep)
    head += separator
    if not partial:
        return head, []
    base = resolve_path(head, directory) if head else directory
    entries, error = list_directory(
        base,
        show_hidden=show_hidden or partial.startswith("."),
        patterns=patterns,
        directories_only=directories_only,
    )
    matches = [
        entry for entry in entries if entry["name"].lower().startswith(partial.lower())
    ]
    return head, sort_entries(matches, "name", False)


def completion_tail(partial, matches):
    """What to add after `partial` to suggest the entries `matches` (all begin with
    it): the letters they share, plus a separator when the only match is a folder.
    """
    if not matches:
        return ""
    tail = complete_name([entry["name"] for entry in matches], partial)[len(partial) :]
    if len(matches) == 1 and matches[0]["is_dir"]:
        tail += os.sep
    return tail


def complete_path(
    text, directory, show_hidden=False, directories_only=True, patterns=("*",)
):
    """A typed path with its last piece completed to the name of a folder (or, unless
    directories_only, of a file matching the patterns), ending with a separator when
    the only name that fits is a folder. Returns `text` unchanged when there is
    nothing to complete.
    """
    head, matches = completion_candidates(
        text, directory, show_hidden, directories_only, patterns
    )
    return text + completion_tail(text[len(head) :], matches)


def split_typed_names(text, multiple):
    """The file names in the Name field: one name, or with `multiple` any number
    separated by spaces (names with spaces in quotes, like '"a b.txt" c.txt').
    """
    text = text.strip()
    if not text:
        return []
    if not multiple:
        return [text]
    try:
        return shlex.split(text)
    except ValueError:  # an unbalanced quote: treat everything as one name
        return [text]


def path_segments(directory):
    """The folders leading to `directory`, root first, as [(label, path)].

    '/home/me/Docs' gives [('/', '/'), ('home', '/home'), ('me', '/home/me'),
    ('Docs', '/home/me/Docs')]; on Windows the first item is the drive.
    """
    segments = []
    current = os.path.normpath(directory)
    while True:
        parent, name = os.path.split(current)
        if not name:  # reached the root ('/' or a drive)
            segments.append((current, current))
            break
        segments.append((name, current))
        if parent == current:
            break
        current = parent
    return segments[::-1]


def quote_names(names):
    """The inverse of split_typed_names for several names (quote the ones with spaces)."""
    return " ".join(f'"{name}"' if " " in name else name for name in names)


# =============================================================================
# Small helpers for the dialog windows
# =============================================================================


def _ask_new_folder_name(parent):
    """Ask for the name of a new folder; returns the typed name, or None if cancelled."""
    window = Toplevel(
        parent,
        theme=dict(window_theme(parent)),
        appearance_mode=window_appearance_mode(parent),
    )
    window.title("New folder")
    window.resizable(False, False)
    answer = [None]
    body = Frame(window)
    body.pack(fill="both", expand=True, padx=18, pady=(16, 10))
    Label(body, "Name of the new folder:").pack(anchor="w")
    entry = Entry(body, width=38)
    entry.pack(fill="x", pady=(10, 0))

    def finish(accepted):
        """Remember the name (if accepted) and close."""
        answer[0] = entry.get() if accepted else None
        window.destroy()

    row = Frame(window)
    row.pack(fill="x", padx=18, pady=(0, 16))
    Button(row, "Create", command=lambda: finish(True)).pack(side="right", padx=(8, 0))
    Button(row, "Cancel", command=lambda: finish(False)).pack(side="right")
    window.bind("<Return>", lambda _: finish(True))
    window.bind("<Escape>", lambda _: finish(False))
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    entry.focus_set()
    _make_modal(window, parent)
    return answer[0]


# =============================================================================
# The file list and its header
# =============================================================================


class _FileList(Listbox):
    """The list of files and folders: Listbox rows drawn as icon, name, size, and
    modified time. Its items are the entry dicts of list_directory().
    """

    SIZE_WIDTH = 84
    MODIFIED_WIDTH = 140
    ICON_WIDTH = 24

    def column_positions(self):
        """(name_left, size_right, modified_left): the x positions of the columns
        in the current width (the header uses the same ones).
        """
        right = (
            self.winfo_width()
            - self.EDGE
            - (self.BAR_WIDTH + 4 if self._bar_visible() else 0)
        )
        modified_left = right - self.MODIFIED_WIDTH
        size_right = modified_left - 12
        return self.EDGE + 8 + self.ICON_WIDTH, size_right, modified_left

    def _fit(self, text, width):
        """`text` shortened with an ellipsis so that it is at most `width` px wide."""
        if width <= 0:
            return ""
        if self.font.measure(text) <= width:
            return text
        while text and self.font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def _draw_icon(self, is_dir, x, y):
        """Draw a small folder or page icon centered at (x, y)."""
        if is_dir:
            color = self.color("accent")
            self.create_rectangle(
                x - 8,
                y - 7,
                x - 1,
                y - 3,
                fill=color,
                outline="",
                tags=_CANVAS_CHROME_TAG,
            )
            self.create_rectangle(
                x - 8,
                y - 5,
                x + 8,
                y + 6,
                fill=color,
                outline="",
                tags=_CANVAS_CHROME_TAG,
            )
        else:
            outline = self.color("text_muted")
            self.create_rectangle(
                x - 6,
                y - 8,
                x + 6,
                y + 8,
                fill=self.color("surface"),
                outline=outline,
                tags=_CANVAS_CHROME_TAG,
            )
            for offset in (-3, 0, 3):
                self.create_line(
                    x - 3,
                    y + offset,
                    x + 3,
                    y + offset,
                    fill=outline,
                    tags=_CANVAS_CHROME_TAG,
                )

    def draw_row_content(self, row, top, bottom, right, color):
        """Draw a row: icon, the name (shortened to fit), the size, and the time."""
        entry = self._items[row]
        name_left, size_right, modified_left = self.column_positions()
        middle = (top + bottom) / 2
        self._draw_icon(entry["is_dir"], self.EDGE + 12, middle)
        # Size and time are secondary: muted, unless the row is selected/disabled.
        muted = (
            self.color("text_muted") if color == self.current_text_color() else color
        )
        self.create_text(
            name_left,
            middle,
            text=self._fit(entry["name"], size_right - self.SIZE_WIDTH - name_left),
            font=self.font,
            fill=color,
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )
        if not entry["is_dir"]:
            self.create_text(
                size_right,
                middle,
                text=human_size(entry["size"]),
                font=self.font,
                fill=muted,
                anchor="e",
                tags=_CANVAS_CHROME_TAG,
            )
        self.create_text(
            modified_left,
            middle,
            text=format_modified(entry["mtime"]),
            font=self.font,
            fill=muted,
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )


class _FileListHeader(CanvasWidget):
    """The Name / Size / Modified header above the file list; clicking a column
    sorts by it (clicking it again reverses the order).
    """

    def __init__(self, master, file_list, on_sort, **kwargs):
        """`file_list` supplies the column positions; on_sort(column) is called with
        'name', 'size', or 'mtime'.
        """
        kwargs.setdefault("height", 28)
        kwargs.setdefault("width", 100)
        super().__init__(master, **kwargs)
        self.file_list = file_list
        self.on_sort = on_sort
        self.sort_column = "name"
        self.descending = False
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.schedule_redraw()

    def set_sort(self, column, descending):
        """Show which column the list is sorted by, and in which direction."""
        self.sort_column = column
        self.descending = descending
        self.schedule_redraw()

    def _column_at(self, x):
        """The column ('name', 'size', 'mtime') under an x coordinate."""
        _, size_right, modified_left = self.file_list.column_positions()
        if x >= modified_left - 6:
            return "mtime"
        if x >= size_right - self.file_list.SIZE_WIDTH:
            return "size"
        return "name"

    def _on_press(self, event):
        """Click on a column title: sort by that column."""
        self.on_sort(self._column_at(event.x))

    def redraw(self, width, height):
        """Draw the header background, the three titles, and the sort chevron."""
        self.draw_box(
            0,
            0,
            width,
            height,
            self.color("neutral"),
            radius=self.colors["small_radius"],
        )
        name_left, size_right, modified_left = self.file_list.column_positions()
        color = self.color("text_muted")
        titles = (
            ("name", "Name", name_left, "w", 1),
            ("size", "Size", size_right, "e", -1),
            ("mtime", "Modified", modified_left, "w", 1),
        )
        for column, title, x, anchor, side in titles:
            self.create_text(
                x,
                height / 2,
                text=title,
                font=self.font,
                fill=self.color("text") if column == self.sort_column else color,
                anchor=anchor,
                tags=_CANVAS_CHROME_TAG,
            )
            if column == self.sort_column:
                text_width = self.font.measure(title)
                # The chevron sits on the text's inner side (right of left-aligned
                # titles, left of right-aligned ones).
                chevron_x = x + side * (text_width + 12)
                self.draw_chevron(
                    chevron_x, height / 2, "down" if self.descending else "up", color
                )


class _NameList(_FileList):
    """The rows of the suggestion dropdown: an icon and the name."""

    def draw_row_content(self, row, top, bottom, right, color):
        """Draw a row: icon and the name (shortened to fit)."""
        entry = self._items[row]
        middle = (top + bottom) / 2
        self._draw_icon(entry["is_dir"], self.EDGE + 12, middle)
        left = self.EDGE + 8 + self.ICON_WIDTH
        self.create_text(
            left,
            middle,
            text=self._fit(entry["name"], right - left - 8),
            font=self.font,
            fill=color,
            anchor="w",
            tags=_CANVAS_CHROME_TAG,
        )


class _CompletionDropdown:
    """The list of names that fit what is typed in an Entry, shown just below it
    when there is more than one. The Entry keeps the keyboard focus: its Up and
    Down keys move through the list, and a click picks a name.
    """

    VISIBLE_ROWS = 8

    def __init__(self, entry, on_pick):
        """`entry` is the Entry it belongs to; on_pick(item, head) is called with the
        chosen entry dict and the typed text before the name (see show()).
        """
        self.entry = entry
        self.on_pick = on_pick
        self.window = None
        self.list = None
        self.head = ""
        entry.bind(
            "<FocusOut>", lambda _: entry.after(150, self._hide_if_unfocused), add="+"
        )

    def visible(self):
        """Whether the dropdown is on screen."""
        return self.window is not None

    def show(self, matches, head):
        """Show the entry dicts `matches` below the Entry; `head` is the typed text
        before the part being completed (a folder path, or '').
        """
        self.hide()
        self.head = head
        owner = self.entry.winfo_toplevel()
        window = Toplevel(
            owner,
            theme=dict(window_theme(owner)),
            appearance_mode=window_appearance_mode(owner),
            transient=False,
        )
        window.withdraw()
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        listbox = _NameList(window, scrolled=True, row_padding=6)
        listbox.pack(fill="both", expand=True)
        listbox.insert("end", *matches)
        listbox.bind("<ButtonRelease-1>", self._on_click, add="+")
        rows = min(len(matches), self.VISIBLE_ROWS)
        row_height = listbox.font.metrics("linespace") + listbox.row_padding
        height = rows * row_height + 2 * listbox.EDGE + 4
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        window.geometry(f"{self.entry.winfo_width()}x{height}+{x}+{y}")
        window.deiconify()
        window.lift()
        self.window, self.list = window, listbox

    def hide(self):
        """Remove the dropdown."""
        if self.window is not None:
            self.window.destroy()
            self.window = self.list = None

    def _hide_if_unfocused(self):
        """Hide the dropdown once the keyboard focus is neither in the Entry nor in it."""
        if self.window is None:
            return
        focus = self.entry.focus_get()
        if focus is self.entry.inner or str(focus).startswith(str(self.window)):
            return
        self.hide()

    def move(self, step):
        """Highlight the next (+1) or previous (-1) name."""
        count = self.list.size()
        chosen = self.list.curselection()
        if chosen:
            index = max(0, min(count - 1, chosen[0] + step))
        else:
            index = 0 if step > 0 else count - 1
        self.list.selection_clear(0, "end")
        self.list.selection_set(index)
        self.list.see(index)

    def highlighted(self):
        """The highlighted entry dict, or None."""
        chosen = self.list.curselection() if self.list else ()
        return self.list.get(chosen[0]) if chosen else None

    def pick(self, item):
        """Choose a name: hide the dropdown and tell the owner."""
        head = self.head
        self.hide()
        self.entry.focus_set()
        self.on_pick(item, head)

    def _on_click(self, event):
        """Click on a row: choose that name."""
        index = self.list.nearest(event.y)
        if 0 <= index < self.list.size():
            self.pick(self.list.get(index))


# Keys that only move the cursor or change focus; releasing them never changes text.
_FILE_DIALOG_NON_TEXT_KEYS = frozenset(
    "Left Right Up Down Home End Prior Next Tab ISO_Left_Tab Return KP_Enter Escape "
    "Shift_L Shift_R Control_L Control_R Alt_L Alt_R Meta_L Meta_R Super_L Super_R "
    "Caps_Lock Num_Lock Insert".split()
)


class _InlineCompletion:
    """A suggestion shown in an Entry as selected text after what was typed, like the
    file dialogs of Linux desktops: Tab or Return accepts it, Escape hides it until
    the next time something is typed.
    """

    def __init__(self, entry):
        """`entry` is the Entry that shows the suggestion."""
        self.entry = entry
        self.length = (
            0  # how many characters at the end of the entry are the suggestion
        )

    def visible(self):
        """Whether a suggestion is showing (still selected at the end of the entry)."""
        if not self.length or not self.entry.selection_present():
            return False
        end = len(self.entry.get())
        return (
            self.entry.index("sel.first") == end - self.length
            and self.entry.index("sel.last") == end
        )

    def show(self, tail):
        """Add `tail` after the text, selected."""
        start = len(self.entry.get())
        self.entry.insert("end", tail)
        self.entry.select_range(start, "end")
        self.entry.icursor("end")
        self.length = len(tail)

    def accept(self):
        """Make the suggestion part of the text."""
        self.entry.selection_clear()
        self.entry.icursor("end")
        self.length = 0

    def dismiss(self):
        """Remove the suggestion."""
        if self.visible():
            self.entry.delete(len(self.entry.get()) - self.length, "end")
        self.length = 0


class _PathBar(CanvasWidget):
    """The current folder as a row of clickable pieces: / > home > me > Documents.

    Clicking a piece goes to that folder (an easy way out of the folder you are
    in); clicking the empty space after the last piece asks to edit the path as
    text. When the path is too long for the width, the first pieces collapse into
    a "…" piece that goes to the closest hidden folder.
    """

    PIECE_PADDING = 8
    SEPARATOR_WIDTH = 14

    def __init__(self, master, on_navigate, on_edit, **kwargs):
        """on_navigate(path) is called for a click on a piece; on_edit() for a click
        on the empty space.
        """
        kwargs.setdefault("height", 34)
        kwargs.setdefault("width", 200)
        super().__init__(master, **kwargs)
        self.on_navigate = on_navigate
        self.on_edit = on_edit
        self.segments = []
        self._pieces = []
        self._hover = None
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")

    def set_directory(self, directory):
        """Show the path of a folder."""
        self.segments = path_segments(directory)
        self.schedule_redraw()

    def _piece_at(self, x):
        """The index in self._pieces of the piece under an x coordinate, or None."""
        for index, (left, right, _) in enumerate(self._pieces):
            if left <= x < right:
                return index
        return None

    def _on_motion(self, event):
        """Pointer moved: highlight the piece under it (a hand), or show the text
        cursor over the empty space (where a click edits the path).
        """
        index = self._piece_at(event.x)
        cursor = "hand2" if index is not None else "xterm"
        if cursor != self.cget("cursor"):
            self.configure(cursor=cursor)
        if index != self._hover:
            self._hover = index
            self.schedule_redraw()

    def _on_leave(self, _):
        """Pointer left: remove the highlight."""
        if self._hover is not None:
            self._hover = None
            self.schedule_redraw()

    def _on_press(self, event):
        """Click: go to the folder of a piece, or edit the path."""
        index = self._piece_at(event.x)
        if index is None:
            self.on_edit()
        else:
            self.on_navigate(self._pieces[index][2])

    def redraw(self, width, height):
        """Draw the frame and the pieces that fit (the end of the path is always shown)."""
        self.draw_box(
            0, 0, width, height, self.color("surface"), self.color("border"), 1, 8
        )
        padding, separator = self.PIECE_PADDING, self.SEPARATOR_WIDTH
        widths = [self.font.measure(label) + 2 * padding for label, _ in self.segments]
        ellipsis_width = self.font.measure("…") + 2 * padding
        available = width - 16
        # Drop pieces from the start until the rest fits (with a "…" piece in front).
        start = 0
        while start < len(self.segments) - 1:
            used = sum(widths[start:]) + separator * (len(self.segments) - start - 1)
            if start:
                used += ellipsis_width + separator
            if used <= available:
                break
            start += 1
        pieces = []
        if start:
            pieces.append(("…", self.segments[start - 1][1], ellipsis_width))
        for (label, path), piece_width in zip(self.segments[start:], widths[start:]):
            pieces.append((label, path, piece_width))
        self._pieces = []
        x = 8
        for index, (label, path, piece_width) in enumerate(pieces):
            last = index == len(pieces) - 1
            if index == self._hover:
                self.draw_box(
                    x,
                    5,
                    x + piece_width,
                    height - 5,
                    self.color("row_current"),
                    radius=self.colors["small_radius"],
                )
            self.create_text(
                x + piece_width / 2,
                height / 2,
                text=label,
                font=self.font,
                fill=self.color("text" if last else "text_muted"),
                tags=_CANVAS_CHROME_TAG,
            )
            self._pieces.append((x, x + piece_width, path))
            x += piece_width
            if not last:
                self.draw_chevron(
                    x + separator / 2,
                    height / 2,
                    "right",
                    self.color("text_disabled"),
                    size=3,
                    width=1.5,
                )
                x += separator


# =============================================================================
# The dialog
# =============================================================================


class _FileDialog:
    """One open / save / choose-folder dialog. Create it, then show() it."""

    MODES = ("open", "save", "directory")
    SIZE = (820, 540)

    def __init__(
        self,
        mode,
        parent=None,
        title=None,
        initialdir=None,
        initialfile=None,
        filetypes=None,
        defaultextension="",
        multiple=False,
        mustexist=False,
        confirmoverwrite=True,
        typevariable=None,
    ):
        """Store the options and work out the starting folder and file name.

        mode is 'open', 'save', or 'directory'; the other arguments are the
        tkinter.filedialog options of the same names.
        """
        global _LAST_FILE_DIALOG_DIRECTORY
        self.mode = mode
        self.multiple = multiple
        self.mustexist = mustexist
        self.confirmoverwrite = confirmoverwrite
        self.defaultextension = defaultextension
        self.typevariable = typevariable
        self.filetypes = parse_filetypes(filetypes)
        self.title = (
            title
            or {
                "open": "Open",
                "save": "Save As",
                "directory": "Select Folder",
            }[mode]
        )
        self.parent = parent
        # Where to start: initialdir, else the last dialog's folder, else here.
        start = initialdir or _LAST_FILE_DIALOG_DIRECTORY or os.getcwd()
        self.initial_name = ""
        if initialfile:
            folder, self.initial_name = os.path.split(initialfile)
            if folder:
                start = resolve_path(folder, start)
        start = os.path.abspath(os.path.expanduser(str(start)))
        self.start_directory = start if os.path.isdir(start) else os.getcwd()
        self.result = () if (mode == "open" and multiple) else ""
        self.directory = self.start_directory
        self.history = []
        self.history_index = -1
        self.sort_column = "name"
        self.sort_descending = False
        self.entries = []
        self.name_filter = ""  # the typed text that narrows the list
        self.last_typed_name = ""  # the Name field as last handled by _on_name_typed
        self._typed = ""
        self._typed_at = 0.0

    # ---- showing the dialog -----------------------------------------------------
    def show(self):
        """Open the dialog, wait until it is closed, and return the result
        (a path, a tuple of paths, or '' / () if it was cancelled).
        """
        temporary_root = None
        owner = _parent_toplevel(self.parent)
        if owner is None:  # like tkinter: make a root if the program has none
            temporary_root = owner = Window()
            owner.withdraw()
        try:
            self._build(owner)
            _make_modal(self.window, owner, self.SIZE)
        finally:
            if temporary_root is not None:
                temporary_root.destroy()
        return self.result

    def _build(self, owner):
        """Create the window and every widget, then show the starting folder."""
        self.window = window = Toplevel(
            owner,
            theme=dict(window_theme(owner)),
            appearance_mode=window_appearance_mode(owner),
        )
        window.title(self.title)
        window.geometry("%dx%d" % self.SIZE)
        window.minsize(580, 380)
        theme = window.get_theme()
        self.show_hidden = tk.BooleanVar(window, value=False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        # --- top row: back / forward / up, the path, new folder, hidden files
        top = Frame(window)
        top.pack(fill="x", padx=10, pady=(10, 6))
        self.back_button = Button(
            top, "←", command=self.go_back, radius=8, padx=9, pady=3
        )
        self.forward_button = Button(
            top, "→", command=self.go_forward, radius=8, padx=9, pady=3
        )
        self.up_button = Button(top, "↑", command=self.go_up, radius=8, padx=9, pady=3)
        for button in (self.back_button, self.forward_button, self.up_button):
            button.pack(side="left", padx=(0, 4))
        # The path is a clickable bar; it is swapped for an Entry while being edited.
        path_holder = Frame(top)
        path_holder.pack(side="left", fill="x", expand=True, padx=8)
        self.path_bar = _PathBar(path_holder, self.navigate, self._focus_path)
        self.path_bar.pack(fill="x")
        self.path_entry = Entry(path_holder)
        self.path_completion = _InlineCompletion(self.path_entry)
        self.path_dropdown = _CompletionDropdown(
            self.path_entry, self._pick_path_suggestion
        )
        self.path_entry.bind(
            "<Down>", lambda _: self._move_in_dropdown(self.path_dropdown, 1)
        )
        self.path_entry.bind(
            "<Up>", lambda _: self._move_in_dropdown(self.path_dropdown, -1)
        )
        self.path_entry.bind("<Return>", self._on_path_return)
        self.path_entry.bind("<Tab>", self._on_path_tab)
        self.path_entry.bind("<KeyRelease>", self._on_path_typed)
        self.path_entry.bind("<Escape>", self._on_path_escape)
        self.path_entry.bind("<FocusOut>", lambda _: self._show_path_bar())
        if self.mode != "open":
            Button(
                top, "New folder", command=self.new_folder, radius=8, padx=10, pady=3
            ).pack(side="left", padx=(0, 8))
        Checkbutton(
            top, "Hidden", variable=self.show_hidden, command=self.refresh
        ).pack(side="left")

        # --- middle: places on the left, the sortable file list on the right
        panes = Panedwindow(window, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10)
        self.places = default_places()
        self.places_list = Listbox(
            panes, [label for label, _ in self.places], width=15, scrolled=True
        )
        self.places_list.bind("<<ListboxSelect>>", self._on_place_selected)
        panes.add(self.places_list, weight=0)
        main = Frame(panes)
        panes.add(main, weight=1)
        self.file_list = _FileList(
            main,
            width=52,
            height=14,
            scrolled=True,
            selectmode=(
                "extended" if (self.mode == "open" and self.multiple) else "browse"
            ),
        )
        self.header = _FileListHeader(main, self.file_list, self.sort_by)
        self.header.pack(fill="x", pady=(0, 4))
        self.file_list.pack(fill="both", expand=True)
        self.file_list.bind("<<ListboxSelect>>", self._on_selection_changed)
        self.file_list.bind("<Double-Button-1>", self._on_double_click)
        self.file_list.bind("<Return>", lambda _: self.accept())
        self.file_list.bind("<Button-3>", self._show_context_menu)
        self.file_list.bind("<KeyPress>", self._type_ahead, add="+")
        self.file_list.bind(
            "<Configure>", lambda _: self.header.schedule_redraw(), add="+"
        )

        # --- bottom: the file name, the file type, and the buttons
        bottom = Frame(window)
        bottom.pack(fill="x", padx=10, pady=10)
        bottom.grid_columnconfigure(1, weight=1)
        Label(bottom, "Folder:" if self.mode == "directory" else "Name:").grid(
            row=0, column=0, sticky="w"
        )
        self.name_entry = Entry(bottom)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=(0, 6))
        self.name_entry.insert(0, self.initial_name)
        self.name_completion = _InlineCompletion(self.name_entry)
        self.name_dropdown = _CompletionDropdown(
            self.name_entry, self._pick_name_suggestion
        )
        self.name_entry.bind(
            "<Down>", lambda _: self._move_in_dropdown(self.name_dropdown, 1)
        )
        self.name_entry.bind(
            "<Up>", lambda _: self._move_in_dropdown(self.name_dropdown, -1)
        )
        self.name_entry.bind("<Return>", self._on_name_return)
        self.name_entry.bind("<Tab>", self._on_name_tab)
        self.name_entry.bind("<Escape>", self._on_name_escape)
        self.name_entry.bind("<KeyRelease>", self._on_name_typed)
        self.type_box = None
        if self.mode != "directory":
            Label(bottom, "Type:").grid(row=1, column=0, sticky="w")
            self.type_box = Combobox(
                bottom,
                values=[
                    self._type_text(label, patterns)
                    for label, patterns in self.filetypes
                ],
                state="readonly",
            )
            self.type_box.grid(row=1, column=1, sticky="ew", padx=8)
            self.type_box.current(self._initial_type_index())
            self.type_box.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        buttons = Frame(bottom)
        buttons.grid(row=0, column=2, rowspan=2, sticky="e")
        accept_text = {"open": "Open", "save": "Save", "directory": "Select"}[self.mode]
        Button(buttons, accept_text, command=self.accept).pack(side="right")
        Button(
            buttons,
            "Cancel",
            command=self.cancel,
            default_bg=theme["neutral"],
            default_fg=theme["text"],
        ).pack(side="right", padx=(0, 8))

        # --- keyboard shortcuts for the whole dialog
        window.bind("<Escape>", lambda _: self.cancel())
        window.bind("<Alt-Left>", lambda _: self.go_back())
        window.bind("<Alt-Right>", lambda _: self.go_forward())
        window.bind("<Alt-Up>", lambda _: self.go_up())
        window.bind("<F5>", lambda _: self.refresh())
        window.bind("<Control-h>", lambda _: self._toggle_hidden())
        window.bind("<Control-l>", lambda _: self._focus_path())

        self.navigate(self.start_directory)
        if self.initial_name and self.mode == "open":
            self._select_names([self.initial_name])
        (self.name_entry if self.mode != "open" else self.file_list).focus_set()

    # ---- file types --------------------------------------------------------------
    @staticmethod
    def _type_text(label, patterns):
        """The text of a filter in the Type box: 'Images (*.png *.jpg)'."""
        return label if patterns == ["*"] else f"{label} ({' '.join(patterns)})"

    def _initial_type_index(self):
        """The filter to start with: the one named by typevariable if it is set,
        else the first one.
        """
        if self.typevariable is not None:
            wanted = self.typevariable.get()
            for index, (label, _) in enumerate(self.filetypes):
                if label == wanted:
                    return index
        return 0

    def _current_type(self):
        """(label, patterns) of the selected filter ('*' for everything in
        directory mode).
        """
        if self.type_box is None:
            return "", ["*"]
        return self.filetypes[max(self.type_box.current(), 0)]

    # ---- navigation ---------------------------------------------------------------
    def navigate(self, directory, push=True, select=()):
        """Show a folder; returns False (and tells the user) if it cannot be read.

        push adds it to the back/forward history; `select` names to select in it.
        """
        global _LAST_FILE_DIALOG_DIRECTORY
        directory = os.path.normpath(directory)
        _, patterns = self._current_type()
        entries, error = list_directory(
            directory,
            show_hidden=self.show_hidden.get(),
            patterns=patterns,
            directories_only=self.mode == "directory",
        )
        if error is not None:
            self._message(
                "Cannot open folder", f"{directory}\n\n{error.strerror or error}"
            )
            return False
        self.directory = directory
        _LAST_FILE_DIALOG_DIRECTORY = directory
        self.entries = entries
        self.name_filter = ""
        self.name_dropdown.hide()
        self.path_dropdown.hide()
        if push:
            del self.history[self.history_index + 1 :]
            if not self.history or self.history[-1] != directory:
                self.history.append(directory)
            self.history_index = len(self.history) - 1
        self.path_bar.set_directory(directory)
        self._update_buttons()
        self._populate(select)
        return True

    def _update_buttons(self):
        """Enable the back / forward / up buttons according to the history and
        whether there is a parent folder.
        """
        self.back_button.configure(
            state="normal" if self.history_index > 0 else "disabled"
        )
        self.forward_button.configure(
            state="normal" if self.history_index < len(self.history) - 1 else "disabled"
        )
        self.up_button.configure(
            state=(
                "normal"
                if os.path.dirname(self.directory) != self.directory
                else "disabled"
            )
        )

    def _populate(self, select=()):
        """Fill the file list from self.entries in the current sort order."""
        shown = filter_entries(self.entries, self.name_filter)
        ordered = sort_entries(shown, self.sort_column, self.sort_descending)
        self.file_list.delete(0, "end")
        self.file_list.insert("end", *ordered)
        self.file_list.yview_moveto(0)
        self.header.set_sort(self.sort_column, self.sort_descending)
        self._select_names(select)
        self._clear_places_selection()

    def _select_names(self, names):
        """Select the rows with these names (and scroll to the first)."""
        self.file_list.selection_clear(0, "end")
        first = None
        for index in range(self.file_list.size()):
            if self.file_list.get(index)["name"] in names:
                self.file_list.selection_set(index)
                first = index if first is None else first
        if first is not None:
            self.file_list.see(first)

    def _clear_places_selection(self):
        """Deselect the sidebar (the folder shown is no longer necessarily a place)."""
        self.places_list.selection_clear(0, "end")

    def go_back(self):
        """Go to the previous folder in the history."""
        if self.history_index > 0:
            self.history_index -= 1
            self.navigate(self.history[self.history_index], push=False)

    def go_forward(self):
        """Go to the next folder in the history."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.navigate(self.history[self.history_index], push=False)

    def go_up(self):
        """Go to the parent folder (selecting the folder we came from)."""
        parent = os.path.dirname(self.directory)
        if parent != self.directory:
            self.navigate(parent, select=[os.path.basename(self.directory)])

    def refresh(self):
        """Read the current folder again (also applies the filter and hidden files)."""
        selected = [entry["name"] for entry in self._selected_entries()]
        self.navigate(self.directory, push=False, select=selected)

    def _toggle_hidden(self):
        """Control-h: show or hide hidden files."""
        self.show_hidden.set(not self.show_hidden.get())
        self.refresh()

    def _focus_path(self):
        """Control-l or a click on the empty part of the path bar: edit the path as text."""
        self.path_bar.pack_forget()
        self.path_entry.pack(fill="x")
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, self.directory)
        self.path_entry.focus_set()
        self.path_entry.select_range(0, "end")

    def _show_path_bar(self):
        """Stop editing the path and show the clickable bar again."""
        if self.path_entry.winfo_ismapped():
            self.path_entry.pack_forget()
            self.path_bar.pack(fill="x")

    def _go_to_typed_path(self, _event=None):
        """Return in the path bar: open the folder typed there (for a file, open
        its folder and select it).
        """
        path = resolve_path(self.path_entry.get(), self.directory)
        self._show_path_bar()
        if os.path.isdir(path):
            self.navigate(path)
        elif os.path.exists(path):
            self.navigate(os.path.dirname(path), select=[os.path.basename(path)])
        else:
            self._message("Not found", f"{path}\n\nThat path does not exist.")

    def _on_place_selected(self, _event=None):
        """A place in the sidebar was clicked: go there."""
        chosen = self.places_list.curselection()
        if chosen:
            self.navigate(self.places[chosen[0]][1])
            # navigate() cleared the selection; keep the clicked place marked.
            self.places_list.selection_set(chosen[0])

    def sort_by(self, column):
        """Sort by a column; the same column again reverses the order."""
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column, self.sort_descending = column, False
        self._populate([entry["name"] for entry in self._selected_entries()])

    # ---- selection -----------------------------------------------------------------
    def _selected_entries(self):
        """The entry dicts of the selected rows."""
        return [self.file_list.get(index) for index in self.file_list.curselection()]

    def _on_selection_changed(self, _event=None):
        """The selection changed: put the selected names in the Name field."""
        entries = self._selected_entries()
        if self.mode == "directory":
            names = [entry["name"] for entry in entries]
        else:
            names = [entry["name"] for entry in entries if not entry["is_dir"]]
        if not names:
            return  # selecting only folders leaves what was typed alone
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, quote_names(names) if self.multiple else names[0])
        self.last_typed_name = self.name_entry.get()

    @staticmethod
    def _move_in_dropdown(dropdown, step):
        """Up / Down in an Entry: move through its dropdown if it is showing."""
        if not dropdown.visible():
            return None
        dropdown.move(step)
        return "break"

    def _name_candidates(self, typed):
        """(head, matches) for the text in the Name field: a path completes from the
        folder it points into; a plain name completes from the current list.
        """
        if os.sep in typed or typed.startswith("~"):
            return completion_candidates(
                typed,
                self.directory,
                self.show_hidden.get(),
                self.mode == "directory",
                self._current_type()[1],
            )
        matches = [
            e for e in self.entries if e["name"].lower().startswith(typed.lower())
        ]
        return "", sort_entries(matches, "name", False)

    def _on_name_typed(self, event):
        """Typing in the Name field: narrow the list to the names containing the
        text, suggest the rest of a name that begins with it (not after BackSpace or
        Delete), and show a dropdown when several names fit.
        """
        text = self.name_entry.get()
        if event.keysym in _FILE_DIALOG_NON_TEXT_KEYS or text == self.last_typed_name:
            return
        typed = text.strip()
        # A path (Dir/file, /file, ~/file) or several quoted names do not narrow the list.
        is_path = os.sep in typed or typed.startswith("~")
        filter_text = "" if is_path or '"' in typed or not typed.strip(".") else typed
        deleting = event.keysym in ("BackSpace", "Delete")
        self.name_dropdown.hide()
        if typed and '"' not in typed:
            head, matches = self._name_candidates(typed)
            if not deleting and typed == text:
                tail = completion_tail(typed[len(head) :], matches)
                if tail:
                    self.name_completion.show(tail)
            if len(matches) > 1:
                self.name_dropdown.show(matches, head)
        self.last_typed_name = self.name_entry.get()
        if filter_text != self.name_filter:
            self.name_filter = filter_text
            self._populate()

    def _pick_name_suggestion(self, item, head):
        """A name was chosen in the Name field's dropdown: a file only fills the
        field (and selects it in the list); a folder is entered.
        """
        self.name_completion.length = 0
        if item["is_dir"]:
            self.name_entry.delete(0, "end")
            self.last_typed_name = ""
            self.navigate(item["path"])
            return
        text = head + item["name"]
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, text)
        self.name_entry.icursor("end")
        self.last_typed_name = text
        self.name_filter = "" if head else text
        self._populate(select=[item["name"]] if not head else ())

    def _on_name_tab(self, _event):
        """Tab in the Name field: take the highlighted name or the suggestion
        (otherwise move on).
        """
        highlighted = self.name_dropdown.highlighted()
        if highlighted is not None:
            self.name_dropdown.pick(highlighted)
        elif self.name_completion.visible():
            self._accept_name_completion()
        else:
            return None
        return "break"

    def _on_name_return(self, _event):
        """Return in the Name field: take the highlighted name or the suggestion, or
        else accept the dialog.
        """
        highlighted = self.name_dropdown.highlighted()
        if highlighted is not None:
            self.name_dropdown.pick(highlighted)
        elif self.name_completion.visible():
            self._accept_name_completion()
        else:
            self.name_dropdown.hide()
            self.accept()
        return "break"

    def _on_name_escape(self, _event):
        """Escape in the Name field: hide the suggestion and the dropdown (otherwise
        cancel the dialog).
        """
        if not (self.name_completion.visible() or self.name_dropdown.visible()):
            return None
        self.name_dropdown.hide()
        self.name_completion.dismiss()
        self.last_typed_name = self.name_entry.get()
        return "break"

    def _accept_name_completion(self):
        """Keep the suggested name and select its row in the list."""
        self.name_dropdown.hide()
        self.name_completion.accept()
        text = self.name_entry.get()
        self.last_typed_name = text
        if os.sep not in text and not text.startswith("~"):
            self.name_filter = text
            self._populate(select=[text])

    def _on_path_typed(self, event):
        """Typing in the path field: suggest the rest of a folder name (not after
        BackSpace or Delete), and show a dropdown when several folders fit.
        """
        if event.keysym in _FILE_DIALOG_NON_TEXT_KEYS:
            return
        self.path_dropdown.hide()
        text = self.path_entry.get()
        head, matches = completion_candidates(
            text, self.directory, self.show_hidden.get()
        )
        if event.keysym not in ("BackSpace", "Delete"):
            tail = completion_tail(text[len(head) :], matches)
            if tail:
                self.path_completion.show(tail)
        if len(matches) > 1:
            self.path_dropdown.show(matches, head)

    def _pick_path_suggestion(self, item, _head):
        """A folder was chosen in the path field's dropdown: enter it."""
        self.path_completion.length = 0
        self._show_path_bar()
        self.navigate(item["path"])

    def _on_path_tab(self, _event):
        """Tab in the path field: take the highlighted folder or the suggestion."""
        highlighted = self.path_dropdown.highlighted()
        if highlighted is not None:
            self.path_dropdown.pick(highlighted)
        else:
            self.path_dropdown.hide()
            self.path_completion.accept()
        return "break"

    def _on_path_return(self, _event):
        """Return in the path field: take the highlighted folder or the suggestion,
        or else open the path.
        """
        highlighted = self.path_dropdown.highlighted()
        if highlighted is not None:
            self.path_dropdown.pick(highlighted)
        elif self.path_completion.visible():
            self.path_dropdown.hide()
            self.path_completion.accept()
        else:
            self._go_to_typed_path()
        return "break"

    def _on_path_escape(self, _event):
        """Escape in the path field: hide the suggestion and the dropdown, or else
        stop editing.
        """
        if self.path_completion.visible() or self.path_dropdown.visible():
            self.path_dropdown.hide()
            self.path_completion.dismiss()
        else:
            self._show_path_bar()
        return "break"

    def _on_double_click(self, event):
        """Double click: open a folder, or accept a file."""
        entries = self._selected_entries()
        if not entries:
            return
        entry = entries[0]
        if entry["is_dir"]:
            self.navigate(entry["path"])
        else:
            self.accept()

    def _type_ahead(self, event):
        """Typing letters in the list jumps to the first name starting with them."""
        if not event.char or not event.char.isprintable() or event.char == " ":
            return
        now = time.monotonic()
        self._typed = (
            self._typed if now - self._typed_at < 1.0 else ""
        ) + event.char.lower()
        self._typed_at = now
        for index in range(self.file_list.size()):
            if self.file_list.get(index)["name"].lower().startswith(self._typed):
                self.file_list.selection_clear(0, "end")
                self.file_list.selection_set(index)
                self.file_list.activate(index)
                self.file_list.see(index)
                self._on_selection_changed()
                break

    def _show_context_menu(self, event):
        """Right click in the list: New folder (not when opening), Refresh, Show hidden files."""
        menu = Menu(self.window)
        if self.mode != "open":
            menu.add_command(label="New folder", command=self.new_folder)
        menu.add_command(label="Refresh", accelerator="F5", command=self.refresh)
        menu.add_checkbutton(
            label="Show hidden files",
            accelerator="Ctrl+H",
            variable=self.show_hidden,
            command=self.refresh,
        )
        menu.post(event.x_root, event.y_root, owner=self.window)

    # ---- actions --------------------------------------------------------------------
    def new_folder(self):
        """Ask for a name and make a new folder in the current one."""
        name = (_ask_new_folder_name(self.window) or "").strip()
        if not name:
            return
        path = resolve_path(name, self.directory)
        try:
            os.mkdir(path)
        except OSError as error:
            self._message(
                "Cannot create folder", f"{path}\n\n{error.strerror or error}"
            )
            return
        self.navigate(self.directory, push=False, select=[os.path.basename(path)])

    def _message(self, title, text):
        """Show an error / information box over the dialog."""
        messagebox.showerror(title, text, parent=self.window)

    def _confirm(self, title, text):
        """Ask a yes / no question over the dialog."""
        return messagebox.askyesno(
            title, text, parent=self.window, default=messagebox.NO
        )

    def cancel(self):
        """Close without choosing anything (the result stays empty)."""
        self.window.destroy()

    def _finish(self, result):
        """Remember the answer (and the chosen filter) and close the dialog."""
        self.result = result
        if self.typevariable is not None and self.type_box is not None:
            self.typevariable.set(self._current_type()[0])
        self.window.destroy()

    def accept(self):
        """The Open / Save / Select button, Return, or a double click on a file."""
        if self.mode == "directory":
            self._accept_directory()
        elif self.mode == "save":
            self._accept_save()
        else:
            self._accept_open()

    def _accept_open(self):
        """Open: the typed names, else the selected files; a single folder is
        entered instead.
        """
        names = split_typed_names(self.name_entry.get(), self.multiple)
        if not names:
            entries = self._selected_entries()
            if len(entries) == 1 and entries[0]["is_dir"]:
                self.navigate(entries[0]["path"])
                return
            names = [entry["name"] for entry in entries if not entry["is_dir"]]
        if not names:
            self._message("Nothing selected", "Choose a file first.")
            return
        paths = [resolve_path(name, self.directory) for name in names]
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.name_entry.delete(0, "end")
            self.navigate(paths[0])
            return
        for path in paths:
            if not os.path.isfile(path):
                self._message(
                    "File not found", f"{path}\n\nCheck the name and try again."
                )
                return
        self._finish(tuple(paths) if self.multiple else paths[0])

    def _accept_save(self):
        """Save: the typed name (a folder is entered instead), with the default
        extension added; asks before overwriting.
        """
        name = self.name_entry.get().strip()
        if not name:
            self._message("No file name", "Type a name for the file.")
            return
        path = resolve_path(name, self.directory)
        if os.path.isdir(path):
            self.name_entry.delete(0, "end")
            self.navigate(path)
            return
        path = with_default_extension(path, self.defaultextension)
        if not os.path.isdir(os.path.dirname(path)):
            self._message(
                "Folder not found",
                f"{os.path.dirname(path)}\n\nThat folder does not exist.",
            )
            return
        if os.path.exists(path) and self.confirmoverwrite:
            if not self._confirm(
                "Replace file?",
                f"{os.path.basename(path)} already exists.\nDo you want to replace it?",
            ):
                return
        self._finish(path)

    def _accept_directory(self):
        """Select: the typed folder, else the selected folder, else the current one."""
        text = self.name_entry.get().strip()
        if text:
            path = resolve_path(text, self.directory)
        else:
            entries = self._selected_entries()
            path = entries[0]["path"] if entries else self.directory
        if self.mustexist and not os.path.isdir(path):
            self._message("Folder not found", f"{path}\n\nThat folder does not exist.")
            return
        self._finish(path)


# =============================================================================
# The tkinter.filedialog API
# =============================================================================

# Options the dialogs understand (the same names as tkinter.filedialog).
_FILE_DIALOG_OPTIONS = (
    "parent",
    "title",
    "initialdir",
    "initialfile",
    "filetypes",
    "defaultextension",
    "multiple",
    "mustexist",
    "confirmoverwrite",
    "typevariable",
)


class _Dialog:
    """Base of Open, SaveAs, and Directory (like tkinter's commondialog.Dialog)."""

    mode = "open"

    def __init__(self, master=None, **options):
        """Remember the parent (master) and the default options for show()."""
        self.master = master
        self.options = options

    def show(self, **options):
        """Show the dialog and return the result; options override the ones given
        to the constructor.
        """
        merged = {**self.options, **options}
        merged.setdefault("parent", self.master)
        # message= is a tkinter option for askdirectory; the dialog has no use for it.
        merged.pop("message", None)
        unknown = set(merged) - set(_FILE_DIALOG_OPTIONS)
        if unknown:
            raise TypeError(f"unexpected option {sorted(unknown)[0]!r}")
        if "multiple" in merged:
            merged["multiple"] = bool(merged["multiple"])
        return _FileDialog(self.mode, **merged).show()


class Open(_Dialog):
    """The Open dialog: show() returns a path ('' if cancelled), or a tuple of
    paths with multiple=True.
    """

    mode = "open"


class SaveAs(_Dialog):
    """The Save As dialog: show() returns a path ('' if cancelled)."""

    mode = "save"


class Directory(_Dialog):
    """The choose-a-folder dialog: show() returns a folder path ('' if cancelled)."""

    mode = "directory"


def askopenfilename(**options):
    """Ask for an existing file to open; returns its path, or '' if cancelled."""
    return Open(**options).show()


def asksaveasfilename(**options):
    """Ask where to save a file; returns the path, or '' if cancelled."""
    return SaveAs(**options).show()


def askopenfilenames(**options):
    """Ask for several existing files; returns a tuple of paths (empty if cancelled)."""
    options["multiple"] = True
    return Open(**options).show()


def askdirectory(**options):
    """Ask for a folder; returns its path, or '' if cancelled."""
    return Directory(**options).show()


def askopenfile(mode="r", **options):
    """Ask for a file and return it opened in `mode`, or None if cancelled."""
    filename = Open(**options).show()
    return open(filename, mode) if filename else None


def askopenfiles(mode="r", **options):
    """Ask for several files and return them opened in `mode` (a list), or None."""
    filenames = askopenfilenames(**options)
    return [open(filename, mode) for filename in filenames] if filenames else None


def asksaveasfile(mode="w", **options):
    """Ask where to save and return the file opened in `mode`, or None if cancelled."""
    filename = SaveAs(**options).show()
    return open(filename, mode) if filename else None
