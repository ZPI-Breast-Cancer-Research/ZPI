from django.urls import path
from . import views

urlpatterns = [
    path("auth/signin/", views.log_in, name="sign-in"),
    path("auth/set-password/", views.set_first_password, name="set-password"),
    path("auth/signout/", views.sign_out, name="sign-out"),
    path("auth/change-password/", views.change_password, name="change-password"),

    path("profile/", views.get_profile, name="get-profile"),
    path("users/", views.manage_users, name="manage-users"),
    path("users/<str:user_id>/", views.update_user, name="update-user"),
    path("users/<str:user_id>/block/", views.set_blocked, name="set-blocked"),
    path("users/<str:user_id>/reset-password/", views.reset_password, name="reset-password"),
]