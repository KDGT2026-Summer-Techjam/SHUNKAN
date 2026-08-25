from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


def home(request):
    return redirect("login")


def signup(request):
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
