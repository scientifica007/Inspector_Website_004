import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import Visit, VisitItem, Institution, InspectionReference, ItemResult, VisitStatus, NodeType
from inspection.forms import VisitCreateForm
from inspection.services.visit_service import VisitService
from inspection.services.governance_execution_services import VisitExecutionService, ExportService, GuideService, AssignmentService


@login_required
def visit_list_view(request):
    user = request.user
    if user.is_admin_role:
        visits = Visit.objects.all().select_related("institution", "inspector").order_by("-visit_date", "-created_at")
    else:
        visits = Visit.objects.filter(inspector=user).select_related("institution", "inspector").order_by("-visit_date", "-created_at")

    return render(request, "inspection/visits/list.html", {"visits": visits})


@login_required
def visit_create_view(request):
    user = request.user
    if request.method == "POST":
        form = VisitCreateForm(request.POST, user=user)
        if form.is_valid():
            visit = VisitService.create_visit(
                institution=form.cleaned_data["institution"],
                inspector=user,
                visit_date=form.cleaned_data["visit_date"],
                source_reference=form.cleaned_data.get("source_reference")
            )
            messages.success(request, "تم إنشاء الزيارة بنجاح وتم تجميد المرجع.")
            return redirect("visit_detail", pk=visit.pk)
    else:
        form = VisitCreateForm(user=user)

    return render(request, "inspection/visits/form.html", {"form": form})


@login_required
def visit_detail_view(request, pk):
    visit = get_object_or_404(Visit.objects.select_related("institution", "inspector", "source_reference"), pk=pk)

    if not request.user.is_admin_role and visit.inspector != request.user:
        raise PermissionDenied("لا تملك صلاحية عرض هذه الزيارة.")

    scope = VisitService.get_effective_scope(visit)
    progress = VisitExecutionService.calculate_progress(visit)

    # Prepare item constraints mapping
    all_items = visit.items.all().order_by("order", "created_at")
    items_with_constraints = []
    for item in all_items:
        constraints = AssignmentService.get_effective_item_constraints(item)
        items_with_constraints.append({
            "item": item,
            "constraints": constraints
        })

    # Get available guides for source reference if visit is draft
    available_guides = []
    if visit.status == VisitStatus.DRAFT and visit.source_reference:
        available_guides = visit.source_reference.guides.all()

    # Active assignments on visit
    issued_assignments = visit.assignments.filter(status="ISSUED")

    context = {
        "visit": visit,
        "scope": scope,
        "progress": progress,
        "items_with_constraints": items_with_constraints,
        "available_guides": available_guides,
        "issued_assignments": issued_assignments
    }
    return render(request, "inspection/visits/detail.html", context)


@login_required
def visit_toggle_item_scope_view(request, pk, item_node_id):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        is_selected = request.POST.get("is_selected") == "true"
        try:
            VisitService.set_item_selection(visit, item_node_id, is_selected, request.user)
            messages.success(request, "تم تحديث نطاق الزيارة.")
        except Exception as e:
            messages.error(request, f"فشل التعديل: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_exclude_item_view(request, pk, item_node_id):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        try:
            VisitService.soft_exclude_item(visit, item_node_id, request.user)
            messages.warning(request, "تم استبعاد العنصر مؤقتاً من النطاق.")
        except Exception as e:
            messages.error(request, f"فشل الاستبعاد: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_restore_item_view(request, pk, item_node_id):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        try:
            VisitService.restore_excluded_item(visit, item_node_id, request.user)
            messages.success(request, "تم استرجاع العنصر إلى النطاق بكافة بياناته السابقة.")
        except Exception as e:
            messages.error(request, f"فشل الاسترجاع: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_add_local_item_view(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        if title:
            try:
                VisitService.add_local_content(visit, title, description, user=request.user)
                messages.success(request, "تمت إضافة العنصر المحلي بنجاح.")
            except Exception as e:
                messages.error(request, f"خطأ: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_record_response_view(request, pk, item_node_id):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        result = request.POST.get("result")
        observation = request.POST.get("observation")
        value_text = request.POST.get("value_text")

        try:
            VisitExecutionService.record_item_response(
                visit=visit,
                item_node_id=item_node_id,
                result=result,
                observation=observation,
                value_text=value_text,
                user=request.user
            )
            messages.success(request, "تم حفظ نتيجة الفحص بنجاح.")
        except Exception as e:
            messages.error(request, f"فشل الحفظ: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_apply_guide_view(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        guide_id = request.POST.get("guide_id")
        guide = get_object_or_404(visit.source_reference.guides, pk=guide_id)
        try:
            applied = GuideService.apply_guide_to_visit(visit, guide, request.user)
            messages.success(request, f"تم تطبيق الدليل بنجاح وإضافة {applied} عنصر/عناصر متوافق إلى النطاق.")
        except Exception as e:
            messages.error(request, f"فشل تطبيق الدليل: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_complete_view(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        try:
            VisitExecutionService.complete_visit(visit, request.user)
            messages.success(request, "تم إكمال الزيارة بنجاح وأصبحت حقيقة تاريخية محمية.")
        except Exception as e:
            messages.error(request, f"تعذر إكمال الزيارة: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_delete_draft_view(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if request.method == "POST":
        try:
            VisitService.delete_draft_visit(visit, request.user)
            messages.success(request, "تم حذف مسودة الزيارة.")
            return redirect("visit_list")
        except Exception as e:
            messages.error(request, f"فشل الحذف: {e}")

    return redirect("visit_detail", pk=pk)


@login_required
def visit_export_json_view(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if not request.user.is_admin_role and visit.inspector != request.user:
        raise PermissionDenied("لا تملك صلاحية تصدير هذه الزيارة.")

    data = ExportService.export_visit_json(visit)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    response = HttpResponse(json_str, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="visit_export_{visit.id}_{visit.visit_date}.json"'
    return response
