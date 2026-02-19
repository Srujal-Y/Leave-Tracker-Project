from __future__ import annotations

from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-reset/", views.password_reset_request, name="password_reset_request"),
    path("password-reset/verify/<uuid:token>/", views.password_reset_verify, name="password_reset_verify"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("admin-panel/", views.admin_panel, name="admin_panel"),
    path("admin-panel/create/", views.admin_create_user, name="admin_create_user"),
    path("admin-panel/<int:user_id>/toggle/", views.admin_toggle_user, name="admin_toggle_user"),
    path("admin-panel/<int:user_id>/delete/", views.admin_delete_user, name="admin_delete_user"),
]
