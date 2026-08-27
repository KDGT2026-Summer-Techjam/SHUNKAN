from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .access import (
    get_owned_category,
    get_owned_moment_log,
    get_owned_photo,
    get_owned_room,
    get_owned_task,
    owned_categories,
    owned_moment_logs,
    owned_photos,
)
from .forms import (
    CategoryForm,
    MomentLogForm,
    MomentLogUpdateForm,
    PhotoUpdateForm,
    RoomForm,
    TaskForm,
    TaskUpdateForm,
    _task_label,
)
from .image_processing import process_uploaded_image
from .models import Category, MomentLog, Photo, Room, Task
from .room_state import log_post_permission, require_active_room, room_is_active


def home(request):
    return redirect("login")


def signup(request):
    form: UserCreationForm
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
            return redirect("room_detail", room_id=room.pk)
    else:
        form = RoomForm()

    now = timezone.now()
    user_rooms = list(
        Room.objects.filter(owner=request.user)
        .prefetch_related("tasks")
        .order_by("ends_at")
    )
    for room in user_rooms:
        room.task_count = len(room.tasks.all())
        room.completed_count = sum(task.is_completed for task in room.tasks.all())
        room.progress_percent = (
            round(room.completed_count / room.task_count * 100)
            if room.task_count
            else 0
        )
        if room.is_archived or room.ends_at <= now:
            room.ui_status = "終了済み"
        elif room.starts_at > now:
            room.ui_status = "開催前"
        else:
            room.ui_status = "開催中"

    active_rooms = [room for room in user_rooms if room.ui_status == "開催中"]
    upcoming_rooms = [room for room in user_rooms if room.ui_status == "開催前"]
    ended_rooms = [room for room in user_rooms if room.ui_status == "終了済み"]

    return render(
        request,
        "core/rooms.html",
        {
            "form": form,
            "rooms": user_rooms,
            "active_rooms": active_rooms,
            "upcoming_rooms": upcoming_rooms,
            "ended_rooms": ended_rooms,
            "now": now,
            "active_nav": "rooms",
        },
    )


def room_display_context(room, *, active_nav):
    now = timezone.now()
    task_count = room.tasks.count()
    completed_count = room.tasks.filter(is_completed=True).count()
    if room.is_archived or room.ends_at <= now:
        room_status = "終了済み"
    elif room.starts_at > now:
        room_status = "開催前"
    else:
        room_status = "開催中"
    active = room_is_active(room, now=now)
    return {
        "room": room,
        "now": now,
        "room_status": room_status,
        "room_is_active": active,
        "room_is_ended": room.ends_at <= now,
        "task_count": task_count,
        "completed_count": completed_count,
        "progress_percent": (
            round(completed_count / task_count * 100) if task_count else 0
        ),
        "active_nav": active_nav,
    }


@login_required
def room_detail(request, room_id):
    room = get_owned_room(request.user, room_id)
    context = room_display_context(room, active_nav="room")
    context.update(
        {
            "next_task": room.tasks.filter(is_completed=False)
            .order_by("due_date", "created_at")
            .first(),
            "latest_moment": room.moment_logs.order_by(
                "-occurred_at", "-created_at"
            ).first(),
        }
    )
    return render(request, "core/room_detail.html", context)


@login_required
def room_tasks(request, room_id):
    room = get_owned_room(request.user, room_id)
    if request.method == "POST":
        require_active_room(room)
        form = TaskForm(request.POST, room=room)
        if form.is_valid():
            task = form.save(commit=False)
            task.room = room
            task.save()
            return redirect("room_tasks", room_id=room.pk)
    else:
        form = TaskForm(room=room)
    context = room_display_context(room, active_nav="tasks")
    context.update(
        {
            "form": form,
            "tasks": room.tasks.select_related("category").order_by(
                "is_completed", "due_date", "created_at"
            ),
        }
    )
    return render(request, "core/tasks.html", context)


