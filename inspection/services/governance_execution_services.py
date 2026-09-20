import uuid
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import (
    Guide,
    GuideEntry,
    Assignment,
    AssignmentEntry,
    AssignmentStatus,
    Visit,
    VisitItem,
    VisitStatus,
    ItemOrigin,
    ItemResult,
    NodeType
)


class GuideService:
    @staticmethod
    def create_guide(title, description, reference, created_by, entry_target_node_ids=None):
        if not created_by.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية إنشاء دليل تفتيش.")

        with transaction.atomic():
            guide = Guide.objects.create(
                title=title,
                description=description,
                reference=reference,
                created_by=created_by
            )
            if entry_target_node_ids:
                for target_id in entry_target_node_ids:
                    node_uuid = target_id if isinstance(target_id, uuid.UUID) else uuid.UUID(str(target_id))
                    GuideEntry.objects.get_or_create(guide=guide, target_node_id=node_uuid)
            return guide

    @staticmethod
    def apply_guide_to_visit(visit, guide, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن تطبيق دليل على زيارة مكتملة.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذه الزيارة.")

        guide_entries = guide.entries.all()
        applied_count = 0

        with transaction.atomic():
            for entry in guide_entries:
                try:
                    visit_item = VisitItem.objects.get(visit=visit, node_id=entry.target_node_id)
                except VisitItem.DoesNotExist:
                    # Mismatched target node not present in visit's frozen snapshot -> Skip
                    continue

                if not visit_item.is_selected:
                    visit_item.is_selected = True
                    if visit_item.origin == ItemOrigin.MANUAL:
                        visit_item.origin = ItemOrigin.GUIDE
                    visit_item.save()
                    applied_count += 1

        return applied_count


class AssignmentService:
    @staticmethod
    def create_assignment_draft(visit, title, description, created_by, entries_data):
        if not created_by.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية إنشاء تكليف رسمي.")
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن إنشاء تكليف على زيارة مكتملة.")

        with transaction.atomic():
            assignment = Assignment.objects.create(
                visit=visit,
                title=title,
                description=description,
                created_by=created_by,
                status=AssignmentStatus.DRAFT
            )

            snapshot_node_ids = {
                uuid.UUID(n["node_id"]) for n in visit.frozen_snapshot.get("nodes", [])
            } if visit.frozen_snapshot else set()

            # Include local content node_ids if present
            snapshot_node_ids.update(visit.items.values_list("node_id", flat=True))

            for entry_data in entries_data:
                target_id = entry_data.get("target_node_id")
                target_uuid = target_id if isinstance(target_id, uuid.UUID) else uuid.UUID(str(target_id))

                if snapshot_node_ids and target_uuid not in snapshot_node_ids:
                    raise ValidationError(f"العقدة المستهدفة {target_uuid} غير موجودة في المرجع المجمد للزيارة.")

                AssignmentEntry.objects.create(
                    assignment=assignment,
                    target_node_id=target_uuid,
                    scope_locked=entry_data.get("scope_locked", False),
                    completion_required=entry_data.get("completion_required", False)
                )

            return assignment

    @staticmethod
    def issue_assignment(assignment, admin_user):
        if not admin_user.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية إصدار التكليفات.")
        if assignment.visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن إصدار تكليف لزيارة مكتملة.")
        if assignment.status != AssignmentStatus.DRAFT:
            raise ValidationError("التكليف تم إصداره أو إلغاؤه سابقاً.")

        # Atomic issue verification: all target entries must exist in visit snapshot
        entries = assignment.entries.all()
        visit = assignment.visit
        visit_node_ids = set(visit.items.values_list("node_id", flat=True))

        with transaction.atomic():
            for entry in entries:
                if entry.target_node_id not in visit_node_ids:
                    raise ValidationError(f"فشل الإصدار: العقدة {entry.target_node_id} غير موجودة في عناصر الزيارة.")

            assignment.status = AssignmentStatus.ISSUED
            assignment.issued_at = timezone.now()
            assignment.save()

            # Update visit items to selected if they were not selected
            for entry in entries:
                item = VisitItem.objects.get(visit=visit, node_id=entry.target_node_id)
                item.is_selected = True
                if item.origin in [ItemOrigin.MANUAL, ItemOrigin.GUIDE]:
                    item.origin = ItemOrigin.ASSIGNMENT
                if item.is_excluded:
                    item.is_excluded = False
                item.save()

            return assignment

    @staticmethod
    def revoke_assignment(assignment, admin_user, reason):
        if not admin_user.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية إلغاء التكليفات.")
        if assignment.visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن إلغاء تكليف لزيارة مكتملة.")
        if assignment.status != AssignmentStatus.ISSUED:
            raise ValidationError("لا يمكن إلغاء تكليف غير صادر.")
        if not reason or not reason.strip():
            raise ValidationError("يجب تقديم سبب إلغاء التكليف الرسمي.")

        with transaction.atomic():
            assignment.status = AssignmentStatus.REVOKED
            assignment.revoked_at = timezone.now()
            assignment.revoked_by = admin_user
            assignment.revocation_reason = reason.strip()
            assignment.save()

            return assignment

    @staticmethod
    def get_effective_item_constraints(visit_item):
        """
        Calculates active constraints from all active (ISSUED) assignments.
        """
        active_entries = AssignmentEntry.objects.filter(
            assignment__visit=visit_item.visit,
            assignment__status=AssignmentStatus.ISSUED,
            target_node_id=visit_item.node_id
        )

        scope_locked = active_entries.filter(scope_locked=True).exists()
        completion_required = active_entries.filter(completion_required=True).exists()

        return {
            "scope_locked": scope_locked,
            "completion_required": completion_required
        }


class VisitExecutionService:
    @staticmethod
    def record_item_response(visit, item_node_id, result=None, observation=None, value_text=None, user=None):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("حقيقة تاريخية محمية: الزيارة المكتملة لا يمكن تعديل نتائجها.")
        if user and visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تنفيذ هذه الزيارة.")

        item = VisitItem.objects.get(visit=visit, node_id=item_node_id)

        if result is not None:
            item.result = result
        if observation is not None:
            item.observation = observation
        if value_text is not None:
            item.value_text = value_text

        item.save()
        return item

    @staticmethod
    def calculate_progress(visit):
        # Progress is calculated strictly on active selected checklist items
        active_checklist_items = visit.items.filter(
            is_selected=True,
            is_excluded=False,
            node_type=NodeType.CHECKLIST_ITEM
        )
        total_count = active_checklist_items.count()
        if total_count == 0:
            return {"total": 0, "completed": 0, "percentage": 100}

        completed_count = active_checklist_items.exclude(result=ItemResult.UNANSWERED).count()
        percentage = round((completed_count / total_count) * 100)

        return {
            "total": total_count,
            "completed": completed_count,
            "percentage": percentage
        }

    @staticmethod
    def complete_visit(visit, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("الزيارة مكتملة بالفعل.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية إكمال هذه الزيارة.")

        # Check all completion_required items from active ISSUED assignments
        active_entries = AssignmentEntry.objects.filter(
            assignment__visit=visit,
            assignment__status=AssignmentStatus.ISSUED,
            completion_required=True
        )

        required_target_ids = set(active_entries.values_list("target_node_id", flat=True))

        for target_id in required_target_ids:
            try:
                item = VisitItem.objects.get(visit=visit, node_id=target_id)
                if item.is_excluded:
                    raise ValidationError(f"لا يمكن إكمال الزيارة: العنصر المطلوب {item.title} مستبعد.")
                # If checklist item, must have an answered result
                if item.node_type == NodeType.CHECKLIST_ITEM and item.result == ItemResult.UNANSWERED:
                    raise ValidationError(f"لا يمكن إكمال الزيارة: العنصر الإلزامي {item.title} لم يتم تقييمه.")
                # If specification, must have value_text or observation
                if item.node_type == NodeType.SPECIFICATION and not item.value_text.strip() and not item.observation.strip():
                    raise ValidationError(f"لا يمكن إكمال الزيارة: المواصفة الإلزامية {item.title} لم يتم تعبئتها.")
            except VisitItem.DoesNotExist:
                raise ValidationError("عنصر التكليف المطلوب غير موجود في الزيارة.")

        visit.status = VisitStatus.COMPLETED
        visit.completed_at = timezone.now()
        visit.save()
        return visit


class ExportService:
    @staticmethod
    def export_visit_json(visit):
        effective_scope = visit.items.all().order_by("order", "created_at")
        items_payload = []

        for item in effective_scope:
            constraints = AssignmentService.get_effective_item_constraints(item)
            items_payload.append({
                "node_id": str(item.node_id),
                "parent_node_id": str(item.parent_node_id) if item.parent_node_id else None,
                "node_type": item.node_type,
                "title": item.title,
                "description": item.description,
                "is_selected": item.is_selected,
                "is_excluded": item.is_excluded,
                "origin": item.origin,
                "result": item.result,
                "value_text": item.value_text,
                "observation": item.observation,
                "is_local": item.is_local,
                "constraints": constraints
            })

        assignments_payload = []
        for ass in visit.assignments.all().order_by("created_at"):
            assignments_payload.append({
                "id": ass.id,
                "title": ass.title,
                "description": ass.description,
                "status": ass.status,
                "issued_at": ass.issued_at.isoformat() if ass.issued_at else None,
                "revoked_at": ass.revoked_at.isoformat() if ass.revoked_at else None,
                "revoked_by": ass.revoked_by.username if ass.revoked_by else None,
                "revocation_reason": ass.revocation_reason,
                "entries": [
                    {
                        "target_node_id": str(e.target_node_id),
                        "scope_locked": e.scope_locked,
                        "completion_required": e.completion_required
                    } for e in ass.entries.all()
                ]
            })

        return {
            "schema_version": "1.0",
            "visit_id": visit.id,
            "status": visit.status,
            "institution": {
                "id": visit.institution.id,
                "name": visit.institution.name,
                "code": visit.institution.code
            },
            "inspector": {
                "id": visit.inspector.id,
                "username": visit.inspector.username
            },
            "visit_date": visit.visit_date.strftime("%Y-%m-%d"),
            "completed_at": visit.completed_at.isoformat() if visit.completed_at else None,
            "source_reference_title": visit.source_reference_title,
            "progress": VisitExecutionService.calculate_progress(visit),
            "items": items_payload,
            "assignments_history": assignments_payload
        }
