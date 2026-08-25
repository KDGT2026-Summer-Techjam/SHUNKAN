import os
from datetime import datetime, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Category, MomentLog, Room, Task


class Command(BaseCommand):
    help = "開発用のデモデータを投入します"

    def handle(self, *args, **options):
        password = os.environ.get("DEMO_USER_PASSWORD")
        if not password and settings.DEBUG:
            password = "demo"
        if not password:
            raise CommandError(
                "DEBUG=False では DEMO_USER_PASSWORD を設定してから seed_demo を実行してください。"
            )

        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="demo",
            defaults={
                "email": "demo@example.com",
            },
        )
        user.set_password(password)
        user.save(update_fields=["password"])

        summer_room, _ = Room.objects.update_or_create(
            owner=user,
            name="2026 夏",
            defaults={
                "starts_at": timezone.make_aware(
                    datetime(2026, 7, 1, 0, 0, 0)
                ),
                "ends_at": timezone.make_aware(
                    datetime.combine(
                        datetime(2026, 8, 31).date(),
                        time(23, 59, 59),
                    )
                ),
                "reflection_deadline_at": None,
                "is_archived": False,
            },
        )

        techjam_room, _ = Room.objects.update_or_create(
            owner=user,
            name="TechJam 2026",
            defaults={
                "starts_at": timezone.make_aware(
                    datetime(2026, 8, 21, 0, 0, 0)
                ),
                "ends_at": timezone.make_aware(
                    datetime(2026, 8, 28, 18, 0, 0)
                ),
                "reflection_deadline_at": None,
                "is_archived": False,
            },
        )

        summer_category, _ = Category.objects.update_or_create(
            room=summer_room,
            name="おでかけ",
            defaults={
                "color": "#FFB703",
                "sort_order": 1,
            },
        )

        food_category, _ = Category.objects.update_or_create(
            room=summer_room,
            name="グルメ",
            defaults={
                "color": "#FB8500",
                "sort_order": 2,
            },
        )

        tech_category, _ = Category.objects.update_or_create(
            room=techjam_room,
            name="開発",
            defaults={
                "color": "#219EBC",
                "sort_order": 1,
            },
        )

        task1, _ = Task.objects.update_or_create(
            room=summer_room,
            title="花火を見る",
            defaults={
                "category": summer_category,
                "due_date": datetime(2026, 8, 31).date(),
                "is_completed": False,
                "completed_at": None,
            },
        )

        task2, _ = Task.objects.update_or_create(
            room=summer_room,
            title="夏のグルメを食べる",
            defaults={
                "category": food_category,
                "due_date": datetime(2026, 8, 30).date(),
                "is_completed": True,
                "completed_at": timezone.make_aware(
                    datetime(2026, 8, 20, 19, 0, 0)
                ),
            },
        )

        task3, _ = Task.objects.update_or_create(
            room=techjam_room,
            title="TechJamの開発を進める",
            defaults={
                "category": tech_category,
                "due_date": datetime(2026, 8, 28).date(),
                "is_completed": False,
                "completed_at": None,
            },
        )

        MomentLog.objects.update_or_create(
            room=summer_room,
            body="みんなで花火を見た！",
            defaults={
                "task": task1,
                "category": summer_category,
                "occurred_at": timezone.make_aware(
                    datetime(2026, 8, 20, 20, 0, 0)
                ),
                "entry_type": MomentLog.EntryType.MOMENT,
            },
        )

        MomentLog.objects.update_or_create(
            room=techjam_room,
            body="TechJamの開発を進めた。",
            defaults={
                "task": task3,
                "category": tech_category,
                "occurred_at": timezone.make_aware(
                    datetime(2026, 8, 21, 14, 0, 0)
                ),
                "entry_type": MomentLog.EntryType.MOMENT,
            },
        )

        self.stdout.write(
            self.style.SUCCESS("デモデータを投入しました。")
        )