"""Reusable UI components for MediaCopier."""

from __future__ import annotations

from typing import Literal

import customtkinter as ctk

from mediacopier.ui.styles import Colors, Fonts, Styles


class Toast(ctk.CTkToplevel):
    """Toast notification component."""
    
    def __init__(
        self,
        parent: ctk.CTk,
        message: str,
        type: Literal["info", "success", "warning", "error"] = "info",
        duration: int = Styles.TOAST_DURATION_MS,
    ) -> None:
        super().__init__(parent)
        
        # Configure window
        self.withdraw()  # Hide initially
        self.overrideredirect(True)  # Remove window decorations
        self.attributes("-topmost", True)  # Always on top
        
        # Set color based on type
        color_map = {
            "info": Colors.INFO,
            "success": Colors.SUCCESS,
            "warning": Colors.WARNING,
            "error": Colors.DANGER,
        }
        bg_color = color_map.get(type, Colors.INFO)
        
        # Create frame
        frame = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Add message
        label = ctk.CTkLabel(
            frame,
            text=message,
            font=Fonts.BODY,
            text_color=Colors.TEXT_PRIMARY,
            wraplength=400,
        )
        label.pack(padx=16, pady=12)
        
        # Position and show
        self.update_idletasks()
        self._position_toast(parent)
        self.deiconify()
        
        # Schedule auto-close
        self.after(duration, self._fade_out)
    
    def _position_toast(self, parent: ctk.CTk) -> None:
        """Position toast at bottom-right of parent window."""
        parent.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        toast_width = self.winfo_width()
        toast_height = self.winfo_height()
        
        x = parent_x + parent_width - toast_width - 20
        y = parent_y + parent_height - toast_height - 60
        
        self.geometry(f"+{x}+{y}")
    
    def _fade_out(self) -> None:
        """Fade out and destroy toast."""
        self.destroy()


class StatusBar(ctk.CTkFrame):
    """Status bar component for bottom of window."""
    
    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent, height=Styles.STATUS_BAR_HEIGHT)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=1)
        
        # TechAura connection status
        self._connection_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._connection_frame.grid(row=0, column=0, sticky="w", padx=8, pady=4)
        
        self._connection_indicator = ctk.CTkLabel(
            self._connection_frame,
            text="⚫",
            font=Fonts.BODY,
        )
        self._connection_indicator.pack(side="left", padx=(0, 4))
        
        self._connection_label = ctk.CTkLabel(
            self._connection_frame,
            text="TechAura: Desconectado",
            font=Fonts.SMALL,
        )
        self._connection_label.pack(side="left")
        
        # USB count
        self._usb_label = ctk.CTkLabel(
            self,
            text="💿 USBs: 0",
            font=Fonts.SMALL,
        )
        self._usb_label.grid(row=0, column=1, sticky="w", padx=8, pady=4)
        
        # Current job
        self._job_label = ctk.CTkLabel(
            self,
            text="Job: Ninguno",
            font=Fonts.SMALL,
        )
        self._job_label.grid(row=0, column=2, sticky="w", padx=8, pady=4)
        
        # Last refresh
        self._refresh_label = ctk.CTkLabel(
            self,
            text="Último refresh: --",
            font=Fonts.SMALL,
        )
        self._refresh_label.grid(row=0, column=3, sticky="e", padx=8, pady=4)
    
    def update_connection_status(
        self, connected: bool, connecting: bool = False
    ) -> None:
        """Update TechAura connection status."""
        if connecting:
            self._connection_indicator.configure(text="🟡")
            self._connection_label.configure(
                text="TechAura: Reconectando...",
                text_color=Colors.CONNECTING,
            )
        elif connected:
            self._connection_indicator.configure(text="🟢")
            self._connection_label.configure(
                text="TechAura: Conectado",
                text_color=Colors.CONNECTED,
            )
        else:
            self._connection_indicator.configure(text="🔴")
            self._connection_label.configure(
                text="TechAura: Desconectado",
                text_color=Colors.DISCONNECTED,
            )
    
    def update_usb_count(self, count: int) -> None:
        """Update USB count."""
        self._usb_label.configure(text=f"💿 USBs: {count}")
    
    def update_current_job(self, job_name: str | None) -> None:
        """Update current job display."""
        if job_name:
            self._job_label.configure(text=f"Job: {job_name}")
        else:
            self._job_label.configure(text="Job: Ninguno")
    
    def update_last_refresh(self, timestamp: str) -> None:
        """Update last refresh timestamp."""
        self._refresh_label.configure(text=f"Último refresh: {timestamp}")


class Tooltip:
    """Tooltip component for hover text."""
    
    def __init__(self, widget: ctk.CTkBaseClass, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tooltip_window: ctk.CTkToplevel | None = None
        self._schedule_id: str | None = None
        
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, event=None) -> None:
        """Handle mouse enter."""
        self._schedule_id = self.widget.after(
            Styles.TOOLTIP_DELAY_MS, self._show_tooltip
        )
    
    def _on_leave(self, event=None) -> None:
        """Handle mouse leave."""
        if self._schedule_id:
            self.widget.after_cancel(self._schedule_id)
            self._schedule_id = None
        self._hide_tooltip()
    
    def _show_tooltip(self) -> None:
        """Show tooltip window."""
        if self.tooltip_window:
            return
        
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True)
        
        frame = ctk.CTkFrame(
            self.tooltip_window,
            fg_color=Styles.TOOLTIP_BG,
            corner_radius=4,
        )
        frame.pack()
        
        label = ctk.CTkLabel(
            frame,
            text=self.text,
            font=Fonts.SMALL,
            text_color=Styles.TOOLTIP_FG,
        )
        label.pack(padx=8, pady=4)
    
    def _hide_tooltip(self) -> None:
        """Hide tooltip window."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
