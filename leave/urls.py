from django.urls import path
from . import views

app_name = "leave"

urlpatterns = [
    path("apply/", views.apply_leave, name="apply_leave"),
    path("company/", views.company_leaves, name="company_leaves"),
    path("company/<int:pk>/", views.leave_detail, name="leave_detail"),
]
