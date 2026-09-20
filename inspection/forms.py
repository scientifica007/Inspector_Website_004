from django import forms
from inspection.models import Institution, InspectionReference, ReferenceNode, Guide, Assignment, Visit

class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "institution_type", "code", "city", "address", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "institution_type": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

class VisitCreateForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["institution", "visit_date", "source_reference"]
        widgets = {
            "institution": forms.Select(attrs={"class": "form-select"}),
            "visit_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source_reference": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            # Inspectors can select shared references OR their own private references
            if user.is_admin_role:
                self.fields["source_reference"].queryset = InspectionReference.objects.all()
            else:
                self.fields["source_reference"].queryset = InspectionReference.objects.filter(
                    is_shared=True
                ) | InspectionReference.objects.filter(owner=user)
