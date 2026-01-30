"""Advanced USB management operations."""

import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from mediacopier.api.techaura_client import USBOrder

logger = logging.getLogger(__name__)


class USBManager:
    """Gestión avanzada de operaciones USB."""

    def rename_usb_for_order(self, order: USBOrder, usb_path: str) -> bool:
        """Renombrar la USB con los primeros 6 dígitos del teléfono del cliente.
        
        Args:
            order: Orden USB con información del cliente.
            usb_path: Ruta del dispositivo USB.
            
        Returns:
            True si se renombró exitosamente, False en caso contrario.
        """
        try:
            # Obtener primeros 6 dígitos del teléfono (sin espacios ni símbolos)
            phone = ''.join(filter(str.isdigit, order.customer_phone))[:6]
            if not phone:
                # Fallback: usar primeros 6 caracteres del número de orden
                phone = order.order_number[:6]
                logger.warning(
                    f"No phone digits found for order {order.order_id}, "
                    f"using order number instead: {phone}"
                )
            
            logger.info(f"Renaming USB to: {phone}")
            
            # Renombrar volumen USB (Windows)
            if os.name == 'nt':
                drive_letter = os.path.splitdrive(usb_path)[0]
                if not drive_letter:
                    logger.error(f"Invalid USB path (no drive letter): {usb_path}")
                    return False
                
                # Use label command to rename volume
                result = subprocess.run(
                    ['label', drive_letter, phone],
                    check=True,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                logger.info(f"USB renamed successfully to {phone}: {result.stdout}")
                return True
            
            # Renombrar volumen USB (Linux/Mac)
            elif os.name == 'posix':
                # On Linux, use fatlabel for FAT filesystems
                # This is a simplified implementation
                logger.warning("USB renaming on Linux/Mac not fully implemented")
                return False
            
            else:
                logger.error(f"Unsupported OS for USB renaming: {os.name}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout while renaming USB for order {order.order_id}")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Error renaming USB: {e.stderr if e.stderr else str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error renaming USB: {e}")
            return False

    def rename_volume(self, drive_path: str, new_name: str) -> bool:
        """Renombrar volumen USB.
        
        Args:
            drive_path: Ruta del dispositivo USB.
            new_name: Nuevo nombre para el volumen.
            
        Returns:
            True si se renombró exitosamente, False en caso contrario.
        """
        try:
            logger.info(f"Renaming volume {drive_path} to {new_name}")
            
            if os.name == 'nt':
                drive_letter = os.path.splitdrive(drive_path)[0]
                if not drive_letter:
                    logger.error(f"Invalid drive path (no drive letter): {drive_path}")
                    return False
                
                result = subprocess.run(
                    ['label', drive_letter, new_name],
                    check=True,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                logger.info(f"Volume renamed successfully: {result.stdout}")
                return True
            else:
                logger.warning(f"Volume renaming not implemented for OS: {os.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error renaming volume: {e}")
            return False

    def verify_copy(self, source: str, dest: str) -> bool:
        """Verificar integridad de copia con checksum.
        
        Args:
            source: Ruta del archivo fuente.
            dest: Ruta del archivo destino.
            
        Returns:
            True si los checksums coinciden, False en caso contrario.
        """
        try:
            source_path = Path(source)
            dest_path = Path(dest)
            
            if not source_path.exists():
                logger.error(f"Source file does not exist: {source}")
                return False
            
            if not dest_path.exists():
                logger.error(f"Destination file does not exist: {dest}")
                return False
            
            # Verificar tamaño primero (más rápido)
            source_size = source_path.stat().st_size
            dest_size = dest_path.stat().st_size
            
            if source_size != dest_size:
                logger.error(
                    f"File size mismatch: {source} ({source_size}) vs "
                    f"{dest} ({dest_size})"
                )
                return False
            
            # Calcular checksums MD5
            source_checksum = self._calculate_checksum(source_path)
            dest_checksum = self._calculate_checksum(dest_path)
            
            if source_checksum != dest_checksum:
                logger.error(
                    f"Checksum mismatch: {source} ({source_checksum}) vs "
                    f"{dest} ({dest_checksum})"
                )
                return False
            
            logger.info(f"Copy verified successfully: {dest}")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying copy: {e}")
            return False

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calcular checksum MD5 de un archivo.
        
        Args:
            file_path: Ruta del archivo.
            
        Returns:
            Checksum MD5 del archivo.
        """
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            # Leer en bloques para archivos grandes
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def create_folder_structure(self, dest: str, structure: dict) -> bool:
        """Crear estructura de carpetas organizada.
        
        Args:
            dest: Directorio destino base.
            structure: Diccionario con la estructura de carpetas.
                      Ej: {"Música": ["Rock", "Pop"], "Videos": []}
            
        Returns:
            True si se creó exitosamente, False en caso contrario.
        """
        try:
            dest_path = Path(dest)
            
            if not dest_path.exists():
                logger.error(f"Destination path does not exist: {dest}")
                return False
            
            for folder, subfolders in structure.items():
                folder_path = dest_path / folder
                folder_path.mkdir(exist_ok=True)
                logger.debug(f"Created folder: {folder_path}")
                
                # Crear subcarpetas si existen
                for subfolder in subfolders:
                    subfolder_path = folder_path / subfolder
                    subfolder_path.mkdir(exist_ok=True)
                    logger.debug(f"Created subfolder: {subfolder_path}")
            
            logger.info(f"Folder structure created successfully in {dest}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating folder structure: {e}")
            return False

    def cleanup_temp_files(self, path: str) -> None:
        """Limpiar archivos temporales.
        
        Args:
            path: Ruta del directorio a limpiar.
        """
        try:
            path_obj = Path(path)
            
            if not path_obj.exists():
                logger.warning(f"Path does not exist for cleanup: {path}")
                return
            
            # Patrones de archivos temporales comunes
            temp_patterns = [
                '*.tmp',
                '*.temp',
                '*~',
                '.DS_Store',
                'Thumbs.db',
                'desktop.ini',
                '._*'  # macOS resource forks
            ]
            
            cleaned_count = 0
            for pattern in temp_patterns:
                for temp_file in path_obj.rglob(pattern):
                    try:
                        if temp_file.is_file():
                            temp_file.unlink()
                            cleaned_count += 1
                            logger.debug(f"Removed temp file: {temp_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove {temp_file}: {e}")
            
            logger.info(f"Cleaned up {cleaned_count} temporary files from {path}")
            
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")

    def validate_path(self, path: str, must_exist: bool = True, must_be_writable: bool = False) -> bool:
        """Validar una ruta antes de operaciones de copia.
        
        Args:
            path: Ruta a validar.
            must_exist: Si True, la ruta debe existir.
            must_be_writable: Si True, la ruta debe ser escribible.
            
        Returns:
            True si la ruta es válida, False en caso contrario.
        """
        try:
            path_obj = Path(path)
            
            # Validar que la ruta no esté vacía
            if not path or path.strip() == '':
                logger.error("Path is empty")
                return False
            
            # Validar caracteres peligrosos
            dangerous_chars = ['..', '<', '>', '|', '\x00']
            path_str = str(path_obj)
            if any(char in path_str for char in dangerous_chars):
                logger.error(f"Path contains dangerous characters: {path}")
                return False
            
            # Verificar existencia
            if must_exist and not path_obj.exists():
                logger.error(f"Path does not exist: {path}")
                return False
            
            # Verificar permisos de escritura
            if must_be_writable:
                if path_obj.exists():
                    if not os.access(path_obj, os.W_OK):
                        logger.error(f"Path is not writable: {path}")
                        return False
                else:
                    # Verificar que el directorio padre sea escribible
                    parent = path_obj.parent
                    if not parent.exists() or not os.access(parent, os.W_OK):
                        logger.error(f"Parent directory is not writable: {parent}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating path: {e}")
            return False
