from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
OUT = Path(__file__).resolve().parents[1] / "build" / "icon.png"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (SIZE, SIZE), (10, 15, 28, 255))
    draw = ImageDraw.Draw(image)

    # Deliberately simple, geometric mark that remains readable as a small tray icon.
    draw.rounded_rectangle((64, 64, 960, 960), radius=220, fill=(18, 28, 47, 255), outline=(75, 96, 129, 255), width=16)
    draw.line((280, 340, 512, 224, 744, 340), fill=(84, 180, 255, 255), width=34)
    draw.line((280, 340, 512, 512, 744, 340), fill=(84, 180, 255, 255), width=34)
    draw.line((280, 340, 280, 640, 512, 784, 744, 640, 744, 340), fill=(135, 229, 202, 255), width=28, joint="curve")
    for x, y, radius, fill in (
        (280, 340, 70, (84, 180, 255, 255)),
        (744, 340, 70, (84, 180, 255, 255)),
        (512, 224, 74, (135, 229, 202, 255)),
        (512, 512, 86, (240, 246, 255, 255)),
        (280, 640, 56, (135, 229, 202, 255)),
        (744, 640, 56, (135, 229, 202, 255)),
        (512, 784, 70, (135, 229, 202, 255)),
    ):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    image.save(OUT, format="PNG", optimize=True)
    print(f"Generated {OUT}")


if __name__ == "__main__":
    main()
