from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("moments/new/", views.moments_new, name="moments_new"),
    path("tasks/", views.tasks, name="tasks"),
    path("album/", views.album, name="album"),
]
