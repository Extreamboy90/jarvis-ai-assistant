#!/usr/bin/env python3
"""
Generate placeholder icons for PWA
Creates simple colored squares with "J" text
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Icon sizes
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# Colors
BG_COLOR = (26, 26, 46)  # Dark blue
TEXT_COLOR = (233, 69, 96)  # Accent red

def generate_icon(size):
    """Generate a single icon"""
    # Create image
    img = Image.new('RGB', (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fallback to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size // 2)
    except:
        font = ImageFont.load_default()

    # Draw text
    text = "J"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 10

    draw.text((x, y), text, fill=TEXT_COLOR, font=font)

    return img

def main():
    # Create icons directory
    icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
    os.makedirs(icons_dir, exist_ok=True)

    print("🎨 Generating PWA icons...")

    for size in SIZES:
        icon = generate_icon(size)
        filename = f"icon-{size}.png"
        filepath = os.path.join(icons_dir, filename)
        icon.save(filepath)
        print(f"  ✓ {filename}")

    print(f"\n✅ Generated {len(SIZES)} icons in {icons_dir}/")
    print("   You can replace these with custom icons later")

if __name__ == '__main__':
    try:
        main()
    except ImportError:
        print("❌ Pillow not installed. Run: pip install Pillow")
        print("   Or create icons manually in pwa/icons/")
