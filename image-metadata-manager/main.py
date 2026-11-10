"""
Image Metadata Manager
----------------------
A small command line tool to inspect, export and strip EXIF metadata
from images stored in the ./media folder.

Usage:
    python main.py

Requirements:
    pip install Pillow
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, ImageOps
from PIL.ExifTags import TAGS

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
MEDIA_DIR = ROOT_DIR / "media"
OUTPUT_DIR = ROOT_DIR / "output"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}

# EXIF tags that only point to sub-sections and carry no useful value
POINTER_TAGS = {"ExifOffset", "GPSInfo", "InteropOffset"}

MAX_VALUE_WIDTH = 60  # Long values are truncated in the terminal view only


# --------------------------------------------------------------------------
# Terminal styling
# --------------------------------------------------------------------------

class Style:
    """ANSI escape codes used to colour the terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"


def enable_ansi_on_windows() -> None:
    """Calling os.system with an empty command enables ANSI in Windows consoles."""
    if os.name == "nt":
        os.system("")


def paint(text: str, *styles: str) -> str:
    return "".join(styles) + text + Style.RESET


def print_header(title: str) -> None:
    line = "=" * 64
    print(f"\n{paint(line, Style.CYAN)}")
    print(paint(f"  {title}", Style.BOLD, Style.CYAN))
    print(paint(line, Style.CYAN))


def print_section(title: str) -> None:
    print(f"\n{paint(title.upper(), Style.BOLD, Style.YELLOW)}")
    print(paint("-" * 64, Style.DIM))


# --------------------------------------------------------------------------
# Metadata extraction
# --------------------------------------------------------------------------

def make_serializable(value: Any) -> Any:
    """Convert EXIF values (rationals, bytes, tuples) into JSON friendly types."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8").strip("\x00").strip()
        except UnicodeDecodeError:
            return f"<{len(value)} bytes of binary data>"
    if isinstance(value, (tuple, list)):
        return [make_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): make_serializable(v) for k, v in value.items()}
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    try:
        return float(value)  # PIL IFDRational
    except (TypeError, ValueError):
        return str(value)


def dms_to_decimal(dms: list[float], ref: str) -> float:
    """Convert degrees, minutes, seconds to signed decimal degrees."""
    degrees, minutes, seconds = dms
    decimal = degrees + minutes / 60 + seconds / 3600
    return round(-decimal if ref in ("S", "W") else decimal, 6)


def extract_gps(gps_ifd: dict[int, Any]) -> dict[str, Any]:
    """Build a readable GPS block, including decimal coordinates when available."""
    gps = {
        ExifTags.GPSTAGS.get(tag, f"Unknown_{tag}"): make_serializable(value)
        for tag, value in gps_ifd.items()
    }

    try:
        latitude = dms_to_decimal(gps["GPSLatitude"], gps["GPSLatitudeRef"])
        longitude = dms_to_decimal(gps["GPSLongitude"], gps["GPSLongitudeRef"])
        gps["DecimalLatitude"] = latitude
        gps["DecimalLongitude"] = longitude
        gps["MapsLink"] = f"https://www.google.com/maps?q={latitude},{longitude}"
    except KeyError:
        pass  # The image has partial or no coordinates

    return gps


def extract_metadata(path: Path) -> dict[str, Any]:
    """Return file information, EXIF tags and GPS data for one image."""
    stats = path.stat()

    with Image.open(path) as image:
        exif = image.getexif()

        # Merge the base IFD with the Exif sub-IFD (exposure, lens, dates...)
        tags = dict(exif)
        tags.update(exif.get_ifd(ExifTags.IFD.Exif))

        exif_data = {}
        for tag_id, value in tags.items():
            name = TAGS.get(tag_id, f"Unknown_{tag_id}")
            if name not in POINTER_TAGS:
                exif_data[name] = make_serializable(value)

        return {
            "file": {
                "name": path.name,
                "size_kb": round(stats.st_size / 1024, 1),
                "format": image.format,
                "mode": image.mode,
                "dimensions": f"{image.width}x{image.height}",
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(timespec="seconds"),
            },
            "exif": exif_data,
            "gps": extract_gps(exif.get_ifd(ExifTags.IFD.GPSInfo)),
        }


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def display_metadata(metadata: dict[str, Any]) -> None:
    """Print the metadata as aligned, coloured sections."""
    print_header(f"Metadata: {metadata['file']['name']}")

    for section, content in metadata.items():
        print_section(section)

        if not content:
            print(paint("  No data found", Style.DIM))
            continue

        key_width = max(len(key) for key in content) + 2
        for key, value in content.items():
            text = str(value)
            if len(text) > MAX_VALUE_WIDTH:
                text = text[: MAX_VALUE_WIDTH - 3] + "..."
            print(f"  {paint(key.ljust(key_width), Style.GREEN)}{text}")


def export_metadata(metadata: dict[str, Any], image_path: Path) -> Path:
    """Write the metadata to output/<image>_metadata.json."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    destination = OUTPUT_DIR / f"{image_path.stem}_metadata.json"

    with destination.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4, ensure_ascii=False)

    return destination


