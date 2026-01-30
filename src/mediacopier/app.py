"""Application entrypoint for MediaCopier."""

from __future__ import annotations

import os
import sys
import os
from typing import Any


def run_demo() -> dict[str, Any]:
    """Run the application in demo mode."""
    from mediacopier.core.demo import run_demo_pipeline
    return run_demo_pipeline()


def main() -> None:
    """Main application entrypoint."""
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
    from mediacopier.config.settings import get_settings
    from mediacopier.ui.window import run_window

    # Show current configuration
    try:
        settings = get_settings()
        print("=" * 50)
        print("🔧 Configuración TechAura:")
        print(f"   API URL: {settings.techaura.api_url or 'No configurada'}")
        print(
            f"   API Key: {'✓ Configurada' if settings.techaura.api_key else '✗ No configurada'}"
        )
        print("   Content Sources:")

        content_sources = {
            "music": settings.content.music_path,
            "videos": settings.content.videos_path,
            "movies": settings.content.movies_path,
        }

        for tipo, path in content_sources.items():
            exists = "✓" if path and os.path.isdir(path) else "✗"
            print(f"      {tipo}: {path or 'No configurada'} [{exists}]")
        print("=" * 50)
    except Exception as e:
        print(f"⚠️ Error al mostrar configuración: {e}")
        print("=" * 50)

    run_window()


if __name__ == "__main__":
    main()