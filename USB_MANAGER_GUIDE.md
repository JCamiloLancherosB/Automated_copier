# USB Manager Integration Guide

## Overview

The `USBManager` class provides advanced USB operations including:
- Volume renaming based on customer phone numbers
- Copy verification with checksums
- Folder structure creation
- Temporary file cleanup
- Path validation

## Usage Examples

### 1. Rename USB for Order

```python
from mediacopier.core.usb_manager import USBManager
from mediacopier.api.techaura_client import USBOrder

manager = USBManager()
order = USBOrder(
    order_id="123",
    order_number="ORD-001",
    customer_phone="+57 300 123 4567",
    customer_name="Juan Pérez",
    product_type="music",
    capacity="16GB"
)

# Rename USB with first 6 digits of phone (573001)
success = manager.rename_usb_for_order(order, "D:\\")
if success:
    print("USB renamed successfully")
```

### 2. Verify Copy Integrity

```python
# After copying a file, verify integrity
source = "/path/to/source/file.mp3"
dest = "D:\\Music\\file.mp3"

if manager.verify_copy(source, dest):
    print("Copy verified successfully")
else:
    print("Copy verification failed - checksums don't match")
```

### 3. Create Organized Folder Structure

```python
# Create organized folders on USB
structure = {
    "Música": ["Rock", "Pop", "Jazz"],
    "Videos": ["Conciertos", "Clips"],
    "Películas": []
}

manager.create_folder_structure("D:\\", structure)
```

### 4. Cleanup Temporary Files

```python
# Remove temporary files after copying
manager.cleanup_temp_files("D:\\")
# Removes: *.tmp, *.temp, *~, .DS_Store, Thumbs.db, desktop.ini
```

### 5. Validate Paths

```python
# Validate path before copying
if manager.validate_path("D:\\Music", must_exist=True, must_be_writable=True):
    # Safe to copy to this path
    pass
```

## Integration with Order Processor

The USBManager can be integrated into the copy workflow:

```python
from mediacopier.integration.order_processor import TechAuraOrderProcessor

# In the order processor, after creating the job:
usb_manager = USBManager()

# 1. Rename USB volume
usb_manager.rename_usb_for_order(order, usb_destination)

# 2. Create folder structure
structure = get_usb_music_folder_structure(order.genres, order.artists)
usb_manager.create_folder_structure(usb_destination, structure)

# 3. Copy files (existing copy logic)
# ...

# 4. Verify copied files
for file_path in copied_files:
    source = file_path
    dest = get_destination_path(file_path, usb_destination)
    if not usb_manager.verify_copy(source, dest):
        logger.error(f"Verification failed for {file_path}")

# 5. Cleanup
usb_manager.cleanup_temp_files(usb_destination)
```

## Error Handling

All USBManager methods include comprehensive error handling:

```python
try:
    success = manager.rename_usb_for_order(order, usb_path)
    if not success:
        # Handle failure
        logger.warning("USB renaming failed")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

## Platform Support

- **Windows**: Full support for volume renaming using `label` command
- **Linux/macOS**: Volume renaming not fully implemented yet
- **All platforms**: Copy verification, folder creation, cleanup, validation

## Security

The USBManager includes path validation to prevent:
- Path traversal attacks (../)
- Dangerous characters in paths
- Access to unauthorized locations

Always validate paths before operations:

```python
if manager.validate_path(user_input_path, must_exist=True):
    # Safe to proceed
    pass
```
