import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "مدير النظام"
        INSPECTOR = "INSPECTOR", "مفتش التكوين والتعليم المهنيين"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.INSPECTOR,
        verbose_name="الدور"
    )

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_inspector_role(self):
        return self.role == self.Role.INSPECTOR


class Institution(models.Model):
    name = models.CharField(max_length=255, verbose_name="اسم المؤسسة")
    institution_type = models.CharField(max_length=100, verbose_name="نوع المؤسسة", blank=True, default="")
    code = models.CharField(max_length=50, verbose_name="رمز المؤسسة", blank=True, default="")
    address = models.CharField(max_length=255, verbose_name="العنوان", blank=True, default="")
    city = models.CharField(max_length=100, verbose_name="المدينة / الولاية", blank=True, default="")
    is_active = models.BooleanField(default=True, verbose_name="نشطة")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مؤسسة"
        verbose_name_plural = "المؤسسات"

    def __str__(self):
        return self.name


class NodeType(models.TextChoices):
    BRANCH = "BRANCH", "فرع / قسم"
    SPECIFICATION = "SPECIFICATION", "وصف / مواصفة"
    CHECKLIST_ITEM = "CHECKLIST_ITEM", "بند تفتيش"


class InspectionReference(models.Model):
    title = models.CharField(max_length=255, verbose_name="عنوان المرجع")
    description = models.TextField(blank=True, verbose_name="الوصف")
    is_shared = models.BooleanField(default=False, verbose_name="مرجع مشترك")
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="private_references",
        verbose_name="المالك"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "مرجع تفتيش"
        verbose_name_plural = "مراجع التفتيش"

    def __str__(self):
        return f"{self.title} ({'مشترك' if self.is_shared else 'خاص'})"


class ReferenceNode(models.Model):
    node_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference = models.ForeignKey(
        InspectionReference,
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name="المرجع"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="العقدة الأب"
    )
    node_type = models.CharField(
        max_length=20,
        choices=NodeType.choices,
        default=NodeType.CHECKLIST_ITEM,
        verbose_name="نوع العقدة"
    )
    title = models.CharField(max_length=255, verbose_name="العنوان")
    description = models.TextField(blank=True, verbose_name="الوصف / المواصفة")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        verbose_name = "عقدة مرجعية"
        verbose_name_plural = "عقد مرجعية"

    def __str__(self):
        return f"{self.get_node_type_display()}: {self.title}"


class PrivateReferenceSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "قيد المراجعة"
        APPROVED = "APPROVED", "مقبول (معمم)"
        REJECTED = "REJECTED", "مرفوض"

    private_reference = models.ForeignKey(
        InspectionReference,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="المرجع الخاص"
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="submitted_references",
        verbose_name="المقترح"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="الحالة"
    )
    submission_snapshot = models.JSONField(verbose_name="لقطة المحتوى المرفوع")
    admin_notes = models.TextField(blank=True, verbose_name="ملاحظات الإدارة")
    resulting_shared_reference = models.ForeignKey(
        InspectionReference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_from_submissions",
        verbose_name="المرجع المشترك الناتج"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب تعميم مرجع"
        verbose_name_plural = "طلبات تعميم المراجع"


class ItemOrigin(models.TextChoices):
    LEGACY = "LEGACY", "موروث"
    MANUAL = "MANUAL", "يدوي"
    GUIDE = "GUIDE", "دليل"
    ASSIGNMENT = "ASSIGNMENT", "تكليف"
    LOCAL = "LOCAL", "محلي"


class ItemResult(models.TextChoices):
    UNANSWERED = "UNANSWERED", "غير محدد"
    COMPLIANT = "COMPLIANT", "مطابق"
    NON_COMPLIANT = "NON_COMPLIANT", "غير مطابق"
    NOT_APPLICABLE = "NOT_APPLICABLE", "غير منطبق"


class VisitStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    COMPLETED = "COMPLETED", "مكتملة"


class Visit(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        related_name="visits",
        verbose_name="المؤسسة"
    )
    inspector = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="visits",
        verbose_name="المفتش"
    )
    visit_date = models.DateField(verbose_name="تاريخ الزيارة")
    source_reference = models.ForeignKey(
        InspectionReference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visits",
        verbose_name="المرجع المصدر"
    )
    source_reference_title = models.CharField(max_length=255, blank=True, verbose_name="اسم المرجع عند الإنشاء")
    status = models.CharField(
        max_length=20,
        choices=VisitStatus.choices,
        default=VisitStatus.DRAFT,
        verbose_name="حالة الزيارة"
    )
    frozen_snapshot = models.JSONField(default=dict, blank=True, verbose_name="لقطة المرجع المجمدة")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإكمال")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        verbose_name = "زيارة تفتيشية"
        verbose_name_plural = "الزيارات التفتيشية"

    def __str__(self):
        return f"زيارة {self.institution.name} - {self.visit_date} ({self.get_status_display()})"


