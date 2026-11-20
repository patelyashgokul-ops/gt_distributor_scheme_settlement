from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDistributorSchemeFoundation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "Scheme Test Company B",
            "currency_id": cls.company_a.currency_id.id,
        })
        cls.product_a = cls.env["product.product"].create({
            "name": "Scheme Test Qualifying Product",
            "type": "consu",
            "company_id": cls.company_a.id,
        })
        cls.reward_a = cls.env["product.product"].create({
            "name": "Scheme Test Reward Product",
            "type": "consu",
            "company_id": cls.company_a.id,
        })
        cls.product_b = cls.env["product.product"].create({
            "name": "Scheme Test Company B Product",
            "type": "consu",
            "company_id": cls.company_b.id,
        })
        cls.distributor = cls.env["res.partner"].create({
            "name": "Scheme Test Distributor",
            "vat": "P01TESTVAT",
        })
        cls.scheme = cls.env["gt.distributor.scheme"].create({
            "name": "Foundation Test Scheme",
            "code": "FOUNDATION-TEST",
            "company_id": cls.company_a.id,
            "qualifying_product_id": cls.product_a.id,
            "reward_product_id": cls.reward_a.id,
            "distributor_ids": [(4, cls.distributor.id)],
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "qualifying_uom_id": cls.product_a.uom_id.id,
        })
        cls.operator = cls.env["res.users"].create({
            "name": "Scheme Test Operator",
            "login": "scheme-foundation-operator",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("gt_distributor_scheme_settlement.group_scheme_operator").id,
            ])],
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Scheme Test Manager",
            "login": "scheme-foundation-manager",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("gt_distributor_scheme_settlement.group_scheme_manager").id,
            ])],
        })
        cls.internal_user = cls.env["res.users"].create({
            "name": "Scheme Test Unassigned User",
            "login": "scheme-foundation-unassigned",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_required_model_fields(self):
        required = {
            "gt.distributor.scheme": {"name", "code", "company_id", "qualifying_product_id", "reward_product_id", "distributor_ids", "date_start", "date_end", "qualifying_uom_id"},
            "gt.distributor.scheme.slab": {"scheme_id", "minimum_quantity", "maximum_quantity", "reward_quantity"},
            "gt.distributor.scheme.period": {"scheme_id", "date_start", "date_end"},
            "gt.distributor.scheme.claim": {"scheme_id", "distributor_id", "period_id", "company_id", "entitlement_quantity", "approved_by_id", "approved_at", "fulfillment_order_id", "fulfillment_picking_ids"},
            "gt.distributor.scheme.claim.source": {"claim_id", "move_id", "invoice_line_id", "snapshot_payload"},
            "gt.distributor.scheme.claim.adjustment": {"claim_id", "quantity_delta", "reason"},
            "gt.distributor.scheme.audit": {"company_id", "event_type", "actor_id", "event_date", "evidence"},
        }
        for model_name, field_names in required.items():
            self.assertTrue(field_names.issubset(self.env[model_name]._fields), model_name)

    def test_invalid_scheme_dates_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.scheme.write({"date_start": "2026-12-31", "date_end": "2026-01-01"})

    def test_unimplemented_lifecycle_and_metadata_cannot_be_forged(self):
        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme"].create({
                "name": "Premature Active Scheme",
                "code": "PREMATURE",
                "company_id": self.company_a.id,
                "qualifying_product_id": self.product_a.id,
                "reward_product_id": self.reward_a.id,
                "distributor_ids": [(4, self.distributor.id)],
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "qualifying_uom_id": self.product_a.uom_id.id,
                "state": "active",
            })

        period = self.env["gt.distributor.scheme.period"].create({
            "name": "January 2026",
            "scheme_id": self.scheme.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
        })
        with self.assertRaises(ValidationError):
            period.write({"state": "closed"})

        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme.claim"].create({
                "name": "Forged Approval",
                "scheme_id": self.scheme.id,
                "distributor_id": self.distributor.id,
                "period_id": period.id,
                "company_id": self.company_a.id,
                "entitlement_quantity": 1,
                "state": "approved",
                "approved_by_id": self.manager.id,
            })

    def test_invalid_slab_quantities_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme.slab"].create({
                "scheme_id": self.scheme.id,
                "minimum_quantity": 0,
                "reward_quantity": 1,
            })
        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme.slab"].create({
                "scheme_id": self.scheme.id,
                "minimum_quantity": 10,
                "maximum_quantity": 10,
                "reward_quantity": 1,
            })

    def test_company_consistency(self):
        with self.assertRaises((ValidationError, AccessError)):
            self.env["gt.distributor.scheme"].create({
                "name": "Invalid Cross Company Scheme",
                "code": "CROSS-TEST",
                "company_id": self.company_a.id,
                "qualifying_product_id": self.product_b.id,
                "reward_product_id": self.reward_a.id,
                "distributor_ids": [(4, self.distributor.id)],
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "qualifying_uom_id": self.product_a.uom_id.id,
            })

    def test_acl_access_boundaries(self):
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme"].with_user(self.internal_user).search([])
        self.assertEqual(self.env["gt.distributor.scheme"].with_user(self.operator).search_count([]), 1)
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme"].with_user(self.operator).create({"name": "Forbidden"})

    def test_company_record_rule_isolation_and_relational_write_guard(self):
        other_scheme = self.env["gt.distributor.scheme"].create({
            "name": "Company B Scheme",
            "code": "COMPANY-B-TEST",
            "company_id": self.company_b.id,
            "qualifying_product_id": self.product_b.id,
            "reward_product_id": self.product_b.id,
            "distributor_ids": [(4, self.distributor.id)],
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "qualifying_uom_id": self.product_b.uom_id.id,
        })
        scoped = self.env["gt.distributor.scheme"].with_user(self.operator)
        self.assertIn(self.scheme, scoped.search([]))
        self.assertNotIn(other_scheme, scoped.search([]))
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme"].with_user(self.manager).browse(self.scheme.id).write({"company_id": self.company_b.id})

    def test_audit_modification_is_forbidden_even_for_manager(self):
        audit = self.env["gt.distributor.scheme.audit"].create({
            "company_id": self.company_a.id,
            "scheme_id": self.scheme.id,
            "event_type": "foundation_test",
            "evidence": {"source": "test"},
        })
        with self.assertRaises(AccessError):
            audit.with_user(self.manager).write({"event_type": "changed"})
        with self.assertRaises(AccessError):
            audit.with_user(self.manager).unlink()

    def test_xml_views_and_menu_references_load(self):
        refs = [
            "view_distributor_scheme_list", "view_distributor_scheme_form", "view_distributor_scheme_search",
            "view_distributor_scheme_slab_list", "view_distributor_scheme_slab_form",
            "view_distributor_scheme_period_list", "view_distributor_scheme_period_form",
            "view_distributor_scheme_claim_list", "view_distributor_scheme_claim_form",
            "view_distributor_scheme_claim_search", "menu_distributor_scheme_root", "menu_distributor_schemes",
            "menu_distributor_slabs", "menu_distributor_periods", "menu_distributor_claims", "menu_distributor_configuration",
        ]
        for xml_id in refs:
            self.assertTrue(self.env.ref(f"gt_distributor_scheme_settlement.{xml_id}"), xml_id)
