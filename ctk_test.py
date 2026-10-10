"""Demo of the canvastk package: every widget in one window."""

import tkinter as tk
import tkinter.font as tkfont

from canvastk import *


def build_demo():
    """Build the demo window with one tab per group of widgets and return it.

    The top row has controls that change the appearance mode, the accent color, and the
    tab corner radius while the demo is running.
    """
    root = Window()
    root.title("Canvas widgets")
    root.geometry("780x740")

    # Menus: a menu bar whose cascades are File and View (the File menu has a submenu, a
    # check entry, and a disabled entry).
    menu_bar_menu = Menu(root)
    file_menu = Menu(root)
    file_menu.add_command(label="New", accelerator="Ctrl+N")
    file_menu.add_command(label="Open…", accelerator="Ctrl+O")
    file_menu.add_separator()
    recent_menu = Menu(root)
    recent_menu.add_command(label="notes.txt")
    recent_menu.add_command(label="todo.md")
    file_menu.add_cascade(label="Recent", menu=recent_menu)
    word_wrap = tk.BooleanVar(root, value=True)
    file_menu.add_checkbutton(label="Word wrap", variable=word_wrap)
    file_menu.add_command(label="Disabled", state="disabled")
    menu_bar_menu.add_cascade(label="File", menu=file_menu)
    view_menu = Menu(root)
    view_mode = tk.StringVar(root, value="a")
    view_menu.add_radiobutton(label="Mode A", variable=view_mode, value="a")
    view_menu.add_radiobutton(label="Mode B", variable=view_mode, value="b")
    menu_bar_menu.add_cascade(label="View", menu=view_menu)
    MenuBar(root, menu_bar_menu).pack(fill="x")

    # Controls that change the look while the demo runs: appearance mode, accent color,
    # and tab corners.
    appearance_row = Frame(root)
    appearance_row.pack(fill="x", padx=10, pady=(8, 0))
    Label(appearance_row, "Appearance").pack(side="left", padx=(0, 8))
    OptionMenu(
        appearance_row,
        None,
        "Light",
        "Light",
        "Dark",
        command=lambda mode: set_appearance_mode(mode),
    ).pack(side="left")
    Label(appearance_row, "Accent color").pack(side="left", padx=(16, 8))
    OptionMenu(
        appearance_row,
        None,
        "blue",
        *CANVAS_COLOR_THEMES,
        command=lambda name: set_theme(CANVAS_COLOR_THEMES[name]),
    ).pack(side="left")
    Label(appearance_row, "Tab corners").pack(side="left", padx=(16, 8))
    # Each choice sets segment_radius (the segmented tabs; None = fully rounded
    # pills) and radius (the classic tabs and the page corners).
    tab_corner_radii = {
        "Pill": (None, 16),
        "Round (10)": (10, 10),
        "Soft (6)": (6, 6),
        "Square (0)": (0, 0),
    }
    OptionMenu(
        appearance_row,
        None,
        "Round (10)",
        *tab_corner_radii,
        command=lambda name: notebook.configure(
            segment_radius=tab_corner_radii[name][0], radius=tab_corner_radii[name][1]
        ),
    ).pack(side="left")

    # The notebook holding every demo tab; its tabs can be reordered by dragging.
    notebook = Notebook(root, draggable=True, radius=10)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # Entries, drop-downs, combo boxes, and spin boxes, laid out as label/widget rows.
    # --- Inputs tab
    inputs = Frame(notebook)
    notebook.add(inputs, text="Inputs")
    row = 0

    def add_row(label, widget):
        """Add a 'label + widget' row to the Inputs tab's grid."""
        nonlocal row
        Label(inputs, label).grid(row=row, column=0, sticky="w", padx=8, pady=6)
        widget.grid(row=row, column=1, sticky="w", padx=8, pady=6)
        row += 1

    entry = Entry(inputs, placeholder="Type something here...")
    entry.insert(0, "Hello")
    add_row("Entry", entry)
    add_row("Password", Entry(inputs, show="•", placeholder="Password"))
    add_row(
        "Custom placeholder colors",
        Entry(
            inputs,
            placeholder="Search...",
            placeholder_color="#C2255C",
            placeholder_fill_color="#FFF0F6",
        ),
    )
    combo = Combobox(
        inputs,
        values=["Python", "LaTeX", "Plain text", "Markdown"],
        state="readonly",
        placeholder="Choose a language...",
    )
    add_row("Combobox", combo)
    editable_combo = Combobox(
        inputs, values=["one", "two", "three"], placeholder="Type or pick..."
    )
    add_row("Combobox (editable)", editable_combo)
    add_row(
        "Dropdown",
        OptionMenu(inputs, None, "Light", "Light", "Dark", "Solarized"),
    )
    # Dropdown lists scroll once they would be taller than popup_max_height.
    add_row(
        "Combobox (80 values, max height 180)",
        Combobox(
            inputs,
            values=[f"Value {n}" for n in range(1, 81)],
            state="readonly",
            popup_max_height=180,
        ),
    )
    add_row(
        "Dropdown (40 values, max height 150)",
        OptionMenu(
            inputs,
            None,
            "Item 1",
            *[f"Item {n}" for n in range(1, 41)],
            popup_max_height=150,
        ),
    )
    add_row(
        "Dropdown with a placeholder",
        OptionMenu(
            inputs, None, None, "Small", "Medium", "Large", placeholder="Pick a size..."
        ),
    )
    add_row("Spinbox", Spinbox(inputs, from_=0, to=20, increment=1))
    add_row("Decimal spinbox", Spinbox(inputs, from_=0, to=1, increment=0.1))
    add_row("Disabled entry", Entry(inputs, state="disabled"))

    # Check boxes, radio buttons, a slider driving a progress bar, and an indeterminate
    # progress bar.
    # --- Toggles tab
    toggles = Frame(notebook)
    notebook.add(toggles, text="Toggles & sliders")
    check_var = tk.IntVar(toggles, value=1)
    Checkbutton(toggles, "Enable feature", variable=check_var).pack(
        anchor="w", padx=10, pady=4
    )
    Checkbutton(toggles, "Another option").pack(anchor="w", padx=10, pady=4)
    Checkbutton(toggles, "Disabled", state="disabled").pack(anchor="w", padx=10, pady=4)
    choice = tk.StringVar(toggles, value="Red")
    for name in ("Red", "Green", "Blue"):
        Radiobutton(toggles, name, variable=choice).pack(anchor="w", padx=10, pady=2)
    Separator(toggles).pack(fill="x", padx=10, pady=8)
    progress = Progressbar(toggles, length=300)
    scale = Scale(
        toggles,
        from_=0,
        to=100,
        length=300,
        command=lambda v: progress.configure(value=v),
    )
    scale.pack(anchor="w", padx=10, pady=4)
    scale.set(35)
    progress.pack(anchor="w", padx=10, pady=4)
    busy = Progressbar(toggles, length=300, mode="indeterminate")
    busy.pack(anchor="w", padx=10, pady=4)
    busy.start()

    # Toggle switches, meters in three shapes (one that can be dragged), and foldable
    # sections that fold away without disturbing the widgets around them.
    # --- Meters & folds tab
    gauges = Frame(notebook)
    notebook.add(gauges, text="Meters & folds")
    switch_row = Frame(gauges)
    switch_row.pack(fill="x", padx=10, pady=(10, 4))
    Toggle(switch_row, "Notifications").pack(side="left", padx=(0, 16))
    Toggle(switch_row, "Already on", variable=tk.IntVar(gauges, value=1)).pack(
        side="left", padx=(0, 16)
    )
    Toggle(switch_row, "Disabled", state="disabled").pack(side="left")
    meter_row = Frame(gauges)
    meter_row.pack(fill="x", padx=10, pady=4)
    meter_value = tk.DoubleVar(gauges, value=65)
    Meter(
        meter_row,
        variable=meter_value,
        suffix="%",
        subtext="drag me",
        interactive=True,
        size=170,
    ).pack(side="left", padx=(0, 16))
    Meter(
        meter_row, variable=meter_value, shape="circle", subtext="circle", size=150
    ).pack(side="left", padx=(0, 16))
    Meter(
        meter_row, variable=meter_value, shape="semi", subtext="semi", size=170
    ).pack(side="left", anchor="s")
    Scale(gauges, from_=0, to=100, length=300, variable=meter_value).pack(
        anchor="w", padx=10, pady=4
    )
    details = Foldable(gauges, "Details")
    Label(details, "Everything in here is an ordinary child of the foldable.").pack(
        anchor="w"
    )
    Checkbutton(details, "A check box inside").pack(anchor="w")
    more = Foldable(details, "Even more (nested)", expanded=False)
    Label(more, "A foldable inside a foldable.").pack(anchor="w")
    more.pack(fill="x", pady=(6, 0))
    details.pack(fill="x", padx=10, pady=(10, 4))
    surprise = Foldable(gauges, "Folded at the start", expanded=False)
    Label(surprise, "Surprise!").pack(anchor="w")
    surprise.pack(fill="x", padx=10, pady=4)
    Label(gauges, "This label shares the parent and stays where it is.").pack(
        anchor="w", padx=10, pady=4
    )

    # A scrolled text box and a scrolled list box in a horizontal panedwindow.
    # --- Text tab
    text_tab = Frame(notebook)
    notebook.add(text_tab, text="Text & lists")
    pane = Panedwindow(text_tab, orient="horizontal")
    pane.pack(fill="both", expand=True)
    textbox = Textbox(
        pane,
        scrolled=True,
        wrap="word",
        width=30,
        height=10,
        placeholder="Start typing here...",
    )
    textbox.insert("1.0", "A scrolled textbox.\n" * 40)
    pane.add(textbox, weight=1)
    listbox = Listbox(
        pane,
        [f"Item {n}" for n in range(1, 60)],
        width=18,
        selectmode="extended",
        scrolled=True,
    )
    pane.add(listbox, weight=1)

    # Buttons in custom colors, a tooltip, fonts as Font objects and tuples, and a
    # bigger check box.
    # --- Buttons tab
    buttons = Frame(notebook)
    notebook.add(buttons, text="Buttons")
    Button(
        buttons, "cancel", default_bg="#E9E2E2", hover_bg="#F8F4F4", press_bg="#E9E2E2"
    ).grid(row=0, column=0, padx=10, pady=10)
    Button(buttons, "ok").grid(row=0, column=1, padx=10, pady=10)
    Button(
        buttons,
        "never",
        default_bg="#FF0000",
        hover_bg="#F04141",
        press_bg="#FF0000",
        default_fg="white",
        hover_fg="white",
        press_fg="white",
    ).grid(row=0, column=2, padx=10, pady=10)
    disabled_button = Button(buttons, "disabled", state="disabled")
    disabled_button.grid(row=0, column=3, padx=10, pady=10)
    tip_target = Button(buttons, "hover me")
    tip_target.grid(row=1, column=0, padx=10, pady=10)
    Tooltip(tip_target, "A canvas-drawn tooltip")

    # Fonts: a tkinter Font object, a font tuple, or the default.
    serif_font = tkfont.Font(family="Times", size=16, slant="italic", weight="bold")
    Button(buttons, "Font object", font=serif_font).grid(
        row=1, column=1, padx=10, pady=10
    )
    Button(buttons, "Font tuple", font=("Courier", 11, "bold"), radius=4).grid(
        row=1, column=2, padx=10, pady=10
    )
    Checkbutton(
        buttons, "Big checkbox", font=("TkDefaultFont", 15), indicator_size=26
    ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=10)
    Label(buttons, "A label in a custom font", font=serif_font).grid(
        row=2, column=2, columnspan=2, sticky="w", padx=10, pady=10
    )

    # --- Toplevels tab: subwindows with their own themes
    windows_tab = Frame(notebook)
    notebook.add(windows_tab, text="Toplevels")

    def open_toplevel(title, **options):
        """Open a demo Toplevel (extra options such as theme= go to Toplevel) with some widgets and a 'Make darker' button."""
        top = Toplevel(root, **options)
        top.title(title)
        top.geometry("340x260")
        Label(top, title, font=("TkDefaultFont", 13, "bold")).pack(
            anchor="w", padx=14, pady=(14, 6)
        )
        Entry(top).pack(fill="x", padx=14, pady=4)
        Combobox(top, values=["One", "Two", "Three"], state="readonly").pack(
            fill="x", padx=14, pady=4
        )
        Checkbutton(top, "A checkbox").pack(anchor="w", padx=14, pady=4)
        Scale(top, from_=0, to=100, length=200).pack(anchor="w", padx=14, pady=4)
        row = Frame(top)
        row.pack(fill="x", padx=14, pady=10)
        Button(row, "Close", command=top.destroy).pack(side="right")
        Button(
            row,
            "Make darker",
            command=lambda: top.set_theme({"window": "#101010", "surface": "#1c1c1c"}),
        ).pack(side="right", padx=8)
        return top

    Label(windows_tab, "Subwindows follow the appearance mode:").pack(
        anchor="w", padx=14, pady=(14, 4)
    )
    Button(
        windows_tab, "Open a Toplevel", command=lambda: open_toplevel("A Toplevel")
    ).pack(anchor="w", padx=14, pady=4)
    Label(windows_tab, "Each window can have its own theme dictionary:").pack(
        anchor="w", padx=14, pady=(14, 4)
    )
    Button(
        windows_tab,
        "Dark Toplevel (CANVAS_DARK_PALETTE)",
        command=lambda: open_toplevel("Dark Toplevel", theme=CANVAS_DARK_PALETTE),
    ).pack(anchor="w", padx=14, pady=4)
    Button(
        windows_tab,
        "Orange Toplevel (custom accent and background)",
        command=lambda: open_toplevel(
            "Orange Toplevel",
            theme={"window": "#fff4e6", "surface": "#fffaf3", "accent": "#e8590c"},
        ),
    ).pack(anchor="w", padx=14, pady=4)
    Label(windows_tab, "And the main window's theme can change while running:").pack(
        anchor="w", padx=14, pady=(14, 4)
    )
    window_row = Frame(windows_tab)
    window_row.pack(anchor="w", padx=14, pady=4)
    Button(
        window_row,
        "Make this window dark",
        command=lambda: root.set_theme(CANVAS_DARK_PALETTE),
    ).pack(side="left", padx=(0, 8))
    Button(
        window_row,
        "Purple accent for this window",
        command=lambda: root.set_theme({"accent": "#7048e8"}),
    ).pack(side="left", padx=(0, 8))
    Button(window_row, "Reset this window", command=root.reset_theme).pack(side="left")

    # Panedwindows nested to split in both directions.
    # --- Panes tab: nested horizontal + vertical Panedwindows
    panes_tab = Frame(notebook)
    notebook.add(panes_tab, text="Panes")
    outer_pane = Panedwindow(panes_tab, orient="horizontal")
    outer_pane.pack(fill="both", expand=True)
    left_list = Listbox(
        outer_pane, [f"Left item {n}" for n in range(1, 40)], width=14, scrolled=True
    )
    outer_pane.add(left_list, weight=0)
    right_pane = Panedwindow(outer_pane, orient="vertical")
    outer_pane.add(right_pane, weight=1)
    top_text = Textbox(right_pane, wrap="word", width=30, height=6)
    top_text.insert("1.0", "Drag the grips between the panes.\nThis is the top pane.")
    right_pane.add(top_text, weight=1)
    bottom = Frame(right_pane)
    Label(bottom, "Bottom pane").pack(anchor="w", padx=10, pady=10)
    Button(bottom, "A button in a pane").pack(anchor="w", padx=10)
    right_pane.add(bottom, weight=1)

    # A GridPanedwindow: the same layouts in a single widget, with buttons that split or
    # remove the last pane.
    # --- Grid panes: one widget split in both directions, as often as you like
    grid_tab = Frame(notebook)
    notebook.add(grid_tab, text="Grid panes")
    grid_toolbar = Frame(grid_tab)
    grid_toolbar.pack(fill="x", padx=6, pady=6)
    grid = GridPanedwindow(grid_tab)
    grid.pack(fill="both", expand=True)
    pane_numbers = iter(range(1, 1000))

    def make_grid_pane():
        """Make a small labeled frame to use as a pane of the grid panedwindow."""
        pane = Frame(grid)
        Label(
            pane, f"Pane {next(pane_numbers)}", font=("TkDefaultFont", 12, "bold")
        ).pack(anchor="w", padx=10, pady=10)
        return pane

    def split_last_pane(orient):
        """Split the last pane of the grid panedwindow in the given direction, adding a new pane."""
        grid.split(grid.panes()[-1], make_grid_pane(), orient)

    def remove_last_pane():
        """Remove (and destroy) the last pane of the grid panedwindow, keeping at least one."""
        if len(grid.panes()) > 1:
            last = grid.panes()[-1]
            grid.remove(last)
            last.destroy()

    Button(
        grid_toolbar,
        "Split last pane horizontally",
        command=lambda: split_last_pane("horizontal"),
    ).pack(side="left", padx=(0, 6))
    Button(
        grid_toolbar,
        "Split last pane vertically",
        command=lambda: split_last_pane("vertical"),
    ).pack(side="left", padx=(0, 6))
    Button(grid_toolbar, "Remove last pane", command=remove_last_pane).pack(side="left")

    grid_list = Listbox(
        grid, [f"Left item {n}" for n in range(1, 40)], width=14, scrolled=True
    )
    grid.add(grid_list)
    grid_text = Textbox(grid, wrap="word", width=30, height=6)
    grid_text.insert("1.0", "A pane that was split horizontally from the list.")
    grid.split(grid_list, grid_text, "horizontal")
    grid_bottom = make_grid_pane()
    grid.split(grid_text, grid_bottom, "vertical")
    # The bottom pane can be split horizontally too, in the same widget.
    grid.split(grid_bottom, make_grid_pane(), "horizontal")

    # The canvastk file dialogs and message boxes: the same functions and options as
    # tkinter.filedialog and tkinter.messagebox.
    # --- Dialogs tab
    dialogs_tab = Frame(notebook)
    notebook.add(dialogs_tab, text="Dialogs")
    dialog_result = tk.StringVar(dialogs_tab, value="Pick a dialog to open.")
    Label(
        dialogs_tab,
        "Same API as tkinter.filedialog, tkinter.messagebox, and tkinter.colorchooser:",
    ).pack(anchor="w", padx=14, pady=(14, 6))
    text_types = [("Text files", "*.txt"), ("Python files", "*.py *.pyw"), ("All files", "*")]
    for caption, ask in (
        ("askopenfilename", lambda: filedialog.askopenfilename(parent=root, filetypes=text_types)),
        ("askopenfilenames", lambda: filedialog.askopenfilenames(parent=root)),
        (
            "asksaveasfilename",
            lambda: filedialog.asksaveasfilename(
                parent=root, defaultextension=".txt", filetypes=text_types
            ),
        ),
        ("askdirectory", lambda: filedialog.askdirectory(parent=root)),
        ("askcolor", lambda: colorchooser.askcolor("#3b82f6", parent=root)),
        ("showinfo", lambda: messagebox.showinfo("Saved", "The file was saved.", parent=root)),
        (
            "showwarning",
            lambda: messagebox.showwarning(
                "Careful", "This cannot be undone.", detail="Make a copy first.", parent=root
            ),
        ),
        ("showerror", lambda: messagebox.showerror("Error", "Could not open the file.", parent=root)),
        ("askyesno", lambda: messagebox.askyesno("Quit", "Quit without saving?", parent=root)),
        (
            "askyesnocancel",
            lambda: messagebox.askyesnocancel("Save", "Save the changes?", parent=root),
        ),
        (
            "askretrycancel",
            lambda: messagebox.askretrycancel("Network", "The server is not answering.", parent=root),
        ),
    ):
        Button(
            dialogs_tab, caption, command=lambda ask=ask: dialog_result.set(repr(ask()))
        ).pack(anchor="w", padx=14, pady=4)
    Label(dialogs_tab, "The last result (an empty value means cancelled):").pack(
        anchor="w", padx=14, pady=(14, 4)
    )
    Label(dialogs_tab, textvariable=dialog_result, wraplength=600, justify="left").pack(
        anchor="w", padx=14
    )

    # ScrolledFrame in its three orientations.
    # --- Scrolled frames: vertical, horizontal, and both
    scrolled = ScrolledFrame(notebook)
    notebook.add(scrolled, text="Vertical scroll", closable=True)
    for n in range(40):
        Checkbutton(scrolled, f"Scrolled option {n}").pack(anchor="w", padx=10, pady=2)

    horizontal = ScrolledFrame(notebook, orient="horizontal")
    notebook.add(horizontal, text="Horizontal scroll", closable=True)
    for n in range(30):
        Button(horizontal, f"Button {n}").pack(side="left", padx=6, pady=10)

    both = ScrolledFrame(notebook, orient="both")
    notebook.add(both, text="Both", closable=True)
    for row_number in range(14):
        for column_number in range(10):
            Label(both, f"R{row_number}C{column_number}").grid(
                row=row_number, column=column_number, padx=14, pady=4
            )

    return root


if __name__ == "__main__":
    build_demo().mainloop()
