from typing import Union
from io import BytesIO
from PIL import Image, ImageFilter, UnidentifiedImageError
import smartcrop
import os

MAX_ANALYSIS_SIZE = 324

def pad_to_square_with_blur(cropped: Image.Image) -> Image.Image:
    w, h = cropped.size
    if w == h:
        return cropped

    canvas_size = max(w, h)

    background = (
        cropped.copy()
        .resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)
        .filter(ImageFilter.GaussianBlur(radius=15))
    )

    final = Image.new("RGB", (canvas_size, canvas_size))
    final.paste(background, (0, 0))

    offset = ((canvas_size - w) // 2, (canvas_size - h) // 2)
    final.paste(cropped, offset)

    return final


def crop_to_square(
    image_input: Union[str, BytesIO, Image.Image],
    output_size: int | None = None,
    zoom_threshold: float = 0.3,
) -> Image.Image:
    try:
        # * Try loading image
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image file not found: {image_input}")
            img = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            img = image_input
        elif isinstance(image_input, BytesIO):
            img = Image.open(image_input)
        else:
            raise ValueError("Unsupported input type for image_input")

        img.load()

    except FileNotFoundError as e:
        # ! Reraise
        raise e
    except UnidentifiedImageError:
        raise ValueError("The file could not be identified as a valid image.")
    except Exception as e:
        raise RuntimeError(f"Unexpected error loading image: {e}")

    original_width, original_height = img.size
    original_area = original_width * original_height

    if max(original_width, original_height) > MAX_ANALYSIS_SIZE:
        scale_factor = MAX_ANALYSIS_SIZE / float(max(original_width, original_height))
        resized_width = int(original_width * scale_factor)
        resized_height = int(original_height * scale_factor)
        resized_img = img.resize(
            (resized_width, resized_height), Image.Resampling.LANCZOS
        )
    else:
        scale_factor = 1.0
        resized_img = img.copy()

    try:
        sc = smartcrop.SmartCrop()
        result = sc.crop(resized_img, min(resized_img.size), min(resized_img.size))
        top_crop = result["top_crop"]

        scale_w = original_width / resized_img.width
        scale_h = original_height / resized_img.height
        x = int(top_crop["x"] * scale_w)
        y = int(top_crop["y"] * scale_h)
        w = int(top_crop["width"] * scale_w)
        h = int(top_crop["height"] * scale_h)

        # ! Validate crop box
        if (
            w <= 0
            or h <= 0
            or x < 0
            or y < 0
            or (x + w) > original_width
            or (y + h) > original_height
        ):
            raise ValueError("SmartCrop returned invalid crop box.")

    except Exception:
        # * Fallback to center square crop
        size = min(original_width, original_height)
        left = (original_width - size) // 2
        top = (original_height - size) // 2
        cropped = img.crop((left, top, left + size, top + size))
        if output_size:
            cropped = cropped.resize(
                (output_size, output_size), Image.Resampling.LANCZOS
            )
        return pad_to_square_with_blur(cropped)

    x = int(top_crop["x"] / scale_factor)
    y = int(top_crop["y"] / scale_factor)
    w = int(top_crop["width"] / scale_factor)
    h = int(top_crop["height"] / scale_factor)

    # * Define crop size
    crop_area = w * h
    area_ratio = crop_area / original_area
    if area_ratio < zoom_threshold:
        desired_crop_size = int((zoom_threshold * original_area) ** 0.5)
    else:
        desired_crop_size = max(w, h)

    # * Recenter crop
    center_x = x + w // 2
    center_y = y + h // 2
    half_size = desired_crop_size // 2

    left = max(0, center_x - half_size)
    top = max(0, center_y - half_size)
    right = min(original_width, left + desired_crop_size)
    bottom = min(original_height, top + desired_crop_size)

    # * Adjust if clipped
    left = max(0, right - desired_crop_size)
    top = max(0, bottom - desired_crop_size)

    cropped = img.crop((left, top, right, bottom))
    pad_cropped = pad_to_square_with_blur(cropped)

    if output_size:
        pad_width, pad_height = pad_cropped.size
        if pad_width < output_size or pad_height < output_size:
            pad_cropped = pad_cropped.resize((output_size, output_size), Image.Resampling.LANCZOS)

    return pad_cropped