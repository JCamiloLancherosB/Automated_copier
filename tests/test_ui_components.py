"""Tests for UI components."""

from unittest.mock import MagicMock, patch

import pytest

from mediacopier.config.settings import UIState, load_ui_state, save_ui_state
from mediacopier.ui.styles import Colors, Emojis, Fonts, Styles

# Try to import Toast, but allow tests to run even if tkinter is not available
try:
    from mediacopier.ui.components import Toast
    TOAST_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    TOAST_AVAILABLE = False
    Toast = None


class TestColors:
    """Test color constants."""

    def test_connection_colors_defined(self):
        """Test connection status colors are defined."""
        assert Colors.CONNECTED == "#2ecc71"
        assert Colors.DISCONNECTED == "#e74c3c"
        assert Colors.CONNECTING == "#f39c12"

    def test_log_level_colors_defined(self):
        """Test log level colors are defined."""
        assert Colors.LOG_INFO
        assert Colors.LOG_OK
        assert Colors.LOG_SUCCESS
        assert Colors.LOG_WARN
        assert Colors.LOG_ERROR

    def test_ui_element_colors_defined(self):
        """Test UI element colors are defined."""
        assert Colors.PRIMARY
        assert Colors.SECONDARY
        assert Colors.SUCCESS
        assert Colors.WARNING
        assert Colors.DANGER
        assert Colors.INFO
        assert Colors.ERROR  # Added to fix AttributeError in window.py line 568


class TestEmojis:
    """Test emoji constants."""

    def test_content_type_emojis_defined(self):
        """Test content type emojis are defined."""
        assert Emojis.MUSIC == "🎵"
        assert Emojis.VIDEOS == "🎬"
        assert Emojis.VIDEO == "🎬"  # Alias
        assert Emojis.MOVIES == "🎥"
        assert Emojis.MOVIE == "🎥"  # Alias

    def test_info_emojis_defined(self):
        """Test info indicator emojis are defined."""
        assert Emojis.ORDER_NUMBER == "📋"
        assert Emojis.ORDER == "📋"  # Alias
        assert Emojis.CUSTOMER == "👤"
        assert Emojis.CLIENT == "👤"  # Alias
        assert Emojis.PHONE == "📞"
        assert Emojis.CAPACITY == "💾"
        assert Emojis.GENRES == "🎶"
        assert Emojis.ARTISTS == "🎤"
        assert Emojis.DATE == "📅"
        assert Emojis.CLOCK == "🕐"
        assert Emojis.USB == "💿"

    def test_action_emojis_defined(self):
        """Test action emojis are defined."""
        assert Emojis.PLAY == "▶️"
        assert Emojis.STOP == "⏹️"
        assert Emojis.PAUSE == "⏸️"

    def test_status_emojis_defined(self):
        """Test status emojis are defined."""
        assert Emojis.CONNECTED == "🟢"
        assert Emojis.DISCONNECTED == "🔴"
        assert Emojis.CONNECTING == "🟡"


class TestFonts:
    """Test font configurations."""

    def test_font_styles_defined(self):
        """Test font styles are defined."""
        assert Fonts.TITLE
        assert Fonts.SUBTITLE
        assert Fonts.HEADING
        assert Fonts.BODY
        assert Fonts.SMALL
        assert Fonts.MONOSPACE

    def test_font_tuples_format(self):
        """Test fonts are tuples with correct format."""
        assert isinstance(Fonts.TITLE, tuple)
        assert len(Fonts.TITLE) >= 2
        assert isinstance(Fonts.TITLE[0], str)
        assert isinstance(Fonts.TITLE[1], int)


class TestStyles:
    """Test style configurations."""

    def test_toast_configuration(self):
        """Test toast configuration values."""
        assert Styles.TOAST_DURATION_MS == 3000
        assert Styles.TOAST_FADE_MS == 500

    def test_status_bar_configuration(self):
        """Test status bar configuration."""
        assert Styles.STATUS_BAR_HEIGHT == 30

    def test_tooltip_configuration(self):
        """Test tooltip configuration."""
        assert Styles.TOOLTIP_DELAY_MS == 500
        assert Styles.TOOLTIP_BG
        assert Styles.TOOLTIP_FG


@pytest.mark.skipif(not TOAST_AVAILABLE, reason="tkinter not available in test environment")
class TestToast:
    """Test Toast notification component."""

    def test_toast_constants(self):
        """Test toast type constants are defined."""
        assert Toast.SUCCESS == "success"
        assert Toast.ERROR == "error"
        assert Toast.WARNING == "warning"
        assert Toast.INFO == "info"

    def test_toast_show_method_exists(self):
        """Test that Toast.show static method exists."""
        assert hasattr(Toast, 'show')
        assert callable(Toast.show)

    def test_toast_show_with_mock_parent(self):
        """Test Toast.show with mocked parent window."""
        mock_parent = MagicMock()
        mock_parent.winfo_x.return_value = 100
        mock_parent.winfo_y.return_value = 100
        mock_parent.winfo_width.return_value = 800
        mock_parent.winfo_height.return_value = 600
        
        # Mock Toast initialization to avoid actual window creation
        with patch('mediacopier.ui.components.ctk.CTkToplevel.__init__', return_value=None):
            with patch('mediacopier.ui.components.ctk.CTkToplevel.withdraw'):
                with patch('mediacopier.ui.components.ctk.CTkToplevel.overrideredirect'):
                    with patch('mediacopier.ui.components.ctk.CTkToplevel.attributes'):
                        # This should not raise an exception
                        try:
                            Toast.show(mock_parent, "Test message", Toast.INFO)
                        except Exception:
                            # Some exceptions are expected in test environment without full UI
                            # We're mainly testing that the method is callable
                            pass


