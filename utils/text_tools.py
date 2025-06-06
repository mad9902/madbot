from typing import Literal, Optional
from PIL import Image, ImageDraw, ImageFont

Placement = Literal["top", "bottom"]
CaseType = Literal["uppercase", "lowercase", "caption"]


def get_scaled_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    image_width: int,
    image_height: int,
    font_path: str = "assets/Inter.ttf",
    max_text_height_ratio: float = 0.15,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str]]:
    max_font_size = int(image_height * max_text_height_ratio)
    min_font_size = 10

    for size in range(max_font_size, min_font_size - 1, -1):
        try:
            font = ImageFont.truetype(
                font_path, size, layout_engine=ImageFont.Layout.BASIC
            )
            font.set_variation_by_name("Bold")
        except IOError:
            continue

        lines = wrap_text(draw, text, font, max_width=int(image_width * 0.9))
        line_heights = [measure_text(draw, line, font)[1] for line in lines]
        total_height = sum(line_heights)

        if total_height <= image_height * max_text_height_ratio:
            return font, lines

    # Fallback
    fallback_font = ImageFont.load_default()
    lines = wrap_text(draw, text, fallback_font, max_width=int(image_width * 0.9))
    return fallback_font, lines


def apply_text_case(text: str, case: CaseType) -> str:
    if case == "uppercase":
        return text.upper()
    elif case == "lowercase":
        return text.lower()
    elif case == "caption":
        return text.capitalize()
    return text


def measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        width, _ = measure_text(draw, test_line, font)
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def place_text(
    image: Image.Image,
    text: str,
    placement: Placement = "bottom",
    settings: Optional[dict] = None,
) -> Image.Image:
    try:
        draw = ImageDraw.Draw(image)
        width, height = image.size

        # Default settings
        text_color = (255, 255, 255)
        stroke_color = (0, 0, 0)
        stroke_width = 2
        case_type: CaseType = "caption"

        if settings:
            text_color = settings.get("text_color", text_color)
            stroke_color = settings.get("stroke_color", stroke_color)
            stroke_width = settings.get("stroke_width", stroke_width)
            case_type = settings.get("type", case_type)

        # Apply case
        text = apply_text_case(text, case_type)

        # Dynamic font with smart wrapping
        font, lines = get_scaled_font(draw, text, width, height)

        # Measure total text height
        line_heights = [measure_text(draw, line, font)[1] for line in lines]
        total_text_height = sum(line_heights)

        # Calculate starting y position
        y = (
            height * 0.125
            if placement == "top"
            else height - total_text_height - height * 0.125
        )

        # Draw each line
        for line, lh in zip(lines, line_heights):
            text_width, _ = measure_text(draw, line, font)
            x = (width - text_width) // 2
            draw.text(
                (x, y),
                line,
                font=font,
                fill=text_color,
                stroke_fill=stroke_color,
                stroke_width=stroke_width,
            )
            y += lh + lh * 0.5

        return image

    except Exception as e:
        raise RuntimeError(f"Failed to place text: {e}")
