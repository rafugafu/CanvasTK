"""Shared fixtures for the canvastk tests.

Most tests create real widgets, so they need a Tk display. Run the whole suite
invisibly with a virtual display:

    xvfb-run -a ~/pyvenv/bin/python -m pytest

Tests that need a display are skipped when there is none, so the pure-logic tests
(colors, file dialog helpers, theme dictionaries) also run on their own.
"""

import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import canvastk as ctk  # noqa: E402


def _display_works():
    """Whether a Tk window can be created at all."""
    try:
        probe = tk.Tk()
    except tk.TclError:
        return False
    probe.destroy()
    return True


_HAS_DISPLAY = _display_works()


def pytest_collection_modifyitems(config, items):
    """Skip the tests that use the `root` fixture when there is no display."""
    if _HAS_DISPLAY:
        return
    skip = pytest.mark.skip(reason="needs a Tk display (use xvfb-run)")
    for item in items:
        if "root" in item.fixturenames:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def clean_application_theme():
    """Every test starts and ends with the default application theme and mode."""
    ctk.reset_theme()
    ctk.set_appearance_mode("light")
    yield
    ctk.reset_theme()
    ctk.set_appearance_mode("light")


@pytest.fixture
def root():
    """A shown window (the tests that measure sizes need a mapped window)."""
    window = ctk.Window()
    window.geometry("700x500+0+0")
    window.update()
    yield window
    for child in list(window.winfo_children()):
        try:
            child.destroy()
        except tk.TclError:
            pass
    window.destroy()


def settle(widget, rounds=3):
    """Run the pending idle callbacks (redraws, measurements) a few times."""
    for _ in range(rounds):
        widget.update_idletasks()
        widget.update()
