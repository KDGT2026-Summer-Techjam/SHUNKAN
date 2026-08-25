from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def home(request):
    return redirect("login")


@login_required
def rooms(request):
    return render(request, "core/rooms.html")


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