def strip_metadata(image_path: Path) -> Path:
    """
    Save a metadata free copy to output/cleaned/.
    The original file is never modified.
    """
    clean_dir = OUTPUT_DIR / "cleaned"
    clean_dir.mkdir(parents=True, exist_ok=True)
    destination = clean_dir / f"{image_path.stem}_clean{image_path.suffix}"

    with Image.open(image_path) as image:
        # Apply the orientation flag first so the photo is not rotated once EXIF is gone
        image = ImageOps.exif_transpose(image)

        # Rebuilding the image from raw pixels guarantees nothing else is carried over
        clean = Image.frombytes(image.mode, image.size, image.tobytes())

        save_options = {"quality": 95} if image_path.suffix.lower() in {".jpg", ".jpeg"} else {}
        clean.save(destination, **save_options)

    return destination


# --------------------------------------------------------------------------
# User interface
# --------------------------------------------------------------------------

def list_images() -> list[Path]:
    """Return the supported images found in the media folder, sorted by name."""
    MEDIA_DIR.mkdir(exist_ok=True)
    return sorted(
        path for path in MEDIA_DIR.iterdir()
        if path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def prompt_choice(message: str, valid: set[str]) -> str:
    """Keep asking until the user enters one of the valid options."""
    while True:
        answer = input(paint(message, Style.BOLD)).strip().lower()
        if answer in valid:
            return answer
        print(paint("  Invalid choice, please try again.", Style.RED))


def action_menu(image_path: Path) -> None:
    """Let the user act on a single image until they go back."""
    metadata = extract_metadata(image_path)

    while True:
        print_header(f"Selected: {image_path.name}")
        print("  [1] View metadata")
        print("  [2] Export metadata to JSON")
        print("  [3] Remove metadata (saves a clean copy)")
        print("  [b] Back to image list")

        choice = prompt_choice("\nChoose an action: ", {"1", "2", "3", "b"})

        if choice == "1":
            display_metadata(metadata)
        elif choice == "2":
            destination = export_metadata(metadata, image_path)
            print(paint(f"\n  Exported to {destination.relative_to(ROOT_DIR)}", Style.GREEN))
        elif choice == "3":
            destination = strip_metadata(image_path)
            print(paint(f"\n  Clean copy saved to {destination.relative_to(ROOT_DIR)}", Style.GREEN))
        else:
            return


def main() -> None:
    enable_ansi_on_windows()

    while True:
        images = list_images()
        print_header("Image Metadata Manager")

        if not images:
            print(paint(f"\n  No images found. Drop files into: {MEDIA_DIR}", Style.YELLOW))
            return

        for index, path in enumerate(images, start=1):
            print(f"  [{index}] {path.name}")
        print("  [q] Quit")

        choice = prompt_choice(
            "\nSelect an image: ",
            {str(i) for i in range(1, len(images) + 1)} | {"q"},
        )
        if choice == "q":
            print(paint("\n  Goodbye.\n", Style.CYAN))
            return

        try:
            action_menu(images[int(choice) - 1])
        except OSError as error:
            print(paint(f"\n  Could not process the file: {error}", Style.RED))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(paint("\n\n  Interrupted.", Style.DIM))
