"""Test to verify SettingsDialog import fix."""

import ast
from pathlib import Path


def test_settings_dialog_import_in_window():
    """Verify that SettingsDialog is imported in window.py."""
    window_py = Path(__file__).parent.parent / "src" / "mediacopier" / "ui" / "window.py"

    with open(window_py, "r") as f:
        tree = ast.parse(f.read())

    # Find all imports
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "mediacopier.ui.settings_dialog":
                for alias in node.names:
                    imports.append(alias.name)

    # Verify SettingsDialog is imported
    assert "SettingsDialog" in imports, (
        "SettingsDialog should be imported from mediacopier.ui.settings_dialog"
    )


def test_settings_dialog_class_exists():
    """Verify that SettingsDialog class exists in settings_dialog.py."""
    settings_dialog_py = (
        Path(__file__).parent.parent / "src" / "mediacopier" / "ui" / "settings_dialog.py"
    )

    with open(settings_dialog_py, "r") as f:
        tree = ast.parse(f.read())

    # Find SettingsDialog class
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)

    assert "SettingsDialog" in classes, "SettingsDialog class should exist in settings_dialog.py"


def test_settings_dialog_has_required_methods():
    """Verify that SettingsDialog has the required methods."""
    settings_dialog_py = (
        Path(__file__).parent.parent / "src" / "mediacopier" / "ui" / "settings_dialog.py"
    )

    with open(settings_dialog_py, "r") as f:
        tree = ast.parse(f.read())

    # Find SettingsDialog class and its methods
    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SettingsDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)

    # Verify required methods exist
    assert "__init__" in methods, "SettingsDialog should have __init__ method"
    assert "get_result" in methods, "SettingsDialog should have get_result method"


def test_settings_dialog_usage_in_window():
    """Verify that SettingsDialog is used correctly in window.py."""
    window_py = Path(__file__).parent.parent / "src" / "mediacopier" / "ui" / "window.py"

    with open(window_py, "r") as f:
        content = f.read()
        tree = ast.parse(content)

    # Find usage of SettingsDialog
    found_usage = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "SettingsDialog":
                found_usage = True
                # Verify it's called with 2 arguments
                assert len(node.args) == 2, "SettingsDialog should be called with 2 arguments"

    assert found_usage, "SettingsDialog should be instantiated in window.py"
