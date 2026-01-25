"""Application entrypoint for MediaCopier."""

from __future__ import annotations

from mediacopier.ui.cli import run_cli


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
