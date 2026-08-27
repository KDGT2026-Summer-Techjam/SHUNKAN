from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Photo


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
