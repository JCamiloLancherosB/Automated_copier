"""Application entrypoint for MediaCopier."""

from __future__ import annotations

import sys
from typing import Any


def run_demo() -> dict[str, Any]:
    """Run the application in demo mode.

    Demo mode creates temporary files and demonstrates the complete
    MediaCopier pipeline without requiring external resources.

    Returns:
        Dictionary with demo results including stats and report.
    """
    from mediacopier.core.demo import run_demo_pipeline

    return run_demo_pipeline()


def main() -> None:
    """Main application entrypoint.

    Supports command line arguments:
        --demo: Run in demo mode (prints results and exits)
        --demo-info: Print demo mode information and exit
    """
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        if arg == "--demo":
            print("Running MediaCopier in demo mode...")
            results = run_demo()
            print("\nDemo Results:")
            print(f"  Total requests: {results['total_requests']}")
            print(f"  Matches found: {results['matches_found']}")
            print(f"  Files to copy: {results['files_to_copy']}")
            print(f"  Total bytes: {results['total_bytes']}")
            print("\nDry-run report:")
            print(f"  Copied: {results['dry_run_copied']}")
            print(f"  Skipped: {results['dry_run_skipped']}")
            print(f"  Failed: {results['dry_run_failed']}")
            print("\nDemo completed successfully!")
            return

        if arg == "--demo-info":
            from mediacopier.core.demo import get_demo_info

            info = get_demo_info()
            print("MediaCopier Demo Mode Information:")
            print(f"  Available: {info['available']}")
            print(f"  Description: {info['description']}")
            print(f"  Songs available: {info['songs_available']}")
            print(f"  Movies available: {info['movies_available']}")
            print(f"\nSample song requests: {', '.join(info['song_requests'][:5])}...")
            print(f"Sample movie requests: {', '.join(info['movie_requests'][:3])}...")
            return

    # Normal mode - run GUI (import here to avoid tkinter requirement for CLI)
    from mediacopier.ui.window import run_window

    run_window()


if __name__ == "__main__":
    main()
