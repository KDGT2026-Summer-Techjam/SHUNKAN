from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import RoomForm
from .models import Room


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
            "rooms": Room.objects.filter(owner=request.user).order_by("ends_at"),
            "now": timezone.now(),
        },
    )


@login_required
def room_detail(request, room_id):
    room = get_object_or_404(Room, pk=room_id, owner=request.user)
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
