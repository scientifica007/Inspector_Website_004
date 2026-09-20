import uuid
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import (
    Visit,
    VisitItem,
    VisitStatus,
    InspectionReference,
    ItemOrigin,
    NodeType,
    AssignmentEntry,
    AssignmentStatus
)
from inspection.services.reference_service import ReferenceService


class VisitService:
    @staticmethod
    def create_visit(institution, inspector, visit_date, source_reference=None):
        with transaction.atomic():
            frozen_snapshot = {}
            ref_title = ""
            if source_reference:
                ref_title = source_reference.title
                frozen_snapshot = ReferenceService.build_snapshot_json(source_reference)

            visit = Visit.objects.create(
                institution=institution,
                inspector=inspector,
                visit_date=visit_date,
                source_reference=source_reference,
                source_reference_title=ref_title,
                status=VisitStatus.DRAFT,
                frozen_snapshot=frozen_snapshot
            )

            # Build initial VisitItems from frozen snapshot in unselected/context state
            nodes = frozen_snapshot.get("nodes", [])
            for node in nodes:
                VisitItem.objects.create(
                    visit=visit,
                    node_id=uuid.UUID(node["node_id"]),
                    parent_node_id=uuid.UUID(node["parent_node_id"]) if node.get("parent_node_id") else None,
                    node_type=node["node_type"],
                    title=node["title"],
                    description=node.get("description", ""),
                    order=node.get("order", 0),
                    is_selected=False,
                    is_excluded=False,
                    origin=ItemOrigin.MANUAL,
                    is_local=False
                )

            return visit

    @staticmethod
    def set_item_selection(visit, item_node_id, is_selected, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن تعديل نطاق زيارة مكتملة.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذه الزيارة.")

        item = VisitItem.objects.get(visit=visit, node_id=item_node_id)
        item.is_selected = is_selected
        item.save()

    @staticmethod
    def soft_exclude_item(visit, item_node_id, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن استبعاد عنصر من زيارة مكتملة.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذه الزيارة.")

        # Check if scope locked by issued assignment
        locked = AssignmentEntry.objects.filter(
            assignment__visit=visit,
            assignment__status=AssignmentStatus.ISSUED,
            target_node_id=item_node_id,
            scope_locked=True
        ).exists()

        if locked:
            raise ValidationError("هذا العنصر مقفل بالنطاق بموجب تكليف رسمي ولا يمكن استبعاده.")

        item = VisitItem.objects.get(visit=visit, node_id=item_node_id)
        item.is_excluded = True
        item.save()

    @staticmethod
    def restore_excluded_item(visit, item_node_id, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن تعديل زيارة مكتملة.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذه الزيارة.")

        item = VisitItem.objects.get(visit=visit, node_id=item_node_id)
        item.is_excluded = False
        item.save()

    @staticmethod
    def add_local_content(visit, title, description="", node_type=NodeType.CHECKLIST_ITEM, parent_node_id=None, user=None):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("لا يمكن إضافة محتوى محلي لزيارة مكتملة.")
        if user and visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذه الزيارة.")

        node_id = uuid.uuid4()
        local_item = VisitItem.objects.create(
            visit=visit,
            node_id=node_id,
            parent_node_id=parent_node_id,
            node_type=node_type,
            title=title,
            description=description,
            is_selected=True,
            is_excluded=False,
            origin=ItemOrigin.LOCAL,
            is_local=True
        )
        return local_item

    @staticmethod
    def delete_draft_visit(visit, user):
        if visit.status == VisitStatus.COMPLETED:
            raise ValidationError("ممنوع حازمًا حذف الزيارات المكتملة.")
        if visit.inspector != user and not user.is_admin_role:
            raise PermissionDenied("لا يمكنك حذف مسودة زيارة لمفتش آخر.")

        visit.delete()

    @staticmethod
    def get_effective_scope(visit):
        """
        Returns items categorized into:
        - selected_items: items explicitly selected for inspection
        - context_ancestors: parent nodes needed for display context only
        - excluded_items: soft-excluded items
        """
        items = list(visit.items.all())
        node_map = {item.node_id: item for item in items}

        selected_items = [item for item in items if item.is_selected and not item.is_excluded]
        excluded_items = [item for item in items if item.is_excluded]

        # Calculate ancestor nodes required for context
        context_ids = set()
        for item in selected_items:
            curr = item
            while curr and curr.parent_node_id:
                parent = node_map.get(curr.parent_node_id)
                if parent and not parent.is_selected:
                    context_ids.add(parent.node_id)
                curr = parent

        context_items = [node_map[nid] for nid in context_ids if nid in node_map]

        return {
            "selected_items": selected_items,
            "context_items": context_items,
            "excluded_items": excluded_items
        }
