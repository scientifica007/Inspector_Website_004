import datetime
from django.core.management.base import BaseCommand
from inspection.models import User, Institution, NodeType
from inspection.services.reference_service import ReferenceService
from inspection.services.visit_service import VisitService
from inspection.services.governance_execution_services import GuideService, AssignmentService


class Command(BaseCommand):
    help = "Seeds initial demo data for testing Inspector_Website_004"

    def handle(self, *args, **options):
        self.stdout.write("جاري إنشاء البيانات النموذجية (Demo Seed Data)...")

        # Users
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"role": User.Role.ADMIN, "is_staff": True, "is_superuser": True}
        )
        admin_user.set_password("admin123")
        admin_user.save()

        inspector_user, _ = User.objects.get_or_create(
            username="inspector",
            defaults={"role": User.Role.INSPECTOR}
        )
        inspector_user.set_password("inspector123")
        inspector_user.save()

        # Institutions
        inst1, _ = Institution.objects.get_or_create(
            code="INS-001",
            defaults={"name": "المعهد الوطني المتخصص في التكوين المهني - الجزائر", "institution_type": "معهد متخصص", "city": "الجزائر", "address": "شارع 5 يوليو"}
        )
        inst2, _ = Institution.objects.get_or_create(
            code="INS-002",
            defaults={"name": "مركز التكوين المهني والتمهين - وهران", "institution_type": "مركز تكوين", "city": "وهران", "address": "حي الأمل"}
        )

        # Shared Reference
        nodes_data = [
            {
                "title": "فرع المتابعة البيداغوجية والوثائق الرسمية",
                "node_type": NodeType.BRANCH,
                "children": [
                    {
                        "title": "مواصفة الدفتر اليومي للتكوين",
                        "node_type": NodeType.SPECIFICATION,
                        "children": [
                            {
                                "title": "مراقبة توقيع المفتش والمدير على الدفتر اليومي",
                                "node_type": NodeType.CHECKLIST_ITEM
                            },
                            {
                                "title": "متابعة مطابقة التقدم في البرنامج الدراسي للرزنامة الرسمية",
                                "node_type": NodeType.CHECKLIST_ITEM
                            }
                        ]
                    }
                ]
            },
            {
                "title": "فرع السلامة والصيانة والتجهيزات",
                "node_type": NodeType.BRANCH,
                "children": [
                    {
                        "title": "تجهيزات المخابر والورشات",
                        "node_type": NodeType.SPECIFICATION,
                        "children": [
                            {
                                "title": "توفر وسائل الوقاية الفردية والسلامة داخل الورشة",
                                "node_type": NodeType.CHECKLIST_ITEM
                            }
                        ]
                    }
                ]
            }
        ]

        shared_ref = ReferenceService.create_reference(
            title="المرجع الوطني العام للتفتيش البيداغوجي 2025",
            description="مرجع مشترك رسمي معتمد من الإدارة المركزية.",
            user=admin_user,
            is_shared=True,
            nodes_data=nodes_data
        )

        # Guide
        all_nodes = list(shared_ref.nodes.all())
        target_ids = [n.node_id for n in all_nodes if n.node_type == NodeType.CHECKLIST_ITEM]
        guide = GuideService.create_guide(
            title="دليل السلامة والصيانة للورشات",
            description="دليل تفتيش موصى به لمتابعة أمن الورشات",
            reference=shared_ref,
            created_by=admin_user,
            entry_target_node_ids=target_ids
        )

        # Visit
        visit = VisitService.create_visit(
            institution=inst1,
            inspector=inspector_user,
            visit_date=datetime.date.today(),
            source_reference=shared_ref
        )

        self.stdout.write(self.style.SUCCESS("تمت العملية بنجاح!"))
        self.stdout.write("حساب المدير: admin / admin123")
        self.stdout.write("حساب المفتش: inspector / inspector123")
