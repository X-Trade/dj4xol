"""Generated thumbnail variant helpers."""

from __future__ import annotations

from pathlib import Path


BLUR_SUFFIX = "__blur.png"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "dj4xol" / "static"
THUMBS_ROOT = STATIC_ROOT / "dj4xol" / "images" / "thumbs"


def is_blur_variant_path(path):
    if not path:
        return False
    return str(path).endswith(BLUR_SUFFIX)


def blur_variant_path(path):
    if not path:
        return path
    if is_blur_variant_path(path):
        return path
    source = Path(str(path))
    return source.with_name(source.stem + BLUR_SUFFIX).as_posix()


def get_blur_variant_path(path):
    """Return the generated blur variant when present, else the original path."""
    if not path:
        return path
    variant = blur_variant_path(path)
    if (STATIC_ROOT / variant).exists():
        return variant
    return path


def _blur_rgba_image(image):
    from PIL import Image, ImageEnhance, ImageFilter

    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    rgb = Image.merge("RGB", (red, green, blue))
    rgb = rgb.filter(ImageFilter.GaussianBlur(radius=6.0))
    rgb = ImageEnhance.Color(rgb).enhance(0.72)
    rgb = ImageEnhance.Brightness(rgb).enhance(0.90)
    return Image.merge("RGBA", (*rgb.split(), alpha))


def build_blur_variant(source_path, target_path):
    from PIL import Image

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(str(source_path)) as image:
        blurred = _blur_rgba_image(image)
        blurred.save(str(target_path))


def ensure_blur_variants(root, force=False):
    """Generate missing `__blur.png` variants for thumbnails beneath `root`."""
    root = Path(root)
    generated = 0
    refreshed = 0
    for png in sorted(root.rglob("*.png")):
        if not png.is_file() or png.name.endswith(BLUR_SUFFIX):
            continue
        target = png.with_name(png.stem + BLUR_SUFFIX)
        if target.exists():
            if not force:
                source_mtime = png.stat().st_mtime
                target_mtime = target.stat().st_mtime
                if target_mtime >= source_mtime:
                    continue
            refreshed += 1
        else:
            generated += 1
        build_blur_variant(png, target)
    return generated, refreshed


def ensure_all_blur_variants(force=False):
    results = {}
    for name in ("star", "ship", "anomaly", "salvage"):
        generated, refreshed = ensure_blur_variants(THUMBS_ROOT / name, force=force)
        results[name] = {
            "generated": generated,
            "refreshed": refreshed,
        }
    return results
