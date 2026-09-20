from django.urls import path
from django.contrib.auth.views import LogoutView
from inspection.views.auth_institution_views import (
    CustomLoginView,
    dashboard_view,
    institution_list_view,
    institution_create_view,
    institution_edit_view
)
from inspection.views.reference_views import (
    reference_list_view,
    reference_detail_view,
    reference_create_view,
    reference_submit_generalization_view,
    governance_submissions_list_view,
    governance_submission_review_view
)
from inspection.views.visit_views import (
    visit_list_view,
    visit_create_view,
    visit_detail_view,
    visit_toggle_item_scope_view,
    visit_exclude_item_view,
    visit_restore_item_view,
    visit_add_local_item_view,
    visit_record_response_view,
    visit_apply_guide_view,
    visit_complete_view,
    visit_delete_draft_view,
    visit_export_json_view
)
from inspection.views.governance_views import (
    guide_list_view,
    guide_create_view,
    assignment_create_view,
    assignment_detail_view
)

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", dashboard_view, name="dashboard"),

    path("institutions/", institution_list_view, name="institution_list"),
    path("institutions/new/", institution_create_view, name="institution_create"),
    path("institutions/<int:pk>/edit/", institution_edit_view, name="institution_edit"),

    path("references/", reference_list_view, name="reference_list"),
    path("references/new/", reference_create_view, name="reference_create"),
    path("references/<int:pk>/", reference_detail_view, name="reference_detail"),
    path("references/<int:pk>/submit-generalization/", reference_submit_generalization_view, name="reference_submit_generalization"),

    path("governance/submissions/", governance_submissions_list_view, name="governance_submissions"),
    path("governance/submissions/<int:pk>/", governance_submission_review_view, name="governance_submission_detail"),

    path("guides/", guide_list_view, name="guide_list"),
    path("guides/new/", guide_create_view, name="guide_create"),

    path("visits/", visit_list_view, name="visit_list"),
    path("visits/new/", visit_create_view, name="visit_create"),
    path("visits/<int:pk>/", visit_detail_view, name="visit_detail"),
    path("visits/<int:pk>/items/<uuid:item_node_id>/toggle-scope/", visit_toggle_item_scope_view, name="visit_toggle_item_scope"),
    path("visits/<int:pk>/items/<uuid:item_node_id>/exclude/", visit_exclude_item_view, name="visit_exclude_item"),
    path("visits/<int:pk>/items/<uuid:item_node_id>/restore/", visit_restore_item_view, name="visit_restore_item"),
    path("visits/<int:pk>/add-local/", visit_add_local_item_view, name="visit_add_local_item"),
    path("visits/<int:pk>/items/<uuid:item_node_id>/record-response/", visit_record_response_view, name="visit_record_response"),
    path("visits/<int:pk>/apply-guide/", visit_apply_guide_view, name="visit_apply_guide"),
    path("visits/<int:pk>/complete/", visit_complete_view, name="visit_complete"),
    path("visits/<int:pk>/delete-draft/", visit_delete_draft_view, name="visit_delete_draft"),
    path("visits/<int:pk>/export-json/", visit_export_json_view, name="visit_export_json"),

    path("visits/<int:visit_pk>/assignments/new/", assignment_create_view, name="assignment_create"),
    path("assignments/<int:pk>/", assignment_detail_view, name="assignment_detail"),
]
