from datetime import datetime

from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import TaskForm
from .models import Task

SUMMER_END = timezone.make_aware(datetime(2026, 8, 31, 23, 59, 59))


def remaining_until_summer_end(now=None):
    now = now or timezone.localtime()
    remaining = SUMMER_END - now
    total_seconds = max(int(remaining.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return {
        "deadline": SUMMER_END,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "seconds": seconds,
        "total_seconds": total_seconds,
        "is_over": remaining.total_seconds() <= 0,
    }


def home(request):
    return render(request, "core/home.html", remaining_until_summer_end())


def task(request):
    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("task")
    else:
        form = TaskForm()

    tasks = Task.objects.all()
    return render(request, "core/task.html", {"form": form, "tasks": tasks})
