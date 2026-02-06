from django.urls import path
from . import views

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-reset/", views.password_reset_request, name="password_reset"),
    path("password-reset/verify/<uuid:token>/", views.password_reset_verify, name="password_reset_verify"),
    path("me/", views.me_dashboard, name="me_dashboard"),
    # Backward-compatible alias (some users navigate to /manager/)
    path("manager/", views.manager_alias, name="manager_alias"),
    path("me/profile/", views.edit_profile, name="edit_profile"),
    # Custom (portal UI) admin panel for staff
    path("admin-panel/", views.admin_panel, name="admin_panel"),
    path("admin-panel/users/new/", views.admin_create_employee, name="admin_create_employee"),
    path("admin-panel/users/<int:user_id>/toggle-active/", views.admin_toggle_user_active, name="admin_toggle_user_active"),
    path("admin-panel/users/<int:user_id>/delete/", views.admin_delete_user, name="admin_delete_user"),
]
