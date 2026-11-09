from django.urls import path
from .views import (
    review_queue,
    review_case_detail,
    approve_case,
    approve_mask,
    reopen_case,
    unapprove_mask,
    approve_form,
    unapprove_form,
    review_overview
)

urlpatterns = [
    path('queue/', review_queue, name='review-queue'),
    path('cases/<str:study_id>/', review_case_detail, name='review-case-detail'),
    path('cases/<str:study_id>/approve/', approve_case, name='approve-case'),
    path('cases/<str:study_id>/approve-mask/', approve_mask, name='approve-mask'),
    path('cases/<str:study_id>/reopen/', reopen_case, name='reopen-case'),
    path('cases/<str:study_id>/unapprove-mask/', unapprove_mask, name='unapprove-mask'),
    path('cases/<str:study_id>/approve-form/', approve_form, name='approve-form'),
    path('cases/<str:study_id>/unapprove-form/', unapprove_form, name='unapprove-form'),
    path('cases/<str:study_id>/review-overview/', review_overview, name='review-overview'),
]
