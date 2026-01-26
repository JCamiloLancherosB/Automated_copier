"""Application entrypoint for MediaCopier."""

from __future__ import annotations

from mediacopier.ui.window import run_window


def main() -> None:
    run_window()


if __name__ == "__main__":
    main()
