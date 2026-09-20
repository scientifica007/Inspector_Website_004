from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
from inspection.models import User, InspectionReference, PrivateReferenceSubmission, NodeType
from inspection.services.reference_service import ReferenceService


class ReferenceServiceTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", role=User.Role.ADMIN)
        self.inspector1 = User.objects.create_user(username="insp1", role=User.Role.INSPECTOR)
        self.inspector2 = User.objects.create_user(username="insp2", role=User.Role.INSPECTOR)

    def test_create_shared_reference_by_admin(self):
        nodes_data = [
            {
                "title": "فرع 1",
                "node_type": NodeType.BRANCH,
                "children": [
                    {
                        "title": "بند 1",
                        "node_type": NodeType.CHECKLIST_ITEM
                    }
                ]
            }
        ]
        ref = ReferenceService.create_reference(
            title="مرجع مشترك بيداغوجي",
            description="وصف المرجع",
            user=self.admin,
            is_shared=True,
            nodes_data=nodes_data
        )
        self.assertTrue(ref.is_shared)
        self.assertIsNone(ref.owner)
        self.assertEqual(ref.nodes.count(), 2)

    def test_create_shared_reference_by_inspector_denied(self):
        with self.assertRaises(PermissionDenied):
            ReferenceService.create_reference(
                title="مرجع غير مصرح",
                description="",
                user=self.inspector1,
                is_shared=True
            )

    def test_private_reference_isolation_and_submission(self):
        nodes_data = [{"title": "بند خاص", "node_type": NodeType.CHECKLIST_ITEM}]
        priv_ref = ReferenceService.create_reference(
            title="مرجع خاص للمفتش 1",
            description="",
            user=self.inspector1,
            is_shared=False,
            nodes_data=nodes_data
        )
        self.assertFalse(priv_ref.is_shared)
        self.assertEqual(priv_ref.owner, self.inspector1)

        # Inspector 2 cannot edit Inspector 1's reference
        with self.assertRaises(PermissionDenied):
            ReferenceService.update_reference(
                priv_ref, title="تعديل غير مصرح", description="", user=self.inspector2
            )

        # Submit for generalization
        submission = ReferenceService.submit_for_generalization(priv_ref, self.inspector1)
        self.assertEqual(submission.status, PrivateReferenceSubmission.Status.PENDING)
        self.assertIn("بند خاص", str(submission.submission_snapshot))

        # Modifying private reference after submission does not alter submission snapshot
        ReferenceService.update_reference(
            priv_ref,
            title="مرجع خاص معدل",
            description="",
            user=self.inspector1,
            nodes_data=[{"title": "بند جديد بعد الإرسال", "node_type": NodeType.CHECKLIST_ITEM}]
        )

        submission.refresh_from_db()
        snapshot_nodes = submission.submission_snapshot["nodes"]
        self.assertEqual(len(snapshot_nodes), 1)
        self.assertEqual(snapshot_nodes[0]["title"], "بند خاص")

        # Admin approves submission -> Creates independent shared reference
        reviewed_sub = ReferenceService.review_submission(
            submission, approve=True, admin_user=self.admin, admin_notes="تم القبول"
        )
        self.assertEqual(reviewed_sub.status, PrivateReferenceSubmission.Status.APPROVED)
        self.assertIsNotNone(reviewed_sub.resulting_shared_reference)
        self.assertTrue(reviewed_sub.resulting_shared_reference.is_shared)

        # Original private reference remains private and owned by inspector1
        priv_ref.refresh_from_db()
        self.assertFalse(priv_ref.is_shared)
        self.assertEqual(priv_ref.owner, self.inspector1)
