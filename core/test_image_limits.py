from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, ImageSequence

from core.image_processing import process_uploaded_image


def make_animated_gif(*, frame_count=3, size=(4, 4), durations=None, loop=2):
    frames = [
        Image.new("RGB", size, (index * 60, 20, 255 - index * 60))
        for index in range(frame_count)
    ]
    output = BytesIO()
    durations = durations or [100] * frame_count
    try:
        frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            disposal=[2] * frame_count,
            loop=loop,
        )
    finally:
        for frame in frames:
            frame.close()

    return SimpleUploadedFile(
        "animation.gif",
        output.getvalue(),
        content_type="image/gif",
    )


class GifResourceLimitTests(SimpleTestCase):
    def test_rejects_gif_over_frame_limit_before_processing_more_frames(self):
        uploaded_file = make_animated_gif(frame_count=3)

        with patch("core.image_processing.MAX_GIF_FRAMES", 2):
            with self.assertRaisesMessage(ValidationError, "2フレーム以下"):
                process_uploaded_image(uploaded_file)

        self.assertEqual(uploaded_file.tell(), 0)

    def test_rejects_gif_over_aggregate_decoded_pixel_limit(self):
        uploaded_file = make_animated_gif(frame_count=2, size=(4, 4))

        with patch("core.image_processing.MAX_GIF_TOTAL_PIXELS", 31):
            with self.assertRaisesMessage(ValidationError, "合計画素数"):
                process_uploaded_image(uploaded_file)

        self.assertEqual(uploaded_file.tell(), 0)

    def test_rejects_gif_over_total_duration_limit(self):
        uploaded_file = make_animated_gif(frame_count=2, durations=[100, 100])

        with patch("core.image_processing.MAX_GIF_TOTAL_DURATION_MS", 199):
            with self.assertRaisesMessage(ValidationError, "再生時間"):
                process_uploaded_image(uploaded_file)

        self.assertEqual(uploaded_file.tell(), 0)

    def test_preserves_valid_animation_metadata(self):
        uploaded_file = make_animated_gif(durations=[80, 120, 160], loop=3)

        processed = process_uploaded_image(uploaded_file)

        self.assertEqual(uploaded_file.tell(), 0)
        with Image.open(processed) as image:
            self.assertTrue(image.is_animated)
            self.assertEqual(image.n_frames, 3)
            self.assertEqual(image.info["loop"], 3)
            self.assertEqual(
                [frame.info["duration"] for frame in ImageSequence.Iterator(image)],
                [80, 120, 160],
            )
            self.assertEqual(
                [
                    frame.disposal_method
                    for frame in ImageSequence.Iterator(image)
                ],
                [2, 2, 2],
            )
