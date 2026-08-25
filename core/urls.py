from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/signup/", views.signup, name="signup"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("rooms/", views.rooms, name="rooms"),
    path("rooms/active/", views.room_active, name="room_active"),
    path("rooms/ended/", views.room_ended, name="room_ended"),
    path("moments/new/", views.moments_new, name="moments_new"),
    path("tasks/", views.tasks, name="tasks"),
    path("album/", views.album, name="album"),
]
