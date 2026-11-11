from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=50, fill="#152033")
for x, y, color in [(49, 67, "#426681"), (72, 86, "#83c6d9"), (95, 104, "#e3f2f8")]:
    draw.rounded_rectangle((x, y, x + 101, y + 72), radius=12, fill="#152033", outline=color, width=8)
image.save(Path(__file__).with_name("MediaSuite.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
