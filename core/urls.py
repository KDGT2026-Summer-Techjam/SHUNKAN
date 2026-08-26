from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/signup/", views.signup, name="signup"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("rooms/", views.rooms, name="rooms"),
    path("rooms/<int:room_id>/", views.room_detail, name="room_detail"),
    path("rooms/<int:room_id>/update/", views.room_update, name="room_update"),
    path("rooms/<int:room_id>/delete/", views.room_delete, name="room_delete"),
    path("rooms/<int:room_id>/tasks/", views.room_tasks, name="room_tasks"),
    path("rooms/<int:room_id>/tasks/", views.room_tasks, name="task_list"),
    path(
        "rooms/<int:room_id>/categories/",
        views.room_categories,
        name="room_categories",
    ),
    path(
        "rooms/<int:room_id>/categories/<int:category_id>/update/",
        views.category_update,
        name="category_update",
    ),
    path(
        "rooms/<int:room_id>/categories/<int:category_id>/delete/",
        views.category_delete,
        name="category_delete",
    ),
    path(
        "rooms/<int:room_id>/tasks/<int:task_id>/update/",
        views.task_update,
        name="task_update",
    ),
    path(
        "rooms/<int:room_id>/tasks/<int:task_id>/delete/",
        views.task_delete,
        name="task_delete",
    ),
    path("rooms/<int:room_id>/moments/", views.moment_list, name="moment_list"),
    path(
        "rooms/<int:room_id>/moments/new/",
        views.room_moments_new,
        name="room_moments_new",
    ),
    path(
        "rooms/<int:room_id>/moments/<int:moment_id>/update/",
        views.moment_update,
        name="moment_update",
    ),
    path(
        "rooms/<int:room_id>/moments/<int:moment_id>/delete/",
        views.moment_delete,
        name="moment_delete",
    ),
    path("rooms/<int:room_id>/photos/", views.photo_list, name="photo_list"),
    path(
        "rooms/<int:room_id>/photos/<int:photo_id>/update/",
        views.photo_update,
        name="photo_update",
    ),
    path(
        "rooms/<int:room_id>/photos/<int:photo_id>/delete/",
        views.photo_delete,
        name="photo_delete",
    ),
    path("rooms/<int:room_id>/album/", views.room_album, name="room_album"),
    path("rooms/active/", views.room_active, name="room_active"),
    path("rooms/ended/", views.room_ended, name="room_ended"),
    path("moments/new/", views.moments_new, name="moments_new"),
    path("tasks/", views.tasks, name="tasks"),
    path("album/", views.album, name="album"),
]
