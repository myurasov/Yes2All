"""Render a clean SF Symbols-style checkmark for the Yes2All app icon.

  * `icon-dark.png` / `icon-dark@2x.png`  — black checkmark on transparent
    (used when the system is in Light mode).
  * `icon-light.png` / `icon-light@2x.png` — white checkmark on transparent
    (used when the system is in Dark mode).
  * `icon-large-dark.png` / `icon-large-light.png` — 256px versions for
    the About dialog.

Run with:  uv run --with pillow python scripts/render_icon.py
Pillow is intentionally not a runtime dependency.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


OUT = Path(__file__).resolve().parent.parent / "src" / "yes2all" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def _draw_check(size: int, color, pad: float = 0.0) -> Image.Image:
    """Flat SF Symbols-style checkmark.

    `pad` is the fraction of the canvas reserved as transparent margin on
    each side — useful for shrinking the menubar glyph.
    """
    SCALE = 8
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inner = s * (1.0 - 2 * pad)
    off = s * pad
    pts = [
        (off + inner * 0.16, off + inner * 0.54),
        (off + inner * 0.42, off + inner * 0.78),
        (off + inner * 0.86, off + inner * 0.22),
    ]
    w = max(2, int(round(inner * 0.16)))
    d.line([pts[0], pts[1]], fill=color, width=w)
    d.line([pts[1], pts[2]], fill=color, width=w)
    rr = w / 2
    for x, y in pts:
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=color)
    return img.resize((size, size), Image.LANCZOS)


def _draw_circle(size: int, color, pad: float = 0.0) -> Image.Image:
    """Hairline open circle, matching the checkmark's stroke weight."""
    SCALE = 8
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    inner = s * (1.0 - 2 * pad)
    off = s * pad
    w = max(2, int(round(inner * 0.13)))
    # Inset slightly so the stroke fits inside the inner box.
    inset = w / 2 + max(1, int(s * 0.01))
    d.ellipse(
        [off + inset, off + inset,
         off + inner - inset, off + inner - inset],
        outline=color, width=w,
    )
    return img.resize((size, size), Image.LANCZOS)


def render_check(size: int, path: Path, color, pad: float = 0.0) -> None:
    _draw_check(size, color, pad=pad).save(path)


def render_circle(size: int, path: Path, color, pad: float = 0.0) -> None:
    _draw_circle(size, color, pad=pad).save(path)


def main() -> None:
    BLACK = (0, 0, 0, 255)
    WHITE = (255, 255, 255, 255)
    MENU_PAD = 0.15  # shrink the menubar glyph a bit

    # Menubar checkmark (loaded state).
    render_check(22, OUT / "icon-dark.png", BLACK, pad=MENU_PAD)
    render_check(44, OUT / "icon-dark@2x.png", BLACK, pad=MENU_PAD)
    render_check(22, OUT / "icon-light.png", WHITE, pad=MENU_PAD)
    render_check(44, OUT / "icon-light@2x.png", WHITE, pad=MENU_PAD)

    # Menubar circle (stopped state).
    render_circle(22, OUT / "icon-off-dark.png", BLACK, pad=MENU_PAD)
    render_circle(44, OUT / "icon-off-dark@2x.png", BLACK, pad=MENU_PAD)
    render_circle(22, OUT / "icon-off-light.png", WHITE, pad=MENU_PAD)
    render_circle(44, OUT / "icon-off-light@2x.png", WHITE, pad=MENU_PAD)

    # About dialog (full-bleed checkmark).
    render_check(256, OUT / "icon-large-dark.png", BLACK)
    render_check(256, OUT / "icon-large-light.png", WHITE)

    print("rendered:", *sorted(p.name for p in OUT.glob("icon*.png")))


if __name__ == "__main__":
    main()
