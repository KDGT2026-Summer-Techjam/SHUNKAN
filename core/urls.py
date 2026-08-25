from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("rooms/", views.rooms, name="rooms"),
    path("rooms/active/", views.room_active, name="room_active"),
    path("rooms/ended/", views.room_ended, name="room_ended"),
    path("moments/new/", views.moments_new, name="moments_new"),
    path("tasks/", views.tasks, name="tasks"),
    path("album/", views.album, name="album"),
]
