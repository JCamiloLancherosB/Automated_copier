"""UI styles and color constants for MediaCopier."""

# Color palette
class Colors:
    """Color constants for the UI."""
    
    # Connection status
    CONNECTED = "#2ecc71"  # Green
    DISCONNECTED = "#e74c3c"  # Red
    CONNECTING = "#f39c12"  # Orange
    
    # Log levels
    LOG_INFO = "#ecf0f1"  # Light gray
    LOG_OK = "#2ecc71"  # Green
    LOG_SUCCESS = "#27ae60"  # Dark green
    LOG_WARN = "#f39c12"  # Orange
    LOG_ERROR = "#e74c3c"  # Red
    
    # UI elements
    PRIMARY = "#3498db"  # Blue
    SECONDARY = "#95a5a6"  # Gray
    SUCCESS = "#2ecc71"  # Green
    WARNING = "#f39c12"  # Orange
    DANGER = "#e74c3c"  # Red
    INFO = "#3498db"  # Blue
    ERROR = "#e74c3c"  # Red (alias for consistency)
    
    # Text
    TEXT_PRIMARY = "#ecf0f1"  # Light gray
    TEXT_SECONDARY = "#95a5a6"  # Gray
    TEXT_DARK = "#2c3e50"  # Dark gray
    
    # Background
    BG_DARK = "#2c3e50"  # Dark gray
    BG_LIGHT = "#ecf0f1"  # Light gray
    BG_PANEL = "#34495e"  # Medium gray


class Fonts:
    """Font configurations."""
    
    TITLE = ("Arial", 18, "bold")
    SUBTITLE = ("Arial", 16, "bold")
    HEADING = ("Arial", 14, "bold")
    BODY = ("Arial", 12)
    SMALL = ("Arial", 10)
    MONOSPACE = ("Courier", 10)


class Emojis:
    """Emoji constants for visual indicators."""
    
    # Content types
    MUSIC = "🎵"
    VIDEOS = "🎬"
    MOVIES = "🎥"
    
    # Info indicators
    ORDER_NUMBER = "📋"
    CUSTOMER = "👤"
    CAPACITY = "💾"
    GENRES = "🎶"
    ARTISTS = "🎤"
    DATE = "📅"
    USB = "💿"
    
    # Status
    CONNECTED = "🟢"
    DISCONNECTED = "🔴"
    CONNECTING = "🟡"
    WARNING = "⚠️"
    ERROR = "❌"
    SUCCESS = "✅"
    INFO = "ℹ️"


class Styles:
    """Style configurations."""
    
    # Toast notification
    TOAST_DURATION_MS = 3000
    TOAST_FADE_MS = 500
    
    # Status bar
    STATUS_BAR_HEIGHT = 30
    
    # Tooltips
    TOOLTIP_DELAY_MS = 500
    TOOLTIP_BG = "#34495e"
    TOOLTIP_FG = "#ecf0f1"
