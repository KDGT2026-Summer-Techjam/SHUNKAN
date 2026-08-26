from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920
MAX_SOURCE_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}


def process_uploaded_image(uploaded_file):
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValidationError("写真は1枚10MB以下にしてください。")

    try:
        image = Image.open(uploaded_file)
        image_format = image.format
        if image_format not in ALLOWED_FORMATS:
            raise ValidationError("写真はJPEG、PNG、WebP、GIF形式にしてください。")
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValidationError("画像の縦横サイズが大きすぎます。")

        output = BytesIO()
        if image_format == "GIF" and getattr(image, "is_animated", False):
            _save_animated_gif(image, output)
        else:
            _save_static_image(image, image_format, output)
    except ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
    ) as error:
        raise ValidationError("画像ファイルを読み取れませんでした。") from error
    finally:
        uploaded_file.seek(0)

    stem = Path(uploaded_file.name).stem or "photo"
    filename = f"{stem}{FORMAT_EXTENSIONS[image_format]}"
    return ContentFile(output.getvalue(), name=filename)


def _save_static_image(image, image_format, output):
    image = ImageOps.exif_transpose(image)
    image.thumbnail(
        (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
        Image.Resampling.LANCZOS,
    )

    if image_format == "JPEG":
        image.convert("RGB").save(
            output,
            format="JPEG",
            quality=85,
            optimize=True,
            progressive=True,
        )
    elif image_format == "PNG":
        image.save(output, format="PNG", optimize=True)
    elif image_format == "WEBP":
        image.save(output, format="WEBP", quality=82, method=6)
    else:
        image.save(output, format="GIF", optimize=True)


def _save_animated_gif(image, output):
    frames = []
    durations = []
    disposals = []

    for frame in ImageSequence.Iterator(image):
        resized_frame = frame.convert("RGBA")
        resized_frame.thumbnail(
            (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        frames.append(resized_frame.convert("P", palette=Image.Palette.ADAPTIVE))
        durations.append(frame.info.get("duration", image.info.get("duration", 100)))
        disposals.append(frame.info.get("disposal", image.info.get("disposal", 2)))

    if not frames:
        raise ValidationError("GIF画像に表示できるフレームがありません。")

    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        disposal=disposals,
        loop=image.info.get("loop", 0),
        optimize=True,
    )
