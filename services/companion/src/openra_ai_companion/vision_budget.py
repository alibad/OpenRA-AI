"""Bound the pixels sent to a vision model.

OpenRA's viewport arrives as a full-resolution PNG (often 1-3 MB at 1080p).
Vision cost scales with pixel area, and the hosted proxy accepts two inline
images per call, so every request is shrunk to two images totalling roughly
300 KB: the long edge is capped at 1024 px and photographic frames become
JPEG with a falling quality ladder until they fit. Small synthetic images such
as the tactical overview stay lossless PNG when they already fit.
"""

from __future__ import annotations

import io

MAX_IMAGES = 2
TOTAL_BYTES = 300_000
MAX_EDGE = 1024
_QUALITIES = (72, 62, 52, 42, 34)


def _encode(image, quality: int) -> bytes:
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
    return output.getvalue()


def _fit(data: bytes, media_type: str, budget: int, max_edge: int) -> tuple[bytes, str, dict] | None:
    try:
        from PIL import Image
    except ImportError:  # Pillow ships with the companion; without it only already-small images pass.
        return (data, media_type, {"sent_bytes": len(data), "format": media_type}) if len(data) <= budget else None
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError):
        # Undecodable bytes are passed through only when they already fit.
        return (data, media_type, {"sent_bytes": len(data), "format": media_type}) if len(data) <= budget else None
    width, height = image.size
    if len(data) <= budget and max(width, height) <= max_edge:
        return data, media_type, {"sent_width": width, "sent_height": height, "sent_bytes": len(data), "format": media_type}
    image = image.convert("RGB")
    if max(width, height) > max_edge:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    while True:
        for quality in _QUALITIES:
            encoded = _encode(image, quality)
            if len(encoded) <= budget:
                return encoded, "image/jpeg", {
                    "sent_width": image.size[0],
                    "sent_height": image.size[1],
                    "sent_bytes": len(encoded),
                    "format": "image/jpeg",
                    "jpeg_quality": quality,
                }
        if min(image.size) <= 160:
            return None
        image = image.resize((max(1, int(image.size[0] * 0.8)), max(1, int(image.size[1] * 0.8))), Image.Resampling.LANCZOS)


def fit_images(
    images: list[tuple[bytes, str]],
    views: list[dict],
    *,
    max_images: int = MAX_IMAGES,
    total_bytes: int = TOTAL_BYTES,
    max_edge: int = MAX_EDGE,
) -> tuple[list[tuple[bytes, str]], list[dict]]:
    """Return at most ``max_images`` images whose encoded sizes sum to ``total_bytes`` or less.

    Smaller images are fitted first so the leftover budget goes to the
    viewport. Views keep their original order and gain the sent size/format.
    """
    pairs = list(zip(images, views))[:max_images]
    order = sorted(range(len(pairs)), key=lambda index: len(pairs[index][0][0]))
    remaining = total_bytes
    fitted: dict[int, tuple[tuple[bytes, str], dict]] = {}
    for position, index in enumerate(order):
        (data, media_type), view = pairs[index]
        share = remaining // max(1, len(order) - position)
        result = _fit(data, media_type, share, max_edge)
        if result is None:
            continue
        encoded, encoded_type, details = result
        remaining -= len(encoded)
        fitted[index] = ((encoded, encoded_type), {**view, **details, "original_bytes": len(data)})
    kept = [fitted[index] for index in sorted(fitted)]
    for order_number, (_, view) in enumerate(kept, start=1):
        view["order"] = order_number
    return [image for image, _ in kept], [view for _, view in kept]
