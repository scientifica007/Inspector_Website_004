import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError, PermissionDenied
from inspection.models import (
    User,
    Institution,
    VisitStatus,
    ItemResult,
    NodeType,
    ItemOrigin,
    AssignmentStatus
)
from inspection.services.reference_service import ReferenceService
from inspection.services.visit_service import VisitService
from inspection.services.governance_execution_services import (
    GuideService,
    AssignmentService,
    VisitExecutionService,
    ExportService
)


class GovernanceAndExecutionTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", role=User.Role.ADMIN)
        self.inspector = User.objects.create_user(username="inspector", role=User.Role.INSPECTOR)
        self.institution = Institution.objects.create(name="مؤسسة اختبارية")

        nodes_data = [
            {
                "title": "فرع 1",
                "node_type": NodeType.BRANCH,
                "children": [
                    {
                        "title": "بند 1",
                        "node_type": NodeType.CHECKLIST_ITEM
                    },
                    {
                        "title": "بند 2",
                        "node_type": NodeType.CHECKLIST_ITEM
                    }
                ]
            }
        ]
        self.ref = ReferenceService.create_reference(
            title="مرجع معيار التفتيش",
            description="",
            user=self.admin,
            is_shared=True,
            nodes_data=nodes_data
        )

        self.visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector,
            visit_date=datetime.date.today(),
            source_reference=self.ref
        )

    def test_guide_idempotency_and_mismatch_handling(self):
        ref_items = list(self.ref.nodes.all())
        guide = GuideService.create_guide(
            title="دليل السلامة",
            description="",
            reference=self.ref,
            created_by=self.admin,
            entry_target_node_ids=[ref_items[1].node_id]
        )

        # Apply guide to visit
        applied = GuideService.apply_guide_to_visit(self.visit, guide, self.inspector)
        self.assertEqual(applied, 1)

        item1 = self.visit.items.get(node_id=ref_items[1].node_id)
        self.assertTrue(item1.is_selected)
        self.assertEqual(item1.origin, ItemOrigin.GUIDE)

        # Idempotence: applying guide again does not duplicate or reset origin
        applied2 = GuideService.apply_guide_to_visit(self.visit, guide, self.inspector)
        self.assertEqual(applied2, 0)
        item1.refresh_from_db()
        self.assertEqual(item1.origin, ItemOrigin.GUIDE)

    def test_assignment_atomic_issuance_and_completion_blocking(self):
        ref_items = list(self.ref.nodes.all())
        target_item = self.visit.items.get(node_id=ref_items[1].node_id)

        # Create draft assignment with completion_required and scope_locked
        entries_data = [
            {
                "target_node_id": target_item.node_id,
                "scope_locked": True,
                "completion_required": True
            }
        ]
        assignment = AssignmentService.create_assignment_draft(
            visit=self.visit,
            title="تكليف إداري عاجل",
            description="",
            created_by=self.admin,
            entries_data=entries_data
        )

        self.assertEqual(assignment.status, AssignmentStatus.DRAFT)

        # Issue assignment
        AssignmentService.issue_assignment(assignment, self.admin)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.ISSUED)

        # Attempt to complete visit before fulfilling required assignment item fails
        with self.assertRaises(ValidationError):
            VisitExecutionService.complete_visit(self.visit, self.inspector)

        # Attempt to soft-exclude locked item fails
        with self.assertRaises(ValidationError):
            VisitService.soft_exclude_item(self.visit, target_item.node_id, self.inspector)

        # Record response for required item
        VisitExecutionService.record_item_response(
            self.visit,
            target_item.node_id,
            result=ItemResult.COMPLIANT,
            observation="مستوفاة بامتياز"
        )

        # Now completion succeeds
        completed_visit = VisitExecutionService.complete_visit(self.visit, self.inspector)
        self.assertEqual(completed_visit.status, VisitStatus.COMPLETED)

        # Immutability of completed visit: cannot record new response
        with self.assertRaises(ValidationError):
            VisitExecutionService.record_item_response(
                self.visit,
                target_item.node_id,
                result=ItemResult.NON_COMPLIANT
            )

    def test_assignment_revocation(self):
        ref_items = list(self.ref.nodes.all())
        target_item = self.visit.items.get(node_id=ref_items[1].node_id)

        assignment = AssignmentService.create_assignment_draft(
            visit=self.visit,
            title="تكليف ملغى",
            description="",
            created_by=self.admin,
            entries_data=[{"target_node_id": target_item.node_id, "scope_locked": True}]
        )
        AssignmentService.issue_assignment(assignment, self.admin)

        # Revoking without reason fails
        with self.assertRaises(ValidationError):
            AssignmentService.revoke_assignment(assignment, self.admin, reason="")

        # Revoking with reason succeeds
        AssignmentService.revoke_assignment(assignment, self.admin, reason="خطأ في الإدخال الإداري")
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.REVOKED)
        self.assertEqual(assignment.revocation_reason, "خطأ في الإدخال الإداري")

    def test_deterministic_export_schema(self):
        payload = ExportService.export_visit_json(self.visit)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["visit_id"], self.visit.id)
        self.assertIn("items", payload)
        self.assertIn("assignments_history", payload)