class VisitItem(models.Model):
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="الزيارة"
    )
    node_id = models.UUIDField(default=uuid.uuid4, verbose_name="معرف العقدة المستقر")
    parent_node_id = models.UUIDField(null=True, blank=True, verbose_name="معرف العقدة الأب")
    node_type = models.CharField(
        max_length=20,
        choices=NodeType.choices,
        default=NodeType.CHECKLIST_ITEM,
        verbose_name="نوع العقدة"
    )
    title = models.CharField(max_length=255, verbose_name="العنوان")
    description = models.TextField(blank=True, verbose_name="الوصف / المواصفة")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    is_selected = models.BooleanField(default=False, verbose_name="محدد ضمن نطاق التفتيش")
    is_excluded = models.BooleanField(default=False, verbose_name="مستبعد (Soft Exclusion)")
    origin = models.CharField(
        max_length=20,
        choices=ItemOrigin.choices,
        default=ItemOrigin.MANUAL,
        verbose_name="المصدر الأصلي"
    )
    result = models.CharField(
        max_length=20,
        choices=ItemResult.choices,
        default=ItemResult.UNANSWERED,
        verbose_name="النتيجة"
    )
    value_text = models.TextField(blank=True, verbose_name="القيمة / النص للمواصفة")
    observation = models.TextField(blank=True, verbose_name="الملاحظات")
    is_local = models.BooleanField(default=False, verbose_name="محتوى محلي للزيارة")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        unique_together = [("visit", "node_id")]
        verbose_name = "عنصر زيارة"
        verbose_name_plural = "عناصر الزيارة"

    def __str__(self):
        return f"{self.title} ({self.visit})"


class Guide(models.Model):
    title = models.CharField(max_length=255, verbose_name="عنوان الدليل")
    description = models.TextField(blank=True, verbose_name="الوصف")
    reference = models.ForeignKey(
        InspectionReference,
        on_delete=models.CASCADE,
        related_name="guides",
        verbose_name="المرجع المرتبط"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_guides",
        verbose_name="أنشئ بواسطة"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "دليل تفتيش"
        verbose_name_plural = "أدلة التفتيش"

    def __str__(self):
        return f"دليل: {self.title} (مرجع: {self.reference.title})"


class GuideEntry(models.Model):
    guide = models.ForeignKey(
        Guide,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="الدليل"
    )
    target_node_id = models.UUIDField(verbose_name="معرف العقدة المستهدفة")

    class Meta:
        unique_together = [("guide", "target_node_id")]
        verbose_name = "عنصر دليل"
        verbose_name_plural = "عناصر الأدلة"


class AssignmentStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    ISSUED = "ISSUED", "صادر"
    REVOKED = "REVOKED", "ملغى"


class Assignment(models.Model):
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="الزيارة"
    )
    title = models.CharField(max_length=255, verbose_name="عنوان التكليف الرسمية")
    description = models.TextField(blank=True, verbose_name="تفاصيل التكليف")
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        verbose_name="أنشئ بواسطة"
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.DRAFT,
        verbose_name="حالة التكليف"
    )
    issued_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإصدار")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإلغاء")
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_assignments",
        verbose_name="أُلغي بواسطة"
    )
    revocation_reason = models.TextField(blank=True, verbose_name="سبب الإلغاء")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تكليف رسمي"
        verbose_name_plural = "التكليفات الرسمية"

    def __str__(self):
        return f"تكليف: {self.title} - {self.visit} ({self.get_status_display()})"


class AssignmentEntry(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="التكليف"
    )
    target_node_id = models.UUIDField(verbose_name="معرف العقدة المستهدفة")
    scope_locked = models.BooleanField(default=False, verbose_name="مقفل النطاق (ممنوع الاستبعاد)")
    completion_required = models.BooleanField(default=False, verbose_name="إلزامي الإكمال")

    class Meta:
        unique_together = [("assignment", "target_node_id")]
        verbose_name = "قيد تكليف"
        verbose_name_plural = "قيود التكليفات"
