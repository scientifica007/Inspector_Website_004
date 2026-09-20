import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import Guide, InspectionReference, Visit, Assignment, AssignmentStatus
from inspection.services.governance_execution_services import GuideService, AssignmentService


@login_required
def guide_list_view(request):
    if not request.user.is_admin_role:
        raise PermissionDenied("وحدها الإدارة تملك صلاحية إدارة الأدلة.")

    guides = Guide.objects.all().select_related("reference", "created_by").order_by("-created_at")
    shared_references = InspectionReference.objects.filter(is_shared=True)
    return render(request, "inspection/governance/guides_list.html", {"guides": guides, "shared_references": shared_references})


@login_required
def guide_create_view(request):
    if not request.user.is_admin_role:
        raise PermissionDenied("وحدها الإدارة تملك صلاحية إضافة أدلة.")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        reference_id = request.POST.get("reference_id")
        target_node_ids = request.POST.getlist("target_node_ids")

        ref = get_object_or_404(InspectionReference, pk=reference_id)
        try:
            guide = GuideService.create_guide(
                title=title,
                description=description,
                reference=ref,
                created_by=request.user,
                entry_target_node_ids=target_node_ids
            )
            messages.success(request, "تم إنشاء دليل التفتيش بنجاح.")
            return redirect("guide_list")
        except Exception as e:
            messages.error(request, f"فشل إنشاء الدليل: {e}")

    return redirect("guide_list")


@login_required
def assignment_create_view(request, visit_pk):
    if not request.user.is_admin_role:
        raise PermissionDenied("وحدها الإدارة تملك صلاحية إنشاء التكليفات.")

    visit = get_object_or_404(Visit, pk=visit_pk)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        selected_nodes = request.POST.getlist("selected_nodes")

        entries_data = []
        for node_id_str in selected_nodes:
            scope_locked = request.POST.get(f"scope_locked_{node_id_str}") == "true"
            completion_required = request.POST.get(f"completion_required_{node_id_str}") == "true"
            entries_data.append({
                "target_node_id": uuid.UUID(node_id_str),
                "scope_locked": scope_locked,
                "completion_required": completion_required
            })

        try:
            assignment = AssignmentService.create_assignment_draft(
                visit=visit,
                title=title,
                description=description,
                created_by=request.user,
                entries_data=entries_data
            )
            messages.success(request, "تم إنشاء مسودة التكليف بنجاح.")
            return redirect("assignment_detail", pk=assignment.pk)
        except Exception as e:
            messages.error(request, f"خطأ في إنشاء مسودة التكليف: {e}")

    items = visit.items.all().order_by("order", "created_at")
    return render(request, "inspection/governance/assignment_form.html", {"visit": visit, "items": items})


@login_required
def assignment_detail_view(request, pk):
    if not request.user.is_admin_role and not request.user.is_inspector_role:
        raise PermissionDenied()

    assignment = get_object_or_404(Assignment.objects.select_related("visit", "created_by", "revoked_by"), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "issue":
            try:
                AssignmentService.issue_assignment(assignment, request.user)
                messages.success(request, "تم إصدار التكليف الرسمي بنجاح وأصبح ملزماً للزيارة.")
            except Exception as e:
                messages.error(request, f"فشل الإصدار الذري: {e}")
        elif action == "revoke":
            reason = request.POST.get("revocation_reason", "").strip()
            try:
                AssignmentService.revoke_assignment(assignment, request.user, reason)
                messages.warning(request, "تم إلغاء التكليف الرسمي وتسجيل سبب الإلغاء.")
            except Exception as e:
                messages.error(request, f"فشل الإلغاء: {e}")

        return redirect("assignment_detail", pk=pk)

    entries = assignment.entries.all()
    target_items_map = {item.node_id: item for item in assignment.visit.items.all()}

    entries_with_items = []
    for entry in entries:
        entries_with_items.append({
            "entry": entry,
            "item": target_items_map.get(entry.target_node_id)
        })

    context = {
        "assignment": assignment,
        "entries_with_items": entries_with_items
    }
    return render(request, "inspection/governance/assignment_detail.html", context)
