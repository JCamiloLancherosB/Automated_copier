"""Application entrypoint for MediaCopier."""

from __future__ import annotations

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

    # Normal mode - run GUI with TechAura integration
    from mediacopier.ui.window import MediaCopierUI

    app = MediaCopierUI()
    
    # ========================================
    # 🔧 CONFIGURACIÓN DE TECHAURA INTEGRATION
    # ========================================
    # Las rutas se toman de variables de entorno o usan defaults vacíos
    content_sources = {
        "music": os.environ.get("CONTENT_PATH_MUSIC", ""),
        "videos": os.environ.get("CONTENT_PATH_VIDEOS", ""),
        "movies": os.environ.get("CONTENT_PATH_MOVIES", ""),
    }
    
    # Solo configurar si las variables de entorno están definidas
    api_url = os.environ.get("TECHAURA_API_URL")
    api_key = os.environ.get("TECHAURA_API_KEY")
    
    if api_url and api_key:
        print(f"🔗 Configurando integración TechAura: {api_url}")
        # Filtrar solo los paths que existen
        valid_sources = {k: v for k, v in content_sources.items() if v and os.path.isdir(v)}
        if valid_sources:
            app.setup_techaura_integration(content_sources=valid_sources)
            print(f"✅ Fuentes de contenido configuradas: {list(valid_sources.keys())}")
        else:
            print("⚠️ No se encontraron rutas de contenido válidas en las variables de entorno")
    else:
        print("⚠️ Integración TechAura no configurada (falta TECHAURA_API_URL o TECHAURA_API_KEY)")
        print("   Ejecutando en modo standalone...")
    
    app.mainloop()


if __name__ == "__main__":
    main()