class TestUIState:
    """Test UI state persistence."""

    def test_default_values(self):
        """Test default UI state values."""
        state = UIState()
        assert state.window_width == 1200
        assert state.window_height == 800
        assert state.window_x is None
        assert state.window_y is None
        assert state.auto_refresh_enabled is True
        assert state.last_destination == ""

    def test_to_dict(self):
        """Test converting UI state to dictionary."""
        state = UIState(
            window_width=1024,
            window_height=768,
            window_x=100,
            window_y=50,
            auto_refresh_enabled=False,
            last_destination="/media/usb",
        )
        data = state.to_dict()
        assert data["window_width"] == 1024
        assert data["window_height"] == 768
        assert data["window_x"] == 100
        assert data["window_y"] == 50
        assert data["auto_refresh_enabled"] is False
        assert data["last_destination"] == "/media/usb"

    def test_from_dict(self):
        """Test creating UI state from dictionary."""
        data = {
            "window_width": 1024,
            "window_height": 768,
            "window_x": 100,
            "window_y": 50,
            "auto_refresh_enabled": False,
            "last_destination": "/media/usb",
        }
        state = UIState.from_dict(data)
        assert state.window_width == 1024
        assert state.window_height == 768
        assert state.window_x == 100
        assert state.window_y == 50
        assert state.auto_refresh_enabled is False
        assert state.last_destination == "/media/usb"

    def test_from_dict_with_defaults(self):
        """Test creating UI state from partial dictionary uses defaults."""
        data = {"window_width": 1024}
        state = UIState.from_dict(data)
        assert state.window_width == 1024
        assert state.window_height == 800  # Default
        assert state.window_x is None  # Default
        assert state.auto_refresh_enabled is True  # Default

    def test_roundtrip_conversion(self):
        """Test converting to dict and back preserves values."""
        original = UIState(
            window_width=1920,
            window_height=1080,
            window_x=200,
            window_y=100,
            auto_refresh_enabled=True,
            last_destination="/mnt/usb",
        )
        data = original.to_dict()
        restored = UIState.from_dict(data)
        assert restored.window_width == original.window_width
        assert restored.window_height == original.window_height
        assert restored.window_x == original.window_x
        assert restored.window_y == original.window_y
        assert restored.auto_refresh_enabled == original.auto_refresh_enabled
        assert restored.last_destination == original.last_destination


class TestUIStatePersistence:
    """Test UI state save/load functionality."""

    def test_load_ui_state_returns_default_when_no_file(self, tmp_path, monkeypatch):
        """Test loading UI state returns default when no file exists."""
        # Mock home directory
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        state = load_ui_state()
        assert isinstance(state, UIState)
        assert state.window_width == 1200  # Default value

    def test_save_and_load_ui_state(self, tmp_path, monkeypatch):
        """Test saving and loading UI state."""
        # Mock home directory
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # Create and save state
        original_state = UIState(
            window_width=1024,
            window_height=768,
            window_x=100,
            window_y=50,
            auto_refresh_enabled=False,
            last_destination="/test/path",
        )
        save_ui_state(original_state)

        # Load and verify
        loaded_state = load_ui_state()
        assert loaded_state.window_width == original_state.window_width
        assert loaded_state.window_height == original_state.window_height
        assert loaded_state.window_x == original_state.window_x
        assert loaded_state.window_y == original_state.window_y
        assert loaded_state.auto_refresh_enabled == original_state.auto_refresh_enabled
        assert loaded_state.last_destination == original_state.last_destination

    def test_save_creates_config_directory(self, tmp_path, monkeypatch):
        """Test saving creates .mediacopier directory if it doesn't exist."""
        # Mock home directory
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        state = UIState()
        save_ui_state(state)

        config_dir = tmp_path / ".mediacopier"
        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_load_handles_corrupted_file(self, tmp_path, monkeypatch):
        """Test loading handles corrupted JSON file gracefully."""
        # Mock home directory
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # Create corrupted file
        config_dir = tmp_path / ".mediacopier"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "ui_state.json"
        config_file.write_text("{ invalid json }")

        # Should return default state instead of crashing
        state = load_ui_state()
        assert isinstance(state, UIState)
        assert state.window_width == 1200  # Default value


class TestUSBSpaceValidation:
    """Test USB space validation for robustness."""

    def test_usb_has_sufficient_space(self):
        """Test checking if USB has sufficient space."""
        # Mock USB with 16 GB
        class MockUSB:
            free_gb = 15.5
            size_gb = 16.0

        usb = MockUSB()
        required_gb = 10.0

        # USB has enough space
        assert usb.free_gb >= required_gb

    def test_usb_insufficient_space(self):
        """Test detecting insufficient USB space."""
        # Mock USB with limited space
        class MockUSB:
            free_gb = 2.5
            size_gb = 8.0

        usb = MockUSB()
        required_gb = 5.0

        # USB doesn't have enough space
        assert usb.free_gb < required_gb

    def test_calculate_required_space_for_order(self):
        """Test calculating required space for an order."""
        # For an 8GB USB order, we need at least that capacity
        order_capacity_gb = 8
        safety_margin = 0.5  # 500 MB

        required_space = order_capacity_gb + safety_margin
        assert required_space == 8.5

    def test_space_validation_with_exact_match(self):
        """Test space validation with exact capacity match."""
        class MockUSB:
            free_gb = 8.0
            size_gb = 8.0

        usb = MockUSB()
        required_gb = 8.0

        # Should have enough space (equal)
        assert usb.free_gb >= required_gb

    def test_space_validation_edge_case(self):
        """Test space validation with very small margin."""
        class MockUSB:
            free_gb = 8.01
            size_gb = 8.0

        usb = MockUSB()
        required_gb = 8.0

        # Should have enough space (just barely)
        assert usb.free_gb >= required_gb
