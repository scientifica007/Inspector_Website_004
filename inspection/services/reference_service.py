from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import (
    InspectionReference,
    ReferenceNode,
    PrivateReferenceSubmission,
    NodeType,
    User
)


class ReferenceService:
    @staticmethod
    def create_reference(title, description, user, is_shared=False, nodes_data=None):
        if is_shared and not user.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية إنشاء مرجع مشترك.")

        with transaction.atomic():
            reference = InspectionReference.objects.create(
                title=title,
                description=description,
                is_shared=is_shared,
                owner=None if is_shared else user
            )
            if nodes_data:
                ReferenceService._build_nodes_tree(reference, nodes_data)
            return reference

    @staticmethod
    def update_reference(reference, title, description, user, nodes_data=None):
        if reference.is_shared and not user.is_admin_role:
            raise PermissionDenied("لا يمكنك تعديل مرجع مشترك.")
        if not reference.is_shared and reference.owner != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية تعديل هذا المرجع الخاص.")

        with transaction.atomic():
            reference.title = title
            reference.description = description
            reference.save()

            if nodes_data is not None:
                reference.nodes.all().delete()
                ReferenceService._build_nodes_tree(reference, nodes_data)

            return reference

    @staticmethod
    def delete_reference(reference, user):
        if reference.is_shared and not user.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية حذف مرجع مشترك.")
        if not reference.is_shared and reference.owner != user and not user.is_admin_role:
            raise PermissionDenied("لا تملك صلاحية حذف هذا المرجع الخاص.")

        reference.delete()

    @staticmethod
    def build_snapshot_json(reference):
        nodes = reference.nodes.all().order_by("order", "created_at")
        nodes_list = []
        for node in nodes:
            nodes_list.append({
                "node_id": str(node.node_id),
                "parent_node_id": str(node.parent.node_id) if node.parent else None,
                "node_type": node.node_type,
                "title": node.title,
                "description": node.description,
                "order": node.order,
            })
        return {
            "reference_id": reference.id,
            "title": reference.title,
            "description": reference.description,
            "is_shared": reference.is_shared,
            "nodes": nodes_list,
            "snapshot_timestamp": timezone.now().isoformat()
        }

    @staticmethod
    def submit_for_generalization(private_reference, inspector):
        if private_reference.is_shared:
            raise ValidationError("المرجع المشترك معمم بالفعل.")
        if private_reference.owner != inspector:
            raise PermissionDenied("يمكن لصاحب المرجع الخاص فقط اقتراح تعميمه.")

        snapshot = ReferenceService.build_snapshot_json(private_reference)
        submission = PrivateReferenceSubmission.objects.create(
            private_reference=private_reference,
            submitted_by=inspector,
            status=PrivateReferenceSubmission.Status.PENDING,
            submission_snapshot=snapshot
        )
        return submission

    @staticmethod
    def review_submission(submission, approve, admin_user, admin_notes=""):
        if not admin_user.is_admin_role:
            raise PermissionDenied("وحدها الإدارة تملك صلاحية مراجعة طلبات التعميم.")

        if submission.status != PrivateReferenceSubmission.Status.PENDING:
            raise ValidationError("تمت مراجعة هذا الطلب سابقًا.")

        with transaction.atomic():
            if approve:
                snapshot = submission.submission_snapshot
                shared_ref = InspectionReference.objects.create(
                    title=f"{snapshot.get('title')} (معمم)",
                    description=snapshot.get('description', ''),
                    is_shared=True,
                    owner=None
                )

                id_mapping = {}
                nodes = snapshot.get("nodes", [])

                for node_data in nodes:
                    parent_node = None
                    parent_id_str = node_data.get("parent_node_id")
                    if parent_id_str and parent_id_str in id_mapping:
                        parent_node = id_mapping[parent_id_str]

                    node = ReferenceNode.objects.create(
                        reference=shared_ref,
                        parent=parent_node,
                        node_type=node_data.get("node_type"),
                        title=node_data.get("title"),
                        description=node_data.get("description", ""),
                        order=node_data.get("order", 0)
                    )
                    id_mapping[node_data.get("node_id")] = node

                submission.status = PrivateReferenceSubmission.Status.APPROVED
                submission.resulting_shared_reference = shared_ref
            else:
                submission.status = PrivateReferenceSubmission.Status.REJECTED

            submission.admin_notes = admin_notes
            submission.reviewed_at = timezone.now()
            submission.save()

            return submission

    @staticmethod
    def _build_nodes_tree(reference, nodes_data, parent_node=None):
        for idx, item in enumerate(nodes_data):
            node = ReferenceNode.objects.create(
                reference=reference,
                parent=parent_node,
                node_type=item.get("node_type", NodeType.CHECKLIST_ITEM),
                title=item.get("title", ""),
                description=item.get("description", ""),
                order=item.get("order", idx)
            )
            children = item.get("children", [])
            if children:
                ReferenceService._build_nodes_tree(reference, children, parent_node=node)
