from django.urls import path

from . import views

urlpatterns = [
    path("studies", views.study_list, name="study-list"),
    path("studies/import/", views.study_import, name="study-import"),
    path('studies/<str:orthanc_id>/attach-report/', views.attach_report_to_study),
    path('studies/<str:orthanc_id>/attach-existing-report/', views.attach_existing_report),
    path("reports/unassigned/", views.unassigned_reports_list, name="unassigned-reports-list"),

    path("dashboard/", views.dashboard_view, name="dashboard-view")
]
