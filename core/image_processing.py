from datetime import datetime
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920
MAX_SOURCE_PIXELS = 40_000_000
MAX_GIF_FRAMES = 200
MAX_GIF_TOTAL_PIXELS = 100_000_000
MAX_GIF_TOTAL_DURATION_MS = 300_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}

# Pillowのgetexif()はタグIDを整数で返す。
# 0x9003: DateTimeOriginal、0x9004: DateTimeDigitized
EXIF_DATETIME_TAGS = (0x9003, 0x9004)
EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def read_captured_at(uploaded_file):
    """EXIFの撮影日時を読む。位置情報・端末情報は一切読まない。

    読み取れない場合はNoneを返す。JPEG以外やEXIFが無い画像でも安全にNoneを返す。
    """
    try:
        with Image.open(uploaded_file) as image:
            exif = image.getexif()
            if not exif:
                return None
            for tag in EXIF_DATETIME_TAGS:
                raw = exif.get(tag)
                if not raw:
                    continue
                try:
                    naive = datetime.strptime(str(raw), EXIF_DATETIME_FORMAT)
                    return timezone.make_aware(
                        naive,
                        timezone.get_current_timezone(),
                    )
                except ValueError:
                    continue
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError):
        return None
    finally:
        uploaded_file.seek(0)
    return None


def process_uploaded_image(uploaded_file):
    try:
        if uploaded_file.size > MAX_UPLOAD_SIZE:
            raise ValidationError("写真は1枚10MB以下にしてください。")

        with Image.open(uploaded_file) as image:
            image_format = image.format
            if image_format not in ALLOWED_FORMATS:
                raise ValidationError("この画像形式には対応していません。別の画像を選んでください。")
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
    total_pixels = 0
    total_duration = 0

    try:
        for frame_number, frame in enumerate(ImageSequence.Iterator(image), start=1):
            if frame_number > MAX_GIF_FRAMES:
                raise ValidationError(
                    f"GIFアニメーションは{MAX_GIF_FRAMES}フレーム以下にしてください。"
                )

            total_pixels += frame.width * frame.height
            if total_pixels > MAX_GIF_TOTAL_PIXELS:
                raise ValidationError(
                    "GIFアニメーションの合計画素数が大きすぎます。"
                )

            duration = frame.info.get("duration", image.info.get("duration", 100))
            total_duration += duration
            if total_duration > MAX_GIF_TOTAL_DURATION_MS:
                raise ValidationError(
                    "GIFアニメーションの再生時間は合計300秒以下にしてください。"
                )

            resized_frame = frame.convert("RGBA")
            resized_frame.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            frames.append(
                resized_frame.convert("P", palette=Image.Palette.ADAPTIVE)
            )
            resized_frame.close()
            durations.append(duration)
            disposals.append(
                frame.info.get(
                    "disposal",
                    getattr(frame, "disposal_method", image.info.get("disposal", 2)),
                )
            )

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
    finally:
        for frame in frames:
            frame.close()
