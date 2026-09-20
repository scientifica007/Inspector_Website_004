import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import InspectionReference, PrivateReferenceSubmission, NodeType
from inspection.services.reference_service import ReferenceService


@login_required
def reference_list_view(request):
    user = request.user
    shared_references = InspectionReference.objects.filter(is_shared=True).order_by("-created_at")
    private_references = InspectionReference.objects.filter(is_shared=False, owner=user).order_by("-created_at") if user.is_inspector_role else []

    context = {
        "shared_references": shared_references,
        "private_references": private_references,
    }
    return render(request, "inspection/references/list.html", context)


@login_required
def reference_detail_view(request, pk):
    reference = get_object_or_404(InspectionReference, pk=pk)

    if not reference.is_shared and reference.owner != request.user and not request.user.is_admin_role:
        raise PermissionDenied("لا تملك صلاحية عرض هذا المرجع الخاص.")

    root_nodes = reference.nodes.filter(parent=None).prefetch_related("children__children")

    context = {
        "reference": reference,
        "root_nodes": root_nodes,
    }
    return render(request, "inspection/references/detail.html", context)


@login_required
def reference_create_view(request):
    user = request.user
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        is_shared = request.POST.get("is_shared") == "true" and user.is_admin_role
        nodes_json_str = request.POST.get("nodes_json", "[]")

        try:
            nodes_data = json.loads(nodes_json_str)
        except json.JSONDecodeError:
            nodes_data = []

        if not title:
            messages.error(request, "عنوان المرجع مطلوب.")
            return render(request, "inspection/references/form.html", {"title_page": "إنشاء مرجع جديد"})

        try:
            ref = ReferenceService.create_reference(
                title=title,
                description=description,
                user=user,
                is_shared=is_shared,
                nodes_data=nodes_data
            )
            messages.success(request, "تم إنشاء المرجع بنجاح.")
            return redirect("reference_detail", pk=ref.pk)
        except Exception as e:
            messages.error(request, f"خطأ أثناء الإنشاء: {e}")

    return render(request, "inspection/references/form.html", {"title_page": "إنشاء مرجع جديد"})


@login_required
def reference_submit_generalization_view(request, pk):
    user = request.user
    ref = get_object_or_404(InspectionReference, pk=pk)

    if request.method == "POST":
        try:
            sub = ReferenceService.submit_for_generalization(ref, user)
            messages.success(request, "تم تقديم اقتراح تعميم المرجع إلى الإدارة بنجاح.")
        except Exception as e:
            messages.error(request, f"فشل التقديم: {e}")

    return redirect("reference_detail", pk=pk)


@login_required
def governance_submissions_list_view(request):
    if not request.user.is_admin_role:
        raise PermissionDenied("وحدها الإدارة تملك صلاحية الوصول إلى طلبات التعميم.")

    submissions = PrivateReferenceSubmission.objects.all().select_related("submitted_by", "private_reference")
    return render(request, "inspection/governance/submissions_list.html", {"submissions": submissions})


@login_required
def governance_submission_review_view(request, pk):
    if not request.user.is_admin_role:
        raise PermissionDenied("وحدها الإدارة تملك صلاحية مراجعة الطلبات.")

    sub = get_object_or_404(PrivateReferenceSubmission, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        admin_notes = request.POST.get("admin_notes", "").strip()
        approve = (action == "approve")

        try:
            ReferenceService.review_submission(sub, approve=approve, admin_user=request.user, admin_notes=admin_notes)
            if approve:
                messages.success(request, "تم قبول الطلب وتوليد مرجع مشترك جديد بنجاح.")
            else:
                messages.warning(request, "تم رفض طلب التعميم (يبقى المرجع الخاص للمفتش حواً كمرجع خاص).")
        except Exception as e:
            messages.error(request, f"خطأ في المراجعة: {e}")

        return redirect("governance_submissions")

    return render(request, "inspection/governance/submission_detail.html", {"sub": sub})
