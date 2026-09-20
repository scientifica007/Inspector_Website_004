import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError, PermissionDenied
from inspection.models import User, Institution, InspectionReference, VisitStatus, ItemResult, NodeType
from inspection.services.reference_service import ReferenceService
from inspection.services.visit_service import VisitService


class VisitServiceTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", role=User.Role.ADMIN)
        self.inspector = User.objects.create_user(username="inspector", role=User.Role.INSPECTOR)
        self.institution = Institution.objects.create(name="مؤسسة التكوين المهني 1")

        # Create source shared reference
        nodes_data = [
            {
                "title": "فرع البيداغوجيا",
                "node_type": NodeType.BRANCH,
                "children": [
                    {
                        "title": "مواصفة الدفتر",
                        "node_type": NodeType.SPECIFICATION,
                        "children": [
                            {
                                "title": "بند مراقبة الدفتر اليومي",
                                "node_type": NodeType.CHECKLIST_ITEM
                            }
                        ]
                    }
                ]
            }
        ]
        self.ref = ReferenceService.create_reference(
            title="المرجع الوطني للتفتيش",
            description="",
            user=self.admin,
            is_shared=True,
            nodes_data=nodes_data
        )

    def test_create_visit_captures_frozen_snapshot(self):
        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector,
            visit_date=datetime.date.today(),
            source_reference=self.ref
        )

        self.assertEqual(visit.status, VisitStatus.DRAFT)
        self.assertIn("nodes", visit.frozen_snapshot)
        self.assertEqual(len(visit.frozen_snapshot["nodes"]), 3)

        # Modifying original reference does not change visit items or snapshot
        ReferenceService.update_reference(
            self.ref,
            title="مرجع معدل لاحقاً",
            description="",
            user=self.admin,
            nodes_data=[]
        )

        visit.refresh_from_db()
        self.assertEqual(visit.source_reference_title, "المرجع الوطني للتفتيش")
        self.assertEqual(visit.items.count(), 3)

    def test_selective_scope_and_context(self):
        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector,
            visit_date=datetime.date.today(),
            source_reference=self.ref
        )

        checklist_item = visit.items.get(node_type=NodeType.CHECKLIST_ITEM)
        VisitService.set_item_selection(visit, checklist_item.node_id, is_selected=True, user=self.inspector)

        effective_scope = VisitService.get_effective_scope(visit)
        self.assertEqual(len(effective_scope["selected_items"]), 1)
        self.assertEqual(effective_scope["selected_items"][0], checklist_item)
        # Check that ancestors (BRANCH & SPECIFICATION) are returned in context_items
        self.assertEqual(len(effective_scope["context_items"]), 2)

    def test_soft_exclusion_and_restoration_preserves_notes(self):
        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector,
            visit_date=datetime.date.today(),
            source_reference=self.ref
        )
        item = visit.items.get(node_type=NodeType.CHECKLIST_ITEM)
        item.result = ItemResult.COMPLIANT
        item.observation = "ملاحظة تدقيقية"
        item.is_selected = True
        item.save()

        # Soft exclude
        VisitService.soft_exclude_item(visit, item.node_id, user=self.inspector)
        item.refresh_from_db()
        self.assertTrue(item.is_excluded)

        # Restore item
        VisitService.restore_excluded_item(visit, item.node_id, user=self.inspector)
        item.refresh_from_db()
        self.assertFalse(item.is_excluded)
        self.assertEqual(item.result, ItemResult.COMPLIANT)
        self.assertEqual(item.observation, "ملاحظة تدقيقية")

    def test_local_content_authoring(self):
        visit = VisitService.create_visit(
            institution=self.institution,
            inspector=self.inspector,
            visit_date=datetime.date.today(),
            source_reference=self.ref
        )
        local_item = VisitService.add_local_content(
            visit=visit,
            title="بند محلي للزيارة",
            description="ملاحظة محلية",
            user=self.inspector
        )
        self.assertTrue(local_item.is_local)
        self.assertTrue(local_item.is_selected)
        self.assertEqual(visit.items.filter(is_local=True).count(), 1)
