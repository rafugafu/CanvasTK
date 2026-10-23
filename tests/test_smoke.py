"""The package imports and a window can be created."""

import canvastk as ctk


def test_public_names_exist():
    for name in ctk.__all__:
        assert hasattr(ctk, name), name


def test_window_and_label(root):
    label = ctk.Label(root, "hello")
    label.pack()
    root.update()
    assert label.text == "hello"
