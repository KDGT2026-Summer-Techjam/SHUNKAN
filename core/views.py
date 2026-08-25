from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .access import (
    get_owned_moment_log,
    get_owned_photo,
    get_owned_room,
    get_owned_task,
    owned_moment_logs,
    owned_photos,
    owned_rooms,
    owned_tasks,
)
from .forms import MomentLogUpdateForm, PhotoUpdateForm, RoomForm, TaskUpdateForm


def home(request):
    return redirect("login")


def signup(request):
    if request.user.is_authenticated:
        return redirect("rooms")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("rooms")
    else:
        form = UserCreationForm()
    return render(request, "core/signup.html", {"form": form})


@login_required
def rooms(request):
    if request.method == "POST":
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.owner = request.user
            room.save()
            return redirect("rooms")
    else:
        form = RoomForm()

    return render(
        request,
        "core/rooms.html",
        {
            "form": form,
            "rooms": owned_rooms(request.user).order_by("ends_at"),
            "now": timezone.now(),
        },
    )


@login_required
def room_detail(request, room_id):
    room = get_owned_room(request.user, room_id)
    return render(
        request,
        "core/room_detail.html",
        {"room": room, "now": timezone.now()},
    )


@login_required
def room_active(request):
    return render(request, "core/room_active.html")


@login_required
def room_ended(request):
    return render(request, "core/room_ended.html")


@login_required
def moments_new(request):
    return render(request, "core/moments_new.html")


@login_required
def tasks(request):
    return render(request, "core/tasks.html")


@login_required
def album(request):
    return render(request, "core/album.html")


@login_required
@require_http_methods(["GET", "POST"])
def room_update(request, room_id):
    room = get_owned_room(request.user, room_id)
    form = RoomForm(request.POST or None, instance=room)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("room_detail", room_id=room.pk)
    return render(request, "core/owned_form.html", {"form": form, "heading": "Roomを更新"})


@login_required
@require_POST
def room_delete(request, room_id):
    room = get_owned_room(request.user, room_id)
    room.delete()
    return redirect("rooms")


@login_required
def task_list(request, room_id):
    task_qs = owned_tasks(request.user, room_id)
    return render(
        request,
        "core/owned_list.html",
        {"heading": "タスク", "items": [task.title for task in task_qs]},
    )


@login_required
@require_http_methods(["GET", "POST"])
def task_update(request, room_id, task_id):
    task = get_owned_task(request.user, room_id, task_id)
    form = TaskUpdateForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("task_list", room_id=room_id)
    return render(request, "core/owned_form.html", {"form": form, "heading": "タスクを更新"})


@login_required
@require_POST
def task_delete(request, room_id, task_id):
    task = get_owned_task(request.user, room_id, task_id)
    task.delete()
    return redirect("task_list", room_id=room_id)


@login_required
def moment_list(request, room_id):
    moment_qs = owned_moment_logs(request.user, room_id)
    return render(
        request,
        "core/owned_list.html",
        {"heading": "SHUNKAN-log", "items": [moment.body for moment in moment_qs]},
    )


@login_required
@require_http_methods(["GET", "POST"])
def moment_update(request, room_id, moment_id):
    moment_log = get_owned_moment_log(request.user, room_id, moment_id)
    form = MomentLogUpdateForm(request.POST or None, instance=moment_log)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("moment_list", room_id=room_id)
    return render(request, "core/owned_form.html", {"form": form, "heading": "記録を更新"})


@login_required
@require_POST
def moment_delete(request, room_id, moment_id):
    moment_log = get_owned_moment_log(request.user, room_id, moment_id)
    moment_log.delete()
    return redirect("moment_list", room_id=room_id)


@login_required
def photo_list(request, room_id):
    photo_qs = owned_photos(request.user, room_id)
    return render(
        request,
        "core/owned_list.html",
        {
            "heading": "写真",
            "items": [photo.caption or photo.image.name for photo in photo_qs],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def photo_update(request, room_id, photo_id):
    photo = get_owned_photo(request.user, room_id, photo_id)
    form = PhotoUpdateForm(request.POST or None, instance=photo)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("photo_list", room_id=room_id)
    return render(request, "core/owned_form.html", {"form": form, "heading": "写真を更新"})


@login_required
@require_POST
def photo_delete(request, room_id, photo_id):
    photo = get_owned_photo(request.user, room_id, photo_id)
    photo.delete()
    return redirect("photo_list", room_id=room_id)
