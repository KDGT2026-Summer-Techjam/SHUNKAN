from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Category, DEFAULT_CATEGORY_NAMES, Photo, Room


@receiver(post_save, sender=Room)
def create_default_categories_for_room(sender, instance, created, using, **kwargs):
    if not created:
        return

    Category.objects.using(using).bulk_create(
        [
            Category(room=instance, name=name, sort_order=index)
            for index, name in enumerate(DEFAULT_CATEGORY_NAMES)
        ]
    )


@receiver(post_delete, sender=Photo)
def delete_photo_image_after_commit(sender, instance, using, **kwargs):
    name = instance.image.name
    if not name:
        return

    storage = instance.image.storage
    transaction.on_commit(
        lambda storage=storage, name=name: storage.delete(name),
        using=using,
    )
