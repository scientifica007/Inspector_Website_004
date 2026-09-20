import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied
from inspection.models import (
    User,
    Institution,
    InspectionReference,
    PrivateReferenceSubmission,
    Visit,
    VisitStatus,
    ItemResult,
    NodeType,
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


class EndToEndSystemTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username="admin_user", role=User.Role.ADMIN)
        self.admin.set_password("pass123")
        self.admin.save()

        self.inspector1 = User.objects.create_user(username="insp_1", role=User.Role.INSPECTOR)
        self.inspector1.set_password("pass123")
        self.inspector1.save()

        self.inspector2 = User.objects.create_user(username="insp_2", role=User.Role.INSPECTOR)
        self.inspector2.set_password("pass123")
        self.inspector2.save()

        self.institution = Institution.objects.create(name="مؤسسة الاختبار الشاملة", code="EXP-100")

    def test_permissions_and_private_reference_isolation(self):
        # Inspector 1 creates private reference
        ref1 = ReferenceService.create_reference(
            title="مرجع خاص مفتش 1", description="", user=self.inspector1, is_shared=False
        )

        # Inspector 2 cannot see or edit Inspector 1's reference via service
        with self.assertRaises(PermissionDenied):
            ReferenceService.update_reference(ref1, "تعديل غير مصرح", "", self.inspector2)

        # HTTP level check: Inspector 2 forbidden from viewing Inspector 1's private reference
        self.client.login(username="insp_2", password="pass123")
        response = self.client.get(reverse("reference_detail", kwargs={"pk": ref1.pk}))
        self.assertEqual(response.status_code, 403)

    def test_frozen_snapshot_and_source_deletion_independence(self):
        ref = ReferenceService.create_reference(
            title="مرجع مصدر", description="", user=self.admin, is_shared=True,
            nodes_data=[{"title": "بند 1", "node_type": NodeType.CHECKLIST_ITEM}]
        )

        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector1,
            visit_date=datetime.date.today(),
            source_reference=ref
        )

        # Delete source reference entirely
        ReferenceService.delete_reference(ref, self.admin)

        # Visit still intact with preserved frozen snapshot
        visit.refresh_from_db()
        self.assertEqual(visit.source_reference_title, "مرجع مصدر")
        self.assertEqual(visit.items.count(), 1)
        self.assertIn("nodes", visit.frozen_snapshot)

    def test_overlapping_assignments_and_revocation_integrity(self):
        ref = ReferenceService.create_reference(
            title="مرجع تداخل التكليفات", description="", user=self.admin, is_shared=True,
            nodes_data=[{"title": "بند متداخل", "node_type": NodeType.CHECKLIST_ITEM}]
        )

        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector1,
            visit_date=datetime.date.today(),
            source_reference=ref
        )
        item = visit.items.first()

        # Assignment A sets scope_locked
        ass_a = AssignmentService.create_assignment_draft(
            visit=visit, title="تكليف A", description="", created_by=self.admin,
            entries_data=[{"target_node_id": item.node_id, "scope_locked": True, "completion_required": False}]
        )
        AssignmentService.issue_assignment(ass_a, self.admin)

        # Assignment B sets completion_required
        ass_b = AssignmentService.create_assignment_draft(
            visit=visit, title="تكليف B", description="", created_by=self.admin,
            entries_data=[{"target_node_id": item.node_id, "scope_locked": False, "completion_required": True}]
        )
        AssignmentService.issue_assignment(ass_b, self.admin)

        # Effective constraints should have both locks
        constraints = AssignmentService.get_effective_item_constraints(item)
        self.assertTrue(constraints["scope_locked"])
        self.assertTrue(constraints["completion_required"])

        # Revoke Assignment A -> scope_locked removed, but completion_required from B remains!
        AssignmentService.revoke_assignment(ass_a, self.admin, reason="إلغاء أ")
        constraints_after = AssignmentService.get_effective_item_constraints(item)
        self.assertFalse(constraints_after["scope_locked"])
        self.assertTrue(constraints_after["completion_required"])

    def test_draft_deletion_permissions(self):
        visit = VisitService.create_visit(
            institution=self.institution, inspector=self.inspector1, visit_date=datetime.date.today()
        )

        # Inspector 2 cannot delete Inspector 1's draft visit
        with self.assertRaises(PermissionDenied):
            VisitService.delete_draft_visit(visit, self.inspector2)

        # Inspector 1 can delete own draft visit
        VisitService.delete_draft_visit(visit, self.inspector1)
        self.assertFalse(Visit.objects.filter(pk=visit.pk).exists())
