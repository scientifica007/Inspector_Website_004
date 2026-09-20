from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from inspection.models import Institution, Visit, InspectionReference, PrivateReferenceSubmission, Assignment
from inspection.forms import InstitutionForm

class CustomLoginView(LoginView):
    template_name = "inspection/auth/login.html"

@login_required
def dashboard_view(request):
    user = request.user
    if user.is_admin_role:
        total_visits = Visit.objects.count()
        pending_submissions = PrivateReferenceSubmission.objects.filter(status=PrivateReferenceSubmission.Status.PENDING).count()
        assignments_count = Assignment.objects.count()
    else:
        total_visits = Visit.objects.filter(inspector=user).count()
        pending_submissions = PrivateReferenceSubmission.objects.filter(submitted_by=user, status=PrivateReferenceSubmission.Status.PENDING).count()
        assignments_count = Assignment.objects.filter(visit__inspector=user).count()

    recent_visits = Visit.objects.filter(inspector=user) if not user.is_admin_role else Visit.objects.all()
    recent_visits = recent_visits.select_related("institution", "inspector")[:5]

    context = {
        "total_visits": total_visits,
        "pending_submissions": pending_submissions,
        "assignments_count": assignments_count,
        "recent_visits": recent_visits
    }
    return render(request, "inspection/dashboard.html", context)

@login_required
def institution_list_view(request):
    institutions = Institution.objects.all().order_by("name")
    return render(request, "inspection/institutions/list.html", {"institutions": institutions})

@login_required
def institution_create_view(request):
    if not request.user.is_admin_role:
        messages.error(request, "وحدها الإدارة تملك صلاحية إضافة مؤسسة جديدة.")
        return redirect("institution_list")

    if request.method == "POST":
        form = InstitutionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة المؤسسة بنجاح.")
            return redirect("institution_list")
    else:
        form = InstitutionForm()

    return render(request, "inspection/institutions/form.html", {"form": form, "title": "إضافة مؤسسة جديدة"})

@login_required
def institution_edit_view(request, pk):
    if not request.user.is_admin_role:
        messages.error(request, "وحدها الإدارة تملك صلاحية تعديل المؤسسات.")
        return redirect("institution_list")

    institution = get_object_or_404(Institution, pk=pk)
    if request.method == "POST":
        form = InstitutionForm(request.POST, instance=institution)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت تحديث بيانات المؤسسة بنجاح.")
            return redirect("institution_list")
    else:
        form = InstitutionForm(instance=institution)

    return render(request, "inspection/institutions/form.html", {"form": form, "title": "تعديل مؤسسة"})
