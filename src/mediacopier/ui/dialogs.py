"""Improved dialogs for MediaCopier."""

from __future__ import annotations

import customtkinter as ctk

from mediacopier.api.techaura_client import USBOrder
from mediacopier.core.usb_detector import RemovableDrive
from mediacopier.ui.styles import Colors, Emojis, Fonts


class ConfirmationDialog(ctk.CTkToplevel):
    """Improved confirmation dialog for burning orders."""
    
    def __init__(
        self,
        parent: ctk.CTk,
        order: USBOrder,
        usb: RemovableDrive,
        estimated_time_minutes: int,
    ) -> None:
        super().__init__(parent)
        
        self.result: bool = False
        self._verified = ctk.BooleanVar(value=False)
        
        # Configure window
        self.title("Confirmar Grabación")
        self.geometry("600x700")
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
        # Create scrollable frame for content
        scroll_frame = ctk.CTkScrollableFrame(self)
        scroll_frame.pack(fill="both", expand=True, padx=16, pady=16)
        
        # Title
        title_label = ctk.CTkLabel(
            scroll_frame,
            text="⚠️ Confirmar Grabación USB",
            font=Fonts.TITLE,
            text_color=Colors.WARNING,
        )
        title_label.pack(pady=(0, 16))
        
        # Order details section
        self._create_section(scroll_frame, "Resumen del Pedido")
        
        # Order number
        self._create_info_row(
            scroll_frame,
            f"{Emojis.ORDER_NUMBER} Número de pedido:",
            order.order_id,
        )
        
        # Customer
        customer_info = order.customer_name
        if order.customer_phone:
            customer_info += f" ({order.customer_phone})"
        self._create_info_row(
            scroll_frame,
            f"{Emojis.CUSTOMER} Cliente:",
            customer_info,
        )
        
        # Content type
        content_emoji = {
            "music": Emojis.MUSIC,
            "videos": Emojis.VIDEOS,
            "movies": Emojis.MOVIES,
        }.get(order.product_type, "📦")
        
        content_label = {
            "music": "Música",
            "videos": "Videos",
            "movies": "Películas",
        }.get(order.product_type, order.product_type)
        
        self._create_info_row(
            scroll_frame,
            f"{content_emoji} Tipo de contenido:",
            content_label,
        )
        
        # USB capacity
        capacity_label = self._format_capacity(order.usb_capacity_gb)
        self._create_info_row(
            scroll_frame,
            f"{Emojis.CAPACITY} Capacidad:",
            capacity_label,
        )
        
        # Genres (if applicable)
        if order.genres:
            self._create_info_row(
                scroll_frame,
                f"{Emojis.GENRES} Géneros:",
                "",
            )
            for genre in order.genres:
                bullet_label = ctk.CTkLabel(
                    scroll_frame,
                    text=f"  • {genre}",
                    font=Fonts.BODY,
                    anchor="w",
                )
                bullet_label.pack(fill="x", padx=(32, 16), pady=2)
        
        # Artists (if applicable)
        if order.artists:
            self._create_info_row(
                scroll_frame,
                f"{Emojis.ARTISTS} Artistas:",
                "",
            )
            for artist in order.artists:
                bullet_label = ctk.CTkLabel(
                    scroll_frame,
                    text=f"  • {artist}",
                    font=Fonts.BODY,
                    anchor="w",
                )
                bullet_label.pack(fill="x", padx=(32, 16), pady=2)
        
        # Order date
        if order.created_at:
            date_str = order.created_at.strftime("%Y-%m-%d %H:%M")
            self._create_info_row(
                scroll_frame,
                f"{Emojis.DATE} Fecha del pedido:",
                date_str,
            )
        
        # USB details section
        self._create_section(scroll_frame, "Información del USB")
        
        self._create_info_row(
            scroll_frame,
            f"{Emojis.USB} Dispositivo:",
            usb.name,
        )
        
        self._create_info_row(
            scroll_frame,
            "Ruta:",
            usb.path,
        )
        
        usb_capacity_str = f"{usb.size_gb:.1f} GB"
        usb_free_str = f"{usb.free_gb:.1f} GB disponibles"
        self._create_info_row(
            scroll_frame,
            "Espacio:",
            f"{usb_capacity_str} ({usb_free_str})",
        )
        
        # Estimated time section
        self._create_section(scroll_frame, "Tiempo Estimado")
        
        time_str = self._format_estimated_time(estimated_time_minutes)
        time_label = ctk.CTkLabel(
            scroll_frame,
            text=f"⏱️ Tiempo estimado: {time_str}",
            font=Fonts.HEADING,
            text_color=Colors.INFO,
        )
        time_label.pack(pady=8, padx=16)
        
        # Verification checkbox
        verify_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        verify_frame.pack(pady=16, padx=16, fill="x")
        
        verify_checkbox = ctk.CTkCheckBox(
            verify_frame,
            text="✓ He verificado los datos del pedido y el USB",
            variable=self._verified,
            font=Fonts.BODY,
            text_color=Colors.WARNING,
        )
        verify_checkbox.pack(pady=8)
        
        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=16, padx=16, fill="x")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancelar",
            font=Fonts.BODY,
            command=self._on_cancel,
            fg_color=Colors.SECONDARY,
            hover_color=Colors.TEXT_SECONDARY,
        )
        cancel_btn.grid(row=0, column=0, padx=8, sticky="ew")
        
        confirm_btn = ctk.CTkButton(
            button_frame,
            text="Confirmar Grabación",
            font=Fonts.BODY,
            command=self._on_confirm,
            fg_color=Colors.SUCCESS,
            hover_color=Colors.LOG_SUCCESS,
        )
        confirm_btn.grid(row=0, column=1, padx=8, sticky="ew")
    
    def _create_section(self, parent: ctk.CTkFrame, title: str) -> None:
        """Create a section header."""
        separator = ctk.CTkFrame(parent, height=2, fg_color=Colors.SECONDARY)
        separator.pack(fill="x", pady=(16, 8), padx=16)
        
        label = ctk.CTkLabel(
            parent,
            text=title,
            font=Fonts.SUBTITLE,
            anchor="w",
        )
        label.pack(fill="x", padx=16, pady=(0, 8))
    
    def _create_info_row(
        self, parent: ctk.CTkFrame, label: str, value: str
    ) -> None:
        """Create an information row."""
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill="x", padx=16, pady=4)
        row_frame.grid_columnconfigure(1, weight=1)
        
        label_widget = ctk.CTkLabel(
            row_frame,
            text=label,
            font=Fonts.BODY,
            anchor="w",
        )
        label_widget.grid(row=0, column=0, sticky="w", padx=(0, 8))
        
        if value:
            value_widget = ctk.CTkLabel(
                row_frame,
                text=value,
                font=Fonts.BODY,
                anchor="w",
                text_color=Colors.TEXT_PRIMARY,
            )
            value_widget.grid(row=0, column=1, sticky="w")
    
    def _format_capacity(self, capacity_gb: int) -> str:
        """Format USB capacity."""
        return f"{capacity_gb} GB"
    
    def _format_estimated_time(self, minutes: int) -> str:
        """Format estimated time."""
        if minutes < 60:
            return f"{minutes} minutos"
        else:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours} hora{'s' if hours > 1 else ''}"
            return f"{hours} hora{'s' if hours > 1 else ''} {remaining_minutes} minutos"
    
    def _on_confirm(self) -> None:
        """Handle confirm button."""
        if not self._verified.get():
            # Show warning if not verified
            warning = ctk.CTkToplevel(self)
            warning.title("Verificación Requerida")
            warning.geometry("400x150")
            warning.transient(self)
            warning.grab_set()
            
            # Center on parent
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() - 400) // 2
            y = self.winfo_y() + (self.winfo_height() - 150) // 2
            warning.geometry(f"+{x}+{y}")
            
            label = ctk.CTkLabel(
                warning,
                text="⚠️ Por favor, verifica que has revisado\ntodos los datos antes de confirmar.",
                font=Fonts.BODY,
                text_color=Colors.WARNING,
            )
            label.pack(pady=24)
            
            ok_btn = ctk.CTkButton(
                warning,
                text="Entendido",
                command=warning.destroy,
            )
            ok_btn.pack(pady=8)
            return
        
        self.result = True
        self.destroy()
    
    def _on_cancel(self) -> None:
        """Handle cancel button."""
        self.result = False
        self.destroy()
    
    def wait_for_result(self) -> bool:
        """Wait for user response."""
        self.wait_window()
        return self.result
