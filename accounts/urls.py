from django.urls import path
from .views import LoginView, CreateStaffView, ListStaffView, DeactivateStaffView, ChangePasswordView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('staff/create/', CreateStaffView.as_view(), name='create_staff'),
    path('staff/list/', ListStaffView.as_view(), name='list_staff'),
    path('staff/<int:user_id>/deactivate/', DeactivateStaffView.as_view(), name='deactivate_staff'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
]
