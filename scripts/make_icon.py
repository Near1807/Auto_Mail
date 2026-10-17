"""Génère assets/icon.ico (et icon.png) : enveloppe crème sur carré vermillon.

    python scripts/make_icon.py      (nécessite Pillow)
"""

from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (226, 85, 43, 255)
PAPER = (255, 248, 242, 255)
INK = (34, 28, 23, 255)
S = 1024  # dessin en grand, réduit ensuite (bords nets à toutes les tailles)


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=ACCENT)
    # enveloppe
    left, top, right, bottom = 208, 300, S - 208, S - 290
    d.rounded_rectangle((left, top, right, bottom), radius=70, fill=PAPER)
    mid = (left + right) // 2
    d.line([(left + 40, top + 40), (mid, top + 250), (right - 40, top + 40)], fill=ACCENT, width=64, joint="curve")
    # pastille « envoyé »
    cx, cy, r = right - 10, bottom - 10, 150
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    d.line([(cx - 70, cy + 5), (cx - 15, cy + 60), (cx + 75, cy - 55)], fill=PAPER, width=46, joint="curve")
    return img


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "assets"
    out.mkdir(exist_ok=True)
    big = draw()
    big.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big.resize((256, 256), Image.LANCZOS).save(out / "icon.ico", sizes=[(s, s) for s in sizes])
    print("icône écrite dans", out)


if __name__ == "__main__":
    main()
