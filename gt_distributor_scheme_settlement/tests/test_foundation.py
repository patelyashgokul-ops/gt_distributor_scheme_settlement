from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestDistributorSchemeFoundation(AccountTestInvoicingCommon):
    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() | cls.env.ref(
            "gt_distributor_scheme_settlement.group_scheme_manager"
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({
            "name": "Scheme Test Company B",
            "currency_id": cls.company_a.currency_id.id,
        })
        cls.product_a = cls._create_product(
            name="Scheme Test Qualifying Product",
            company_id=cls.company_a.id,
            uom_id=cls.uom_unit.id,
        )
        cls.reward_a = cls._create_product(
            name="Scheme Test Reward Product",
            company_id=cls.company_a.id,
            uom_id=cls.uom_unit.id,
        )
        cls.product_b = cls._create_product(
            name="Scheme Test Company B Product",
            company_id=cls.company_b.id,
            uom_id=cls.uom_unit.id,
        )
        cls.distributor = cls.env["res.partner"].create({
            "name": "Scheme Test Distributor",
            "vat": "P01TESTVAT",
        })
        cls.scheme = cls.env["gt.distributor.scheme"].sudo().create({
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
                cls.env.ref("account.group_account_readonly").id,
            ])],
        })
        cls.internal_user = cls.env["res.users"].create({
            "name": "Scheme Test Unassigned User",
            "login": "scheme-foundation-unassigned",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def _preview(self, date_start="2026-01-01", date_end="2026-01-31", as_of=None,
                 scheme=None, distributor=None, user=None):
        return self.env["gt.distributor.scheme.calculator"].with_user(user or self.manager).calculate_eligibility(
            (scheme or self.scheme).id,
            (distributor or self.distributor).id,
            date_start,
            date_end,
            as_of or fields.Datetime.now(),
        )

    def _basic_slab(self, minimum=1, maximum=False, reward=1, scheme=None):
        return self.env["gt.distributor.scheme.slab"].create({
            "scheme_id": (scheme or self.scheme).id,
            "minimum_quantity": minimum,
            "maximum_quantity": maximum,
            "reward_quantity": reward,
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

    def test_posted_invoice_refund_uom_conversion_and_highest_slab(self):
        self.scheme.write({"qualifying_uom_id": self.uom_dozen.id})
        period = self.env["gt.distributor.scheme.period"].create({
            "name": "January 2026 Calculation",
            "scheme_id": self.scheme.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
        })
        slab_low = self.env["gt.distributor.scheme.slab"].create({
            "scheme_id": self.scheme.id,
            "minimum_quantity": 5,
            "maximum_quantity": 8,
            "reward_quantity": 1,
        })
        slab_high = self.env["gt.distributor.scheme.slab"].create({
            "scheme_id": self.scheme.id,
            "minimum_quantity": 8,
            "maximum_quantity": 12,
            "reward_quantity": 2,
        })
        self.env["gt.distributor.scheme.slab"].create({
            "scheme_id": self.scheme.id,
            "minimum_quantity": 12,
            "reward_quantity": 4,
        })

        invoice = self._create_invoice_one_line(
            product_id=self.product_a,
            quantity=120,
            invoice_date="2026-01-10",
            partner_id=self.distributor.id,
            post=True,
        )
        self._create_invoice_one_line(
            product_id=self.product_a,
            quantity=600,
            invoice_date="2026-01-11",
            partner_id=self.distributor.id,
            post=False,
        )
        self._create_invoice_one_line(
            move_type="out_refund",
            product_id=self.product_a,
            quantity=24,
            invoice_date="2026-01-20",
            partner_id=self.distributor.id,
            reversed_entry_id=invoice.id,
            post=True,
        )

        result = self.env["gt.distributor.scheme.calculator"].with_user(self.manager).calculate_entitlement(
            self.scheme.id, self.distributor.id, period.id
        )
        self.assertEqual(result["status"], "qualified")
        self.assertAlmostEqual(result["qualifying_quantity"], 8.0)
        self.assertEqual(result["slab_id"], slab_high.id)
        self.assertNotEqual(result["slab_id"], slab_low.id)
        self.assertEqual(result["reward_quantity"], 2)
        self.assertEqual(len(result["source_lines"]), 1)
        self.assertEqual(len(result["refund_lines"]), 1)
        self.assertEqual(result["refund_lines"][0]["reversed_entry_id"], invoice.id)

    def test_preview_excludes_zero_and_fully_discounted_lines(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, price_unit=20,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(product_id=self.product_a, quantity=100, price_unit=0,
                                      invoice_date="2026-01-11", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(product_id=self.product_a, quantity=50, price_unit=20, discount=100,
                                      invoice_date="2026-01-12", partner_id=self.distributor.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "ELIGIBLE")
        self.assertEqual(result["gross_quantity"], 10)
        self.assertEqual(result["invoice_count"], 1)
        self.assertEqual(len([row for row in result["invoice_sources"] if row["line_classification"] == "ZERO_VALUE"]), 2)

    def test_multiple_partial_credit_notes_and_late_refund_attribution(self):
        self.scheme.write({"qualifying_uom_id": self.uom_dozen.id})
        self._basic_slab(minimum=1, maximum=8, reward=1)
        self._basic_slab(minimum=8, maximum=12, reward=2)
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=120,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        first = self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=12,
                                              invoice_date="2026-01-20", partner_id=self.distributor.id,
                                              reversed_entry_id=invoice.id, post=True)
        second = self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=12,
                                               invoice_date="2026-02-05", partner_id=self.distributor.id,
                                               reversed_entry_id=invoice.id, post=True)
        result = self._preview(as_of=fields.Datetime.now())
        self.assertEqual(result["calculation_status"], "ELIGIBLE")
        self.assertAlmostEqual(result["gross_quantity"], 10)
        self.assertAlmostEqual(result["refund_quantity"], 2)
        self.assertAlmostEqual(result["net_quantity"], 8)
        self.assertEqual(result["refund_count"], 2)
        self.assertTrue(any(row["move_id"] == second.id and row.get("late_refund") for row in result["refund_sources"]))
        self.assertTrue(any(item["code"] == "LATE_REFUND" and item["severity"] == "WARNING" for item in result["exceptions"]))
        self.assertNotIn(first.id, {row["move_id"] for row in result["invoice_sources"]})

    def test_unlinked_refund_is_a_blocking_preview_not_a_guess(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=1,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("UNATTRIBUTED_REFUND", {item["code"] for item in result["exceptions"]})

    def test_ambiguous_multi_line_refund_attribution_blocks(self):
        self._basic_slab()
        invoice = self._create_invoice(
            invoice_date="2026-01-10", partner_id=self.distributor.id, post=True,
            invoice_line_ids=[
                self._prepare_invoice_line(product_id=self.product_a, quantity=10),
                self._prepare_invoice_line(product_id=self.product_a, quantity=10),
            ],
        )
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=2,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id,
                                      reversed_entry_id=invoice.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("AMBIGUOUS_REFUND_LINE_ATTRIBUTION", {item["code"] for item in result["exceptions"]})

    def test_child_contact_identity_matches_p02_commercial_partner_policy(self):
        self._basic_slab()
        child = self.env["res.partner"].create({"name": "Distributor Invoice Contact", "parent_id": self.distributor.id, "type": "invoice"})
        self._create_invoice_one_line(product_id=self.product_a, quantity=7,
                                      invoice_date="2026-01-10", partner_id=child.id, post=True)
        result = self._preview()
        self.assertEqual(result["gross_quantity"], 7)
        self.assertEqual(result["invoice_count"], 1)

    def test_preview_fingerprint_is_stable_and_changes_after_source_edit(self):
        self._basic_slab()
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        cutoff = fields.Datetime.now()
        first = self._preview(as_of=cutoff)
        same = self._preview(as_of=cutoff)
        self.assertEqual(first["source_fingerprint"], same["source_fingerprint"])
        invoice.write({"ref": "P03 fingerprint evidence change"})
        changed = self._preview()
        self.assertNotEqual(first["source_fingerprint"], changed["source_fingerprint"])

    def test_backdated_source_after_cutoff_is_blocked(self):
        self._basic_slab()
        cutoff = fields.Datetime.now() - timedelta(days=1)
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        result = self._preview(as_of=cutoff)
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("SOURCE_CHANGED_AFTER_CUTOFF", {item["code"] for item in result["exceptions"]})

    def test_read_only_preview_does_not_create_claims(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        claims_before = self.env["gt.distributor.scheme.claim"].search_count([])
        result = self._preview()
        self.assertEqual(result["calculation_status"], "ELIGIBLE")
        self.assertEqual(self.env["gt.distributor.scheme.claim"].search_count([]), claims_before)

    def test_native_preview_wizard_and_server_side_role_check(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        wizard = self.env["gt.distributor.scheme.preview.wizard"].with_user(self.manager).create({
            "scheme_id": self.scheme.id,
            "distributor_id": self.distributor.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
            "as_of": fields.Datetime.now(),
        })
        action = wizard.action_calculate()
        self.assertEqual(wizard.calculation_status, "ELIGIBLE")
        self.assertEqual(action["res_id"], wizard.id)
        with self.assertRaises(AccessError):
            wizard.with_user(self.internal_user).action_calculate()

    def test_linked_out_of_period_refund_is_rejected_for_review(self):
        self.scheme.write({"qualifying_uom_id": self.uom_dozen.id})
        period = self.env["gt.distributor.scheme.period"].create({
            "name": "January 2026 Refund Review",
            "scheme_id": self.scheme.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
        })
        old_invoice = self._create_invoice_one_line(
            product_id=self.product_a,
            quantity=24,
            invoice_date="2025-12-20",
            partner_id=self.distributor.id,
            post=True,
        )
        self._create_invoice_one_line(
            move_type="out_refund",
            product_id=self.product_a,
            quantity=12,
            invoice_date="2026-01-20",
            partner_id=self.distributor.id,
            reversed_entry_id=old_invoice.id,
            post=True,
        )
        with self.assertRaises(UserError):
            self.env["gt.distributor.scheme.calculator"].with_user(self.manager).calculate_entitlement(
                self.scheme.id, self.distributor.id, period.id
            )
        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme.slab"].create({
                "scheme_id": self.scheme.id,
                "minimum_quantity": 10,
                "maximum_quantity": 10,
                "reward_quantity": 1,
            })

    def test_company_consistency(self):
        with self.assertRaises((ValidationError, AccessError, UserError)):
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
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme.calculator"].with_user(self.internal_user).calculate_entitlement(1, 1, 1)

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
