from django.shortcuts import get_object_or_404

from .models import Category, MomentLog, Photo, Room, Task


def owned_rooms(user):
    return Room.objects.filter(owner=user)


def get_owned_room(user, room_id):
    return get_object_or_404(Room, pk=room_id, owner=user)


def owned_tasks(user, room_id):
    room = get_owned_room(user, room_id)
    return Task.objects.filter(room=room)


def get_owned_task(user, room_id, task_id):
    room = get_owned_room(user, room_id)
    return get_object_or_404(Task, pk=task_id, room=room)


def owned_moment_logs(user, room_id):
    room = get_owned_room(user, room_id)
    return MomentLog.objects.filter(room=room)


def get_owned_moment_log(user, room_id, moment_id):
    room = get_owned_room(user, room_id)
    return get_object_or_404(MomentLog, pk=moment_id, room=room)


def owned_photos(user, room_id):
    room = get_owned_room(user, room_id)
    return Photo.objects.filter(moment_log__room=room)


def get_owned_photo(user, room_id, photo_id):
    room = get_owned_room(user, room_id)
    return get_object_or_404(Photo, pk=photo_id, moment_log__room=room)


def owned_categories(user, room_id):
    room = get_owned_room(user, room_id)
    return Category.objects.filter(room=room)


def get_owned_category(user, room_id, category_id):
    room = get_owned_room(user, room_id)
    return get_object_or_404(Category, pk=category_id, room=room)
