from django.db import migrations


DEFAULT_CATEGORY_NAMES = (
    "食べた",
    "聴いた",
    "観た",
    "感じた",
    "会った",
    "作った",
    "学んだ",
    "その他",
)


def add_default_categories(apps, schema_editor):
    Room = apps.get_model("core", "Room")
    Category = apps.get_model("core", "Category")

    for room in Room.objects.all().iterator():
        existing_names = {
            name.lstrip("#").strip()
            for name in Category.objects.filter(room_id=room.pk).values_list("name", flat=True)
        }
        Category.objects.bulk_create(
            [
                Category(room_id=room.pk, name=name, sort_order=index)
                for index, name in enumerate(DEFAULT_CATEGORY_NAMES)
                if name not in existing_names
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0010_reflection_relational_integrity")]

    operations = [migrations.RunPython(add_default_categories, migrations.RunPython.noop)]