@login_required
@require_POST
def task_quick_create(request, room_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    form = TaskForm(request.POST, room=room)
    if form.is_valid():
        task = form.save(commit=False)
        task.room = room
        task.save()
        return JsonResponse({"id": task.pk, "label": _task_label(task)})
    return JsonResponse(
        {"errors": form.errors.as_json()},
        status=400,
    )


@login_required
@require_POST
def category_quick_create(request, room_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    form = CategoryForm(request.POST, room=room)
    if form.is_valid():
        category = form.save(commit=False)
        category.room = room
        category.sort_order = room.categories.count()
        category.save()
        return JsonResponse({"id": category.pk, "label": category.name})
    return JsonResponse(
        {"errors": form.errors.as_json()},
        status=400,
    )


@login_required
def room_moments_new(request, room_id):
    room = get_owned_room(request.user, room_id)
    now = timezone.now()
    moment_permission = log_post_permission(room, MomentLog.EntryType.MOMENT, now=now)
    reflection_permission = log_post_permission(
        room, MomentLog.EntryType.REFLECTION, now=now
    )
    if request.method == "POST":
        requested_entry_type = (
            request.POST.get("entry_type") or MomentLog.EntryType.MOMENT
        )
        permission = (
            reflection_permission
            if requested_entry_type == MomentLog.EntryType.REFLECTION
            else moment_permission
        )
        if not permission.allowed:
            raise PermissionDenied(permission.message)
        form = MomentLogForm(request.POST, room=room, now=now)
        images = request.FILES.getlist("images")
        captions = request.POST.getlist("captions")
        processed_images = []
        complete_task = request.POST.get("complete_task") == "1"
        if images and not settings.ALLOW_PHOTO_UPLOADS:
            form.add_error(
                None,
                "現在、写真アップロードを一時停止しています。写真を外して保存してください。",
            )
        if complete_task and not request.POST.get("task"):
            form.add_error(None, "完了するタスクを選んでください。")
        if complete_task and not images:
            form.add_error(None, "タスクを写真と一緒に完了するには、写真を1枚以上追加してください。")
        if len(images) > 3:
            form.add_error(None, "写真は3枚までです。")
        else:
            for index, image in enumerate(images, start=1):
                try:
                    processed_images.append(process_uploaded_image(image))
                except ValidationError as error:
                    form.add_error(None, f"写真{index}: {error.messages[0]}")
        if form.is_valid():
            with transaction.atomic():
                moment = form.save(commit=False)
                moment.room = room
                completed_at = timezone.now()
                moment.occurred_at = completed_at
                moment.save()
                if complete_task and moment.task is not None:
                    moment.task.is_completed = True
                    moment.task.completed_at = completed_at
                    moment.task.save(update_fields=["is_completed", "completed_at", "updated_at"])
                for index, image in enumerate(processed_images):
                    Photo.objects.create(
                        moment_log=moment,
                        image=image,
                        caption=captions[index] if index < len(captions) else "",
                        sort_order=index,
                    )
            return redirect("room_album", room_id=room.pk)
    else:
        form = MomentLogForm(room=room, now=now)
    context = room_display_context(room, active_nav="capture")
    context.update(
        {
            "form": form,
            "moment_permission": moment_permission,
            "reflection_permission": reflection_permission,
            "can_post_moment": moment_permission.allowed,
            "can_post_reflection": reflection_permission.allowed,
            "photo_uploads_enabled": settings.ALLOW_PHOTO_UPLOADS,
        }
    )
    return render(request, "core/moments_new.html", context)


@login_required
def room_album(request, room_id):
    room = get_owned_room(request.user, room_id)
    moments = (
        MomentLog.objects.filter(room=room)
        .prefetch_related("photos")
        .select_related("task", "category")
        .order_by("-occurred_at", "-created_at")
    )
    context = room_display_context(room, active_nav="album")
    context.update(
        {
            "moments": moments,
            "completed_tasks": room.tasks.filter(is_completed=True)
            .select_related("category")
            .order_by("-completed_at", "-updated_at"),
        }
    )
    return render(request, "core/album.html", context)


@login_required
def profile(request):
    return render(request, "core/profile.html", {"active_nav": "profile"})


@login_required
def room_active(request):
    return redirect("rooms")

    recent_logs = (
        MomentLog.objects
        .filter(room=room)
        .order_by("-occurred_at", "-id")[:1]
    )

@login_required
def room_ended(request):
    return redirect("rooms")


@login_required
def tasks(request):
    return redirect("rooms")


@login_required
def moments_new(request):
    return redirect("rooms")

@login_required
def album(request, room_id):
    room = get_object_or_404(Room, pk=room_id, owner=request.user)
    return render(
        request,
        "core/album.html",
        {"room": room, "now": timezone.now()},
    )

@login_required
def album(request):
    return redirect("rooms")


@login_required
def room_categories(request, room_id):
    room = get_owned_room(request.user, room_id)
    if request.method == "POST":
        if not room_display_context(room, active_nav="tasks")["room_is_active"]:
            raise PermissionDenied("開催中のRoomだけカテゴリを追加できます。")
        form = CategoryForm(request.POST, room=room)
        if form.is_valid():
            category = form.save(commit=False)
            category.room = room
            category.sort_order = room.categories.count()
            category.save()
            return redirect("room_categories", room_id=room.pk)
    else:
        form = CategoryForm(room=room)
   ˜ context = room_display_context(room, active_nav="tasks")
    context.update(
        {
            "form": form,
            "categories": room.categories.all(),
        }
    )
    return render(request, "core/categories.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def category_update(request, room_id, category_id):
    category = get_owned_category(request.user, room_id, category_id)
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    form = CategoryForm(request.POST or None, instance=category, room=room)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("room_categories", room_id=room_id)
    context = room_display_context(room, active_nav="tasks")
    context.update(
        {
            "form": form,
            "heading": "カテゴリを更新",
            "form_kind": "category",
        }
    )
    return render(request, "core/owned_form.html", context)


@login_required
@require_POST
def category_delete(request, room_id, category_id):
    category = get_owned_category(request.user, room_id, category_id)
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    category.delete()
    return redirect("room_categories", room_id=room_id)


@login_required
@require_http_methods(["GET", "POST"])
def room_update(request, room_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    form = RoomForm(request.POST or None, instance=room)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("room_detail", room_id=room.pk)
    context = room_display_context(room, active_nav="room")
    context.update(
        {"form": form, "heading": "Roomを更新", "form_kind": "room"}
    )
    return render(request, "core/owned_form.html", context)


@login_required
@require_POST
def room_delete(request, room_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    room.delete()
    return redirect("rooms")


@login_required
@require_http_methods(["GET", "POST"])
def task_update(request, room_id, task_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    task = get_owned_task(request.user, room_id, task_id)
    form = TaskUpdateForm(request.POST or None, instance=task, room=room)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("task_list", room_id=room_id)
    context = room_display_context(room, active_nav="tasks")
    context.update(
        {"form": form, "heading": "タスクを更新", "form_kind": "task"}
    )
    return render(request, "core/owned_form.html", context)


@login_required
@require_POST
def task_delete(request, room_id, task_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    task = get_owned_task(request.user, room_id, task_id)
    task.delete()
    return redirect("task_list", room_id=room_id)


@login_required
@require_POST
def task_toggle(request, room_id, task_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    task = get_owned_task(request.user, room_id, task_id)
    task.is_completed = not task.is_completed
    task.completed_at = timezone.now() if task.is_completed else None
    task.save(update_fields=["is_completed", "completed_at", "updated_at"])
    return redirect("task_list", room_id=room_id)


@login_required
@require_POST
def task_complete(request, room_id, task_id):
    """Persist a task completion before a client-side achievement effect."""
    room = get_owned_room(request.user, room_id)
    task = get_owned_task(request.user, room_id, task_id)
    wants_json = "application/json" in request.headers.get("Accept", "")

    if not room_is_active(room):
        message = "開催中のRoomだけタスクを完了できます。"
        if wants_json:
            return JsonResponse({"error": message}, status=403)
        raise PermissionDenied(message)

    with transaction.atomic():
        task = Task.objects.select_for_update().get(pk=task.pk, room=room)
        if task.is_completed:
            message = "このタスクはすでに完了しています。"
            if wants_json:
                return JsonResponse({"error": message}, status=409)
            return redirect("task_list", room_id=room.pk)

        completed_at = timezone.now()
        task.is_completed = True
        task.completed_at = completed_at
        task.save(update_fields=["is_completed", "completed_at", "updated_at"])

    if wants_json:
        return JsonResponse(
            {
                "task": {
                    "id": task.pk,
                    "title": task.title,
                    "completed_at": completed_at.isoformat(),
                }
            }
        )
    return redirect("task_list", room_id=room.pk)


@login_required
def moment_list(request, room_id):
    room = get_owned_room(request.user, room_id)
    moment_qs = owned_moment_logs(request.user, room_id).prefetch_related("photos")
    context = room_display_context(room, active_nav="album")
    context.update(
        {"heading": "SHUNKAN-log", "items": moment_qs, "item_kind": "moment"}
    )
    return render(request, "core/owned_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def moment_update(request, room_id, moment_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    moment_log = get_owned_moment_log(request.user, room_id, moment_id)
    form = MomentLogUpdateForm(request.POST or None, instance=moment_log)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("moment_list", room_id=room_id)
    context = room_display_context(room, active_nav="album")
    context.update(
        {"form": form, "heading": "SHUNKAN-logを更新", "form_kind": "moment"}
    )
    return render(request, "core/owned_form.html", context)


@login_required
@require_POST
def moment_delete(request, room_id, moment_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    moment_log = get_owned_moment_log(request.user, room_id, moment_id)
    moment_log.delete()
    return redirect("moment_list", room_id=room_id)


@login_required
def photo_list(request, room_id):
    room = get_owned_room(request.user, room_id)
    photo_qs = owned_photos(request.user, room_id).select_related("moment_log")
    context = room_display_context(room, active_nav="album")
    context.update({"heading": "写真", "items": photo_qs, "item_kind": "photo"})
    return render(request, "core/owned_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def photo_update(request, room_id, photo_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    photo = get_owned_photo(request.user, room_id, photo_id)
    form = PhotoUpdateForm(request.POST or None, instance=photo)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("photo_list", room_id=room_id)
    context = room_display_context(room, active_nav="album")
    context.update(
        {"form": form, "heading": "写真のひとことを更新", "form_kind": "photo"}
    )
    return render(request, "core/owned_form.html", context)


@login_required
@require_POST
def photo_delete(request, room_id, photo_id):
    room = get_owned_room(request.user, room_id)
    require_active_room(room)
    photo = get_owned_photo(request.user, room_id, photo_id)
    photo.delete()
    return redirect("photo_list", room_id=room_id)
