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
        cls.other_product_a = cls._create_product(
            name="Scheme Test Non Qualifying Product",
            company_id=cls.company_a.id,
            uom_id=cls.uom_unit.id,
        )
        cls.shared_product = cls._create_product(
            name="Scheme Test Shared Product",
            company_id=False,
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
                cls.env.ref("account.group_account_readonly").id,
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
        cls.independent_manager = cls.env["res.users"].create({
            "name": "Scheme Test Independent Approver",
            "login": "scheme-foundation-independent-approver",
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

    def _p04_scheme_period(self, code="P04-TEST", distributors=None, slabs=((1, False, 1),)):
        distributors = distributors or self.distributor
        scheme = self.env["gt.distributor.scheme"].create({
            "name": "P04 Settlement Test Scheme",
            "code": code,
            "company_id": self.company_a.id,
            "qualifying_product_id": self.product_a.id,
            "reward_product_id": self.reward_a.id,
            "distributor_ids": [(6, 0, distributors.ids)],
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "qualifying_uom_id": self.product_a.uom_id.id,
        })
        for minimum, maximum, reward in slabs:
            self.env["gt.distributor.scheme.slab"].create({
                "scheme_id": scheme.id,
                "minimum_quantity": minimum,
                "maximum_quantity": maximum,
                "reward_quantity": reward,
            })
        scheme.with_user(self.manager).action_activate()
        period = self.env["gt.distributor.scheme.period"].with_user(self.manager).create({
            "name": "January 2026 P04 Test Period",
            "scheme_id": scheme.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
            "calculation_cutoff": fields.Datetime.now(),
        })
        return scheme, period

    def _close_p04(self, period):
        period.with_user(self.manager).write({"calculation_cutoff": fields.Datetime.now()})
        return period.with_user(self.manager).action_close_period()

    def test_required_model_fields(self):
        required = {
            "gt.distributor.scheme": {"name", "code", "company_id", "qualifying_product_id", "reward_product_id", "distributor_ids", "date_start", "date_end", "qualifying_uom_id"},
            "gt.distributor.scheme.slab": {"scheme_id", "minimum_quantity", "maximum_quantity", "reward_quantity"},
            "gt.distributor.scheme.period": {"scheme_id", "date_start", "date_end"},
            "gt.distributor.scheme.claim": {"scheme_id", "distributor_id", "period_id", "company_id", "entitlement_quantity", "approved_by_id", "approved_at", "fulfillment_order_id", "fulfillment_picking_ids"},
            "gt.distributor.scheme.claim.source": {"claim_id", "move_id", "invoice_line_id", "snapshot_payload"},
            "gt.distributor.scheme.claim.adjustment": {"claim_id", "quantity_delta", "reason"},
            "gt.distributor.scheme.audit": {"company_id", "event_type", "actor_id", "event_date", "evidence"},
            "gt.distributor.scheme.preview.wizard": {"scheme_id", "distributor_id", "date_start", "date_end", "as_of", "calculation_status", "source_fingerprint"},
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

        with self.assertRaises(AccessError):
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

    def test_customer_invoice_company_product_and_invoice_date_filters(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=5, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, company_id=self.company_a.id, post=True)
        self._create_invoice_one_line(product_id=self.other_product_a, quantity=50, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, company_id=self.company_a.id, post=True)
        self._create_invoice_one_line(product_id=self.product_a, quantity=70, invoice_date="2026-02-10",
                                      partner_id=self.distributor.id, company_id=self.company_a.id, post=True)
        self._create_invoice_one_line(move_type="in_invoice", product_id=self.product_a, quantity=90,
                                      invoice_date="2026-01-15", partner_id=self.distributor.id,
                                      company_id=self.company_a.id, post=True)
        result = self._preview()
        self.assertEqual(result["gross_quantity"], 5)
        self.assertEqual(result["invoice_count"], 1)

    def test_same_shared_product_invoice_in_other_company_is_isolated(self):
        self._basic_slab()
        self.scheme.write({"qualifying_product_id": self.shared_product.id})
        self._create_invoice_one_line(product_id=self.shared_product, quantity=5, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, company_id=self.company_a.id, post=True)
        revenue = self.env["account.account"].create({
            "name": "Company B Scheme Revenue",
            "code": "B410001",
            "account_type": "income",
            "company_ids": [(6, 0, [self.company_b.id])],
        })
        receivable = self.env["account.account"].create({
            "name": "Company B Scheme Receivable",
            "code": "B110001",
            "account_type": "asset_receivable",
            "reconcile": True,
            "company_ids": [(6, 0, [self.company_b.id])],
        })
        self.distributor.with_company(self.company_b).property_account_receivable_id = receivable
        journal = self.env["account.journal"].create({
            "name": "Company B Sales",
            "type": "sale",
            "code": "BSALE",
            "company_id": self.company_b.id,
            "default_account_id": revenue.id,
        })
        invoice_b = self.env["account.move"].with_company(self.company_b).create({
            "move_type": "out_invoice",
            "company_id": self.company_b.id,
            "journal_id": journal.id,
            "partner_id": self.distributor.id,
            "invoice_date": "2026-01-11",
            "invoice_line_ids": [self._prepare_invoice_line(
                product_id=self.shared_product, quantity=500, account_id=revenue.id,
            )],
        })
        invoice_b.action_post()
        result = self._preview()
        self.assertEqual(result["gross_quantity"], 5)
        self.assertNotIn(invoice_b.id, {row["move_id"] for row in result["invoice_sources"]})

    def test_unposted_credit_note_does_not_reduce_preview(self):
        self._basic_slab()
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=5,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id,
                                      reversed_entry_id=invoice.id, post=False)
        result = self._preview()
        self.assertEqual(result["refund_quantity"], 0)
        self.assertEqual(result["gross_quantity"], 10)

    def test_incompatible_uom_blocks_eligibility(self):
        self._basic_slab()
        kg = self.env.ref("uom.product_uom_kgm")
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id,
                                                post=False)
        product_line = invoice.invoice_line_ids
        product_line.write({"product_uom_id": kg.id})
        invoice.action_post()
        result = self._preview()
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("INCOMPATIBLE_UOM", {item["code"] for item in result["exceptions"]})

    def test_quantity_just_below_exclusive_boundary_does_not_round_up(self):
        low = self._basic_slab(minimum=1, maximum=200, reward=1)
        high = self._basic_slab(minimum=200, reward=5)
        result = self.env["gt.distributor.scheme.calculator"].with_user(self.manager)._select_highest_slab(
            self.scheme, 199.999999
        )
        self.assertEqual(result, low)
        self.assertNotEqual(result, high)

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

    def test_posted_invoice_reversing_a_credit_note_restores_its_quantity(self):
        self._basic_slab()
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=20,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        credit = self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=5,
                                               invoice_date="2026-01-15", partner_id=self.distributor.id,
                                               reversed_entry_id=invoice.id, post=True)
        reversal = self._create_invoice_one_line(move_type="out_invoice", product_id=self.product_a, quantity=5,
                                                 invoice_date="2026-01-20", partner_id=self.distributor.id,
                                                 reversed_entry_id=credit.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "ELIGIBLE")
        self.assertEqual(result["gross_quantity"], 20)
        self.assertEqual(result["refund_quantity"], 0)
        self.assertEqual(result["net_quantity"], 20)
        self.assertIn(reversal.id, {row["move_id"] for row in result["refund_sources"]})

    def test_unlinked_refund_is_a_blocking_preview_not_a_guess(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=1,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("UNATTRIBUTED_REFUND", {item["code"] for item in result["exceptions"]})

    def test_attributed_credit_note_exceeding_original_quantity_blocks(self):
        self._basic_slab()
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=5,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=6,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id,
                                      reversed_entry_id=invoice.id, post=True)
        result = self._preview()
        self.assertEqual(result["calculation_status"], "BLOCKED")
        self.assertIn("REFUND_EXCEEDS_PURCHASE", {item["code"] for item in result["exceptions"]})

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

    def test_preview_fingerprint_is_stable_and_changes_after_new_source(self):
        self._basic_slab()
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        cutoff = fields.Datetime.now()
        first = self._preview(as_of=cutoff)
        same = self._preview(as_of=cutoff)
        self.assertEqual(first["source_fingerprint"], same["source_fingerprint"])
        self._create_invoice_one_line(product_id=self.product_a, quantity=3,
                                      invoice_date="2026-01-15", partner_id=self.distributor.id, post=True)
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

    def test_preview_handles_one_thousand_relevant_invoice_lines(self):
        """Exercise a realistic line volume through real accounting ORM records."""
        self._basic_slab(minimum=1, reward=1)
        lines = [
            self._prepare_invoice_line(product_id=self.product_a, quantity=1)
            for _index in range(1000)
        ]
        invoice = self._create_invoice(
            invoice_date="2026-01-10",
            post=True,
            partner_id=self.distributor.id,
            invoice_line_ids=lines,
        )
        result = self._preview()
        matching_sources = [
            row for row in result["invoice_sources"] if row["move_id"] == invoice.id
        ]
        self.assertEqual(result["calculation_status"], "ELIGIBLE")
        self.assertEqual(result["gross_quantity"], 1000)
        self.assertEqual(len(matching_sources), 1000)
        self.assertEqual(result["invoice_count"], 1)

    def test_preview_wizard_results_cannot_be_forged_by_orm_write(self):
        wizard = self.env["gt.distributor.scheme.preview.wizard"].with_user(self.manager).create({
            "scheme_id": self.scheme.id,
            "distributor_id": self.distributor.id,
            "date_start": "2026-01-01",
            "date_end": "2026-01-31",
            "as_of": fields.Datetime.now(),
        })
        with self.assertRaises(AccessError):
            wizard.write({"calculation_status": "ELIGIBLE", "reward_quantity": 999})

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
            self.env["gt.distributor.scheme.calculator"].with_user(self.manager).calculate_eligibility(
                other_scheme.id, self.distributor.id, "2026-01-01", "2026-01-31", fields.Datetime.now()
            )
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme"].with_user(self.manager).browse(self.scheme.id).write({"company_id": self.company_b.id})

    def test_audit_modification_is_forbidden_even_for_manager(self):
        self._basic_slab()
        self.scheme.with_user(self.manager).action_activate()
        audit = self.env["gt.distributor.scheme.audit"].search([("scheme_id", "=", self.scheme.id)], limit=1)
        self.assertTrue(audit)
        with self.assertRaises(AccessError):
            audit.with_user(self.manager).write({"event_type": "changed"})
        with self.assertRaises(AccessError):
            audit.with_user(self.manager).unlink()

    def test_p04_close_generates_claim_snapshot_sources_and_audit(self):
        scheme, period = self._p04_scheme_period()
        invoice = self._create_invoice_one_line(
            product_id=self.product_a, quantity=25, invoice_date="2026-01-10",
            partner_id=self.distributor.id, post=True,
        )
        invoice_write_date = invoice.write_date
        claims_before = self.env["gt.distributor.scheme.claim"].search_count([])
        moves_before = self.env["account.move"].search_count([("company_id", "=", self.company_a.id)])
        pickings_before = self.env["stock.picking"].search_count([("company_id", "=", self.company_a.id)])
        self._close_p04(period)
        self.assertEqual(period.state, "closed")
        self.assertEqual(period.generated_claim_count, 1)
        self.assertEqual(period.eligible_distributor_count, 1)
        self.assertEqual(period.source_count, 1)
        claim = period.claim_ids
        self.assertEqual(len(claim), 1)
        self.assertEqual(claim.state, "draft")
        self.assertEqual(claim.company_id, self.company_a)
        self.assertEqual(claim.scheme_id, scheme)
        self.assertEqual(claim.distributor_id, self.distributor)
        self.assertEqual(claim.gross_quantity, 25)
        self.assertEqual(claim.refund_quantity, 0)
        self.assertEqual(claim.net_quantity, 25)
        self.assertEqual(claim.reward_quantity, 1)
        self.assertEqual(claim.entitlement_quantity, 1)
        self.assertEqual(claim.snapshot_payload["period"]["start"], "2026-01-01")
        self.assertEqual(claim.snapshot_payload["sources"][0]["invoice_line_id"], invoice.invoice_line_ids.id)
        self.assertEqual(claim._hash_snapshot(claim.snapshot_payload), claim.snapshot_hash)
        self.assertEqual(len(claim.source_ids), 1)
        self.assertEqual(claim.source_ids.quantity, 25)
        self.assertEqual(claim.source_ids.source_role, "invoice")
        self.assertEqual(invoice.write_date, invoice_write_date)
        self.assertEqual(self.env["account.move"].search_count([("company_id", "=", self.company_a.id)]), moves_before)
        self.assertEqual(self.env["stock.picking"].search_count([("company_id", "=", self.company_a.id)]), pickings_before)
        self.assertEqual(self.env["gt.distributor.scheme.claim"].search_count([]), claims_before + 1)
        events = self.env["gt.distributor.scheme.audit"].search([("scheme_id", "=", scheme.id)])
        self.assertIn("period_closed", events.mapped("event_type"))
        self.assertIn("claim_generated", events.mapped("event_type"))

    def test_p04_noneligible_distributor_is_in_period_snapshot_without_claim(self):
        _scheme, period = self._p04_scheme_period(code="P04-NONELIGIBLE")
        self._close_p04(period)
        self.assertEqual(period.state, "closed")
        self.assertEqual(period.generated_claim_count, 0)
        self.assertEqual(period.claim_ids, self.env["gt.distributor.scheme.claim"])
        self.assertEqual(period.close_summary["distributors"][0]["calculation_status"], "NOT_ELIGIBLE")

    def test_p04_blocked_calculation_rolls_back_period_close(self):
        scheme, period = self._p04_scheme_period(code="P04-BLOCKED")
        invoice = self._create_invoice_one_line(
            product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
            partner_id=self.distributor.id, post=True,
        )
        self._create_invoice_one_line(
            move_type="out_refund", product_id=self.product_a, quantity=2,
            invoice_date="2026-01-20", partner_id=self.distributor.id, post=True,
        )
        with self.assertRaises(UserError):
            self._close_p04(period)
        self.assertEqual(period.state, "open")
        self.assertFalse(period.closing_cutoff)
        self.assertEqual(period.generated_claim_count, 0)
        self.assertFalse(period.claim_ids)
        self.assertEqual(self.env["gt.distributor.scheme.claim.source"].search_count([("scheme_id", "=", scheme.id)]), 0)
        self.assertEqual(self.env["gt.distributor.scheme.audit"].search_count([
            ("scheme_id", "=", scheme.id), ("event_type", "=", "period_closed")
        ]), 0)

    def test_p04_repeated_close_is_idempotent_and_period_is_immutable(self):
        _scheme, period = self._p04_scheme_period(code="P04-IDEMPOTENT")
        self._create_invoice_one_line(
            product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
            partner_id=self.distributor.id, post=True,
        )
        result = self._close_p04(period)
        claim_ids = period.claim_ids.ids
        self.assertEqual(period.with_user(self.manager).action_close_period(), result)
        self.assertEqual(period.claim_ids.ids, claim_ids)
        with self.assertRaises(ValidationError):
            period.write({"state": "open"})
        with self.assertRaises(ValidationError):
            period.write({"date_end": "2026-02-01"})
        with self.assertRaises(UserError):
            period.unlink()

    def test_p04_period_requires_manager_explicit_past_cutoff_and_ended_period(self):
        _scheme, period = self._p04_scheme_period(code="P04-AUTH")
        with self.assertRaises(AccessError):
            period.with_user(self.operator).action_close_period()
        period.with_user(self.manager).write({"calculation_cutoff": False})
        with self.assertRaises(ValidationError):
            period.with_user(self.manager).action_close_period()
        future_period = self.env["gt.distributor.scheme.period"].with_user(self.manager).create({
            "name": "Future P04 Period", "scheme_id": period.scheme_id.id,
            "date_start": "2026-12-01", "date_end": "2026-12-31",
            "calculation_cutoff": fields.Datetime.now(),
        })
        with self.assertRaises(UserError):
            future_period.with_user(self.manager).action_close_period()

    def test_p04_direct_claim_creation_and_financial_writes_are_blocked(self):
        scheme, period = self._p04_scheme_period(code="P04-CLAIM-GUARD")
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme.claim"].with_user(self.manager).create({
                "scheme_id": scheme.id, "period_id": period.id, "company_id": self.company_a.id,
                "distributor_id": self.distributor.id, "entitlement_quantity": 1,
                "state": "draft",
            })
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        with self.assertRaises(AccessError):
            claim.write({"entitlement_quantity": 500})
        with self.assertRaises(AccessError):
            claim.write({"state": "approved"})
        with self.assertRaises(UserError):
            claim.copy()
        with self.assertRaises(UserError):
            claim.unlink()
        with self.assertRaises(AccessError):
            self.env["gt.distributor.scheme.audit"].with_user(self.manager).create({
                "company_id": self.company_a.id, "scheme_id": scheme.id,
                "event_type": "forged_period_close", "evidence": {"closed": True},
            })

    def test_p04_revalidation_current_then_submit_and_start_review(self):
        _scheme, period = self._p04_scheme_period(code="P04-LIFECYCLE")
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        validation = claim.with_user(self.manager).action_revalidate_sources()
        self.assertEqual(validation["status"], "current")
        self.assertEqual(claim.source_validation_status, "current")
        self.assertTrue(claim.with_user(self.operator).action_submit())
        self.assertEqual(claim.state, "submitted")
        self.assertTrue(claim.with_user(self.manager).action_start_review())
        self.assertEqual(claim.state, "under_review")
        self.assertTrue(claim.submitted_at)
        self.assertTrue(claim.reviewed_at)

    def test_p04_new_backdated_invoice_marks_claim_stale_without_rewriting_snapshot(self):
        scheme, period = self._p04_scheme_period(code="P04-STALE-NEW", slabs=((1, 100, 1), (100, False, 2)))
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        old_hash, old_quantity, old_reward = claim.snapshot_hash, claim.net_quantity, claim.reward_quantity
        self._create_invoice_one_line(product_id=self.product_a, quantity=100, invoice_date="2026-01-12",
                                      partner_id=self.distributor.id, post=True)
        validation = claim.with_user(self.manager).action_revalidate_sources()
        self.assertEqual(validation["status"], "stale")
        self.assertEqual(validation["change_category"], "source_changed_entitlement_changed")
        self.assertEqual(validation["original"]["reward_quantity"], old_reward)
        self.assertEqual(validation["current"]["reward_quantity"], 2)
        self.assertEqual(claim.net_quantity, old_quantity)
        self.assertEqual(claim.snapshot_hash, old_hash)
        response = claim.with_user(self.operator).action_submit()
        self.assertEqual(response["type"], "ir.actions.client")
        self.assertEqual(claim.state, "draft")
        self.assertEqual(claim.source_validation_status, "stale")
        self.assertEqual(claim.scheme_id, scheme)

    def test_p04_source_change_without_reward_change_is_classified(self):
        _scheme, period = self._p04_scheme_period(code="P04-STALE-SAME")
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        self._create_invoice_one_line(product_id=self.product_a, quantity=1, invoice_date="2026-01-11",
                                      partner_id=self.distributor.id, post=True)
        validation = claim.with_user(self.manager).action_revalidate_sources()
        self.assertEqual(validation["status"], "stale")
        self.assertEqual(validation["change_category"], "source_changed_entitlement_unchanged")
        self.assertEqual(validation["original"]["reward_quantity"], validation["current"]["reward_quantity"])

    def test_p04_late_refund_marks_original_claim_stale_and_blocked_refund_is_reported(self):
        _scheme, period = self._p04_scheme_period(code="P04-STALE-REFUND")
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=2,
                                      invoice_date="2026-02-05", partner_id=self.distributor.id,
                                      reversed_entry_id=invoice.id, post=True)
        validation = claim.with_user(self.manager).action_revalidate_sources()
        self.assertEqual(validation["status"], "stale")
        self.assertEqual(validation["current"]["refund_quantity"], 2)
        self.assertEqual(claim.refund_quantity, 0)

    def test_p04_duplicate_cross_scheme_source_allocation_is_rejected(self):
        _scheme_a, period_a = self._p04_scheme_period(code="P04-ALLOC-A")
        _scheme_b, period_b = self._p04_scheme_period(code="P04-ALLOC-B")
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period_a)
        with self.assertRaises(UserError):
            period_b.with_user(self.manager).action_close_period()
        self.assertEqual(period_b.state, "open")
        self.assertEqual(period_b.claim_ids, self.env["gt.distributor.scheme.claim"])

    def test_p04_snapshot_payload_detects_tampering_and_source_rows_are_immutable(self):
        _scheme, period = self._p04_scheme_period(code="P04-SNAPSHOT-GUARD")
        self._create_invoice_one_line(product_id=self.product_a, quantity=10, invoice_date="2026-01-10",
                                      partner_id=self.distributor.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        source = claim.source_ids
        with self.assertRaises(AccessError):
            claim.write({"snapshot_payload": {"tampered": True}})
        with self.assertRaises(AccessError):
            source.write({"quantity": 999})
        with self.assertRaises(AccessError):
            source.unlink()
        self.assertTrue(claim._check_snapshot_integrity())

    def test_p04_period_overlap_and_adjacent_boundaries(self):
        scheme, _period = self._p04_scheme_period(code="P04-PERIOD-RANGES")
        adjacent = self.env["gt.distributor.scheme.period"].with_user(self.manager).create({
            "name": "Adjacent February Period", "scheme_id": scheme.id,
            "date_start": "2026-02-01", "date_end": "2026-02-28",
        })
        self.assertEqual(adjacent.date_start, fields.Date.to_date("2026-02-01"))
        with self.assertRaises(ValidationError):
            self.env["gt.distributor.scheme.period"].with_user(self.manager).create({
                "name": "Overlapping Period", "scheme_id": scheme.id,
                "date_start": "2026-01-31", "date_end": "2026-02-15",
            })

    def test_p04_draft_period_open_requires_manager(self):
        scheme, _period = self._p04_scheme_period(code="P04-OPEN")
        draft = self.env["gt.distributor.scheme.period"].with_user(self.manager).create({
            "name": "Draft P04 Period", "scheme_id": scheme.id, "state": "draft",
            "date_start": "2026-03-01", "date_end": "2026-03-31",
        })
        with self.assertRaises(AccessError):
            draft.with_user(self.operator).action_open_period()
        draft.with_user(self.manager).action_open_period()
        self.assertEqual(draft.state, "open")
        self.assertTrue(self.env["gt.distributor.scheme.audit"].search_count([
            ("scheme_id", "=", scheme.id), ("event_type", "=", "period_opened")
        ]))

    def test_p04_active_scheme_and_slab_configuration_are_immutable(self):
        scheme, _period = self._p04_scheme_period(code="P04-ACTIVE-CONFIG")
        with self.assertRaises(ValidationError):
            scheme.write({"qualifying_product_id": self.other_product_a.id})
        with self.assertRaises(ValidationError):
            scheme.slab_ids.write({"reward_quantity": 500})
        with self.assertRaises(ValidationError):
            scheme.slab_ids.unlink()

    def test_p04_refund_quantity_is_saved_as_negative_source_contribution(self):
        _scheme, period = self._p04_scheme_period(code="P04-REFUND-SOURCES")
        invoice = self._create_invoice_one_line(product_id=self.product_a, quantity=25,
                                                invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(move_type="out_refund", product_id=self.product_a, quantity=5,
                                      invoice_date="2026-01-20", partner_id=self.distributor.id,
                                      reversed_entry_id=invoice.id, post=True)
        self._close_p04(period)
        claim = period.claim_ids
        self.assertEqual(claim.gross_quantity, 25)
        self.assertEqual(claim.refund_quantity, 5)
        self.assertEqual(claim.net_quantity, 20)
        self.assertEqual(len(claim.source_ids), 2)
        refund_source = claim.source_ids.filtered(lambda source: source.source_role == "refund")
        self.assertEqual(refund_source.quantity, -5)
        self.assertEqual(refund_source.origin_invoice_id, invoice)

    def test_p04_two_distributors_receive_separate_claims(self):
        second_distributor = self.env["res.partner"].create({
            "name": "Scheme Test Distributor Two", "vat": "P04DISTRICTWO",
        })
        second_distributor.with_company(self.company_a).property_account_receivable_id = self.distributor.with_company(self.company_a).property_account_receivable_id
        _scheme, period = self._p04_scheme_period(
            code="P04-MULTI-DIST", distributors=self.distributor | second_distributor,
        )
        self._create_invoice_one_line(product_id=self.product_a, quantity=10,
                                      invoice_date="2026-01-10", partner_id=self.distributor.id, post=True)
        self._create_invoice_one_line(product_id=self.product_a, quantity=20,
                                      invoice_date="2026-01-11", partner_id=second_distributor.id, post=True)
        self._close_p04(period)
        self.assertEqual(period.generated_claim_count, 2)
        self.assertEqual(set(period.claim_ids.mapped("distributor_id").ids), {self.distributor.id, second_distributor.id})
        self.assertEqual(sorted(period.claim_ids.mapped("net_quantity")), [10, 20])

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
