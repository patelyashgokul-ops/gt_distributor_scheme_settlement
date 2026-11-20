import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare

from .service_tokens import CLAIM_CREATE_TOKEN, CLAIM_WRITE_TOKEN


class DistributorSchemeClaim(models.Model):
    _name = "gt.distributor.scheme.claim"
    _description = "Distributor Scheme Settlement Claim"
    _inherit = ["gt.distributor.scheme.company.guard.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default="New", copy=False, index=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", required=True, check_company=True, ondelete="restrict", index=True)
    distributor_id = fields.Many2one("res.partner", required=True, check_company=True, domain=[("is_company", "=", True)], index=True)
    period_id = fields.Many2one("gt.distributor.scheme.period", required=True, check_company=True, ondelete="restrict", index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)

    qualifying_product_id = fields.Many2one("product.product", required=True, check_company=True)
    qualifying_uom_id = fields.Many2one("uom.uom", required=True)
    gross_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    refund_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    net_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    slab_id = fields.Many2one("gt.distributor.scheme.slab", required=True, ondelete="restrict")
    reward_product_id = fields.Many2one("product.product", required=True, check_company=True)
    reward_uom_id = fields.Many2one("uom.uom", required=True)
    reward_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    entitlement_quantity = fields.Float(required=True, digits="Product Unit of Measure", help="Compatibility field equal to the original draft reward entitlement.")

    calculation_cutoff = fields.Datetime(required=True, readonly=True, copy=False)
    source_fingerprint = fields.Char(required=True, readonly=True, copy=False, index=True, help="Stable fingerprint of scoped source evidence; excludes the varying revalidation timestamp.")
    calculation_fingerprint = fields.Char(required=True, readonly=True, copy=False)
    snapshot_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    snapshot_version = fields.Integer(required=True, readonly=True, copy=False, default=1)
    snapshot_payload = fields.Json(required=True, readonly=True, copy=False)
    snapshot_json = fields.Text(compute="_compute_snapshot_json", string="Calculation Snapshot", readonly=True)
    source_evidence_count = fields.Integer(required=True, readonly=True, copy=False)
    calculation_snapshot_at = fields.Datetime(required=True, readonly=True, copy=False)
    originating_scheme_code = fields.Char(required=True, readonly=True, copy=False)
    created_by_id = fields.Many2one("res.users", required=True, readonly=True, copy=False)
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_at = fields.Datetime(readonly=True, copy=False)
    review_note = fields.Text(readonly=True, copy=False)
    source_validation_status = fields.Selection([
        ("current", "Current"), ("stale", "Stale"), ("blocked", "Blocked"),
    ], required=True, default="current", readonly=True, copy=False, index=True)
    source_change_category = fields.Selection([
        ("none", "No Change"),
        ("source_changed_entitlement_unchanged", "Source Changed, Entitlement Unchanged"),
        ("source_changed_entitlement_changed", "Source Changed, Entitlement Changed"),
        ("source_attribution_unresolved", "Source Attribution Unresolved"),
    ], required=True, default="none", readonly=True, copy=False)
    source_validation_at = fields.Datetime(readonly=True, copy=False)
    source_validation_result = fields.Json(readonly=True, copy=False)

    state = fields.Selection([
        ("draft", "Draft"), ("submitted", "Submitted"), ("under_review", "Under Review"),
        ("approved", "Approved"), ("rejected", "Rejected"),
        ("fulfillment_in_progress", "Fulfillment In Progress"), ("fulfilled", "Fulfilled"),
        ("settled", "Settled"), ("adjustment_required", "Adjustment Required"),
        ("cancelled", "Cancelled"),
    ], default="draft", required=True, copy=False, tracking=True, index=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    fulfillment_order_id = fields.Many2one("sale.order", readonly=True, copy=False, check_company=True)
    fulfillment_picking_ids = fields.Many2many("stock.picking", string="Fulfillment Transfers", readonly=True, copy=False)
    source_ids = fields.One2many("gt.distributor.scheme.claim.source", "claim_id", string="Source Evidence", readonly=True)
    invoice_source_ids = fields.One2many("gt.distributor.scheme.claim.source", "claim_id", string="Invoice Sources", domain=[("source_role", "=", "invoice")], readonly=True)
    refund_source_ids = fields.One2many("gt.distributor.scheme.claim.source", "claim_id", string="Refund Sources", domain=[("source_role", "=", "refund")], readonly=True)
    adjustment_ids = fields.One2many("gt.distributor.scheme.claim.adjustment", "claim_id", string="Adjustments", readonly=True)
    audit_ids = fields.One2many("gt.distributor.scheme.audit", "claim_id", string="Audit History", readonly=True)
    note = fields.Text()

    _claim_scheme_distributor_period_uniq = models.Constraint(
        "unique(scheme_id, distributor_id, period_id)",
        "Only one claim is allowed per scheme, distributor, and period.",
    )
    _claim_company_scope_uniq = models.Constraint(
        "unique(company_id, scheme_id, period_id, distributor_id)",
        "Only one claim is allowed per company, scheme, period, and distributor.",
    )

    _PROTECTED_FIELDS = {
        "name", "scheme_id", "distributor_id", "period_id", "company_id",
        "qualifying_product_id", "qualifying_uom_id", "gross_quantity", "refund_quantity",
        "net_quantity", "slab_id", "reward_product_id", "reward_uom_id", "reward_quantity",
        "entitlement_quantity", "calculation_cutoff", "source_fingerprint",
        "calculation_fingerprint", "snapshot_hash", "snapshot_version", "snapshot_payload",
        "source_evidence_count", "calculation_snapshot_at", "originating_scheme_code",
        "created_by_id", "submitted_by_id", "submitted_at", "reviewed_by_id", "reviewed_at",
        "review_note", "source_validation_status", "source_change_category",
        "source_validation_at", "source_validation_result", "state", "approved_by_id",
        "approved_at", "fulfillment_order_id", "fulfillment_picking_ids", "source_ids",
        "adjustment_ids", "audit_ids", "invoice_source_ids", "refund_source_ids",
    }

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_claim_create_token") is not CLAIM_CREATE_TOKEN:
            raise AccessError(_("Settlement claims can only be generated by the authorized period close service."))
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise ValidationError(_("Claims can only be generated in Draft state."))
            if vals.get("entitlement_quantity", 0) <= 0 or vals.get("reward_quantity", 0) <= 0:
                raise ValidationError(_("A settlement claim must have a positive calculated reward entitlement."))
            if {"approved_by_id", "approved_at", "fulfillment_order_id", "fulfillment_picking_ids"} & vals.keys():
                raise ValidationError(_("Approval and fulfillment metadata are reserved for later phases."))
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gt.distributor.scheme.claim") or "New"
            vals["created_by_id"] = self.env.user.id
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("_gt_claim_write_token") is CLAIM_WRITE_TOKEN:
            return super().write(vals)
        if self._PROTECTED_FIELDS.intersection(vals):
            raise AccessError(_("Claim calculation, lifecycle, allocation, and review fields are protected by the claim service."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Settlement claims are historical records and cannot be deleted."))

    def copy(self, default=None):
        raise UserError(_("Claims cannot be copied because that could duplicate entitlement and source allocation."))

    @api.constrains("gross_quantity", "refund_quantity", "net_quantity", "reward_quantity", "entitlement_quantity", "snapshot_payload", "snapshot_hash")
    def _check_calculated_values(self):
        for claim in self:
            if min(claim.gross_quantity, claim.refund_quantity, claim.net_quantity, claim.reward_quantity, claim.entitlement_quantity) < 0:
                raise ValidationError(_("Claim quantities cannot be negative."))
            if float_compare(claim.gross_quantity - claim.refund_quantity, claim.net_quantity, precision_digits=12):
                raise ValidationError(_("Claim net quantity must equal gross quantity less refunds."))
            if claim.reward_quantity <= 0 or claim.entitlement_quantity != claim.reward_quantity:
                raise ValidationError(_("Claim entitlement must match its positive reward quantity."))
            if claim.snapshot_payload and claim._hash_snapshot(claim.snapshot_payload) != claim.snapshot_hash:
                raise ValidationError(_("Claim snapshot integrity verification failed."))

    @api.depends("snapshot_payload")
    def _compute_snapshot_json(self):
        for claim in self:
            claim.snapshot_json = json.dumps(claim.snapshot_payload or {}, sort_keys=True, indent=2, ensure_ascii=False)

    @api.constrains("scheme_id", "distributor_id", "period_id", "company_id", "slab_id", "qualifying_product_id")
    def _check_relations(self):
        for rec in self:
            if rec.scheme_id and rec.scheme_id.company_id != rec.company_id:
                raise ValidationError(_("Claim and scheme must belong to the same company."))
            if rec.period_id and (rec.period_id.scheme_id != rec.scheme_id or rec.period_id.company_id != rec.company_id):
                raise ValidationError(_("Claim period must belong to the selected scheme and company."))
            if rec.period_id and rec.period_id.state != "closed" and self.env.context.get("_gt_claim_create_token") is not CLAIM_CREATE_TOKEN:
                raise ValidationError(_("A claim can only belong to a closed scheme period."))
            if rec.distributor_id and rec.distributor_id not in rec.scheme_id.distributor_ids:
                raise ValidationError(_("The distributor must be eligible for the selected scheme."))
            if rec.slab_id and rec.slab_id.scheme_id != rec.scheme_id:
                raise ValidationError(_("The selected purchase slab must belong to the claim scheme."))
            if rec.qualifying_product_id and rec.qualifying_product_id != rec.scheme_id.qualifying_product_id:
                raise ValidationError(_("The qualifying product must match the scheme configuration."))

    @api.model
    def _canonical_value(self, value):
        if isinstance(value, dict):
            return {key: self._canonical_value(value[key]) for key in sorted(value)}
        if isinstance(value, (list, tuple)):
            return [self._canonical_value(item) for item in value]
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValidationError(_("Snapshot evidence contains an invalid numeric value."))
            return format(Decimal(str(value)).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP), "f")
        if value is None or isinstance(value, (str, int, bool)):
            return value
        raise ValidationError(_("Snapshot evidence contains an unsupported value."))

    @api.model
    def _canonical_json(self, payload):
        return json.dumps(self._canonical_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @api.model
    def _hash_snapshot(self, payload):
        return hashlib.sha256(self._canonical_json(payload).encode("utf-8")).hexdigest()

    @api.model
    def _stable_source_fingerprint(self, scheme, period, distributor, result):
        sources = sorted(
            result["invoice_sources"] + result["refund_sources"],
            key=lambda row: (row["company_id"], row["move_id"], row["invoice_line_id"], row["source_role"]),
        )
        payload = {
            "company_id": scheme.company_id.id,
            "scheme_id": scheme.id,
            "distributor_id": distributor.id,
            "period_id": period.id,
            "period_start": fields.Date.to_string(period.date_start),
            "period_end": fields.Date.to_string(period.date_end),
            "qualifying_product_id": scheme.qualifying_product_id.id,
            "qualifying_uom_id": scheme.qualifying_uom_id.id,
            "scheme_date_start": fields.Date.to_string(scheme.date_start),
            "scheme_date_end": fields.Date.to_string(scheme.date_end),
            "reward_product_id": scheme.reward_product_id.id,
            "reward_uom_id": scheme.reward_product_id.uom_id.id,
            "selected_slab": False,
            "sources": sources,
            "exceptions": sorted((item["code"], item["severity"]) for item in result["exceptions"]),
        }
        if result["slab_id"]:
            slab = self.env["gt.distributor.scheme.slab"].browse(result["slab_id"])
            payload["selected_slab"] = {
                "id": slab.id,
                "minimum_quantity": slab.minimum_quantity,
                "maximum_quantity": slab.maximum_quantity or False,
                "reward_quantity": slab.reward_quantity,
            }
        return self._hash_snapshot(payload)

    @api.model
    def _build_snapshot(self, scheme, period, distributor, result, cutoff):
        slab = self.env["gt.distributor.scheme.slab"].browse(result["slab_id"])
        sources = sorted(
            result["invoice_sources"] + result["refund_sources"],
            key=lambda row: (row["company_id"], row["move_id"], row["invoice_line_id"], row["source_role"]),
        )
        source_fingerprint = self._stable_source_fingerprint(scheme, period, distributor, result)
        snapshot = {
            "version": 1,
            "identity": {
                "company_id": scheme.company_id.id,
                "scheme_id": scheme.id,
                "scheme_code": scheme.code,
                "scheme_name": scheme.name,
                "period_id": period.id,
                "distributor_id": distributor.id,
                "distributor_name": distributor.name,
            },
            "scheme_configuration": {
                "date_start": fields.Date.to_string(scheme.date_start),
                "date_end": fields.Date.to_string(scheme.date_end),
                "qualifying_product_id": scheme.qualifying_product_id.id,
                "qualifying_product_name": scheme.qualifying_product_id.display_name,
                "reward_product_id": scheme.reward_product_id.id,
                "reward_product_name": scheme.reward_product_id.display_name,
                "qualifying_uom_id": scheme.qualifying_uom_id.id,
                "qualifying_uom_name": scheme.qualifying_uom_id.display_name,
                "reward_uom_id": scheme.reward_product_id.uom_id.id,
                "reward_uom_name": scheme.reward_product_id.uom_id.display_name,
            },
            "period": {
                "start": fields.Date.to_string(period.date_start),
                "end": fields.Date.to_string(period.date_end),
            },
            "calculation": {
                "cutoff": fields.Datetime.to_string(cutoff),
                "snapshot_at": fields.Datetime.to_string(fields.Datetime.now()),
                "gross_quantity": result["gross_quantity"],
                "refund_quantity": result["refund_quantity"],
                "net_quantity": result["net_quantity"],
                "qualifying_uom_id": result["qualifying_uom_id"],
                "slab_id": slab.id,
                "reward_product_id": result["reward_product_id"],
                "reward_uom_id": scheme.reward_product_id.uom_id.id,
                "reward_quantity": result["reward_quantity"],
                "source_fingerprint": result["source_fingerprint"],
                "source_evidence_fingerprint": source_fingerprint,
                "exceptions": sorted((item["code"], item["severity"]) for item in result["exceptions"]),
            },
            "slab": {
                "id": slab.id,
                "minimum_quantity": slab.minimum_quantity,
                "maximum_quantity": slab.maximum_quantity or False,
                "reward_quantity": slab.reward_quantity,
            },
            "sources": sources,
        }
        return snapshot, source_fingerprint, self._hash_snapshot(snapshot)

    @api.model
    def _prepare_source_values(self, claim, result, stable_fingerprint):
        values = []
        for row in result["invoice_sources"] + result["refund_sources"]:
            if row["line_classification"] != "QUALIFYING":
                continue
            if row["source_role"] == "INVOICE":
                role = "INVOICE"
                contribution = row["normalized_quantity"]
                origin_invoice_id = False
            elif row["source_role"] in ("CREDIT_NOTE", "CREDIT_NOTE_REVERSAL"):
                role = "REFUND"
                contribution = -row["normalized_quantity"]
                origin = self.env["account.move"].browse(row["origin_move_id"]).exists()
                origin_invoice_id = origin.reversed_entry_id.id if origin and origin.move_type == "out_invoice" and origin.reversed_entry_id else origin.id if origin and origin.move_type == "out_invoice" else False
            else:
                continue
            component_hash = self._hash_snapshot(row)
            values.append({
                "claim_id": claim.id,
                "scheme_id": claim.scheme_id.id,
                "period_id": claim.period_id.id,
                "distributor_id": claim.distributor_id.id,
                "company_id": claim.company_id.id,
                "move_id": row["move_id"],
                "invoice_line_id": row["invoice_line_id"],
                "origin_invoice_id": origin_invoice_id,
                "source_role": role,
                "invoice_date": row["invoice_date"],
                "product_id": row["product_id"],
                "product_uom_id": row["source_uom_id"],
                "normalized_uom_id": claim.qualifying_uom_id.id,
                "source_quantity": row["source_quantity"],
                "normalized_quantity": row["normalized_quantity"],
                "quantity": contribution,
                "unit_price": row["line_subtotal"] / row["source_quantity"] if row["source_quantity"] else 0,
                "line_subtotal": row["line_subtotal"],
                "currency_id": row["currency_id"],
                "monetary_classification": row["line_classification"],
                "source_fingerprint_component": component_hash,
                "snapshot_payload": row,
                "claim_source_fingerprint": stable_fingerprint,
            })
        return values

    def _check_action_access(self, manager_only=False):
        group = "gt_distributor_scheme_settlement.group_scheme_manager" if manager_only else None
        if group and not self.env.user.has_group(group):
            raise AccessError(_("Only a scheme manager may start claim review."))
        if not group and not any(self.env.user.has_group(item) for item in (
            "gt_distributor_scheme_settlement.group_scheme_operator",
            "gt_distributor_scheme_settlement.group_scheme_manager",
        )):
            raise AccessError(_("You are not authorized to manage settlement claims."))
        self.check_access("read")
        if any(claim.company_id != self.env.company or claim.company_id not in self.env.companies for claim in self):
            raise AccessError(_("Switch to the claim company before managing this claim."))

    def _check_snapshot_integrity(self):
        self.ensure_one()
        if not self.snapshot_payload or self._hash_snapshot(self.snapshot_payload) != self.snapshot_hash:
            raise ValidationError(_("The protected claim snapshot failed its integrity check."))
        source_payload = self.snapshot_payload.get("sources", [])
        allocated_count = sum(row.get("line_classification") == "QUALIFYING" for row in source_payload)
        if allocated_count != self.source_evidence_count or len(self.source_ids) != self.source_evidence_count:
            raise ValidationError(_("The protected claim snapshot source count does not match its evidence."))
        return True

    def _compute_source_revalidation(self):
        self.ensure_one()
        self._check_snapshot_integrity()
        calculator = self.env["gt.distributor.scheme.calculator"]
        result = calculator.calculate_eligibility(
            self.scheme_id.id, self.distributor_id.id,
            self.period_id.date_start, self.period_id.date_end, fields.Datetime.now(),
        )
        if result["calculation_status"] == "BLOCKED":
            return {
                "status": "blocked",
                "change_category": "source_attribution_unresolved",
                "original": self._snapshot_entitlement(),
                "current": self._result_entitlement(result),
                "source_fingerprint": False,
                "exception_codes": sorted({item["code"] for item in result["exceptions"] if item["severity"] == "BLOCKING"}),
            }
        current_fingerprint = self._stable_source_fingerprint(self.scheme_id, self.period_id, self.distributor_id, result)
        original = self._snapshot_entitlement()
        current = self._result_entitlement(result)
        entitlement_changed = any([
            float_compare(original["gross_quantity"], current["gross_quantity"], precision_digits=12),
            float_compare(original["refund_quantity"], current["refund_quantity"], precision_digits=12),
            float_compare(original["net_quantity"], current["net_quantity"], precision_digits=12),
            original["slab_id"] != current["slab_id"],
            original["reward_product_id"] != current["reward_product_id"],
            float_compare(original["reward_quantity"], current["reward_quantity"], precision_digits=12),
        ])
        if current_fingerprint == self.source_fingerprint and not entitlement_changed:
            status, category = "current", "none"
        else:
            status = "stale"
            category = "source_changed_entitlement_changed" if entitlement_changed else "source_changed_entitlement_unchanged"
        return {
            "status": status,
            "change_category": category,
            "original": original,
            "current": current,
            "source_fingerprint": current_fingerprint,
            "calculation_fingerprint": result["source_fingerprint"],
            "exception_codes": sorted({item["code"] for item in result["exceptions"]}),
        }

    def _snapshot_entitlement(self):
        self.ensure_one()
        return {
            "gross_quantity": self.gross_quantity,
            "refund_quantity": self.refund_quantity,
            "net_quantity": self.net_quantity,
            "qualifying_uom_id": self.qualifying_uom_id.id,
            "slab_id": self.slab_id.id,
            "reward_product_id": self.reward_product_id.id,
            "reward_quantity": self.reward_quantity,
        }

    @api.model
    def _result_entitlement(self, result):
        return {
            "gross_quantity": result["gross_quantity"],
            "refund_quantity": result["refund_quantity"],
            "net_quantity": result["net_quantity"],
            "qualifying_uom_id": result["qualifying_uom_id"],
            "slab_id": result["slab_id"],
            "reward_product_id": result["reward_product_id"] if result["calculation_status"] == "ELIGIBLE" else False,
            "reward_quantity": result["reward_quantity"] if result["calculation_status"] == "ELIGIBLE" else 0,
        }

    def _store_revalidation(self, validation):
        self.ensure_one()
        values = {
            "source_validation_status": validation["status"],
            "source_change_category": validation["change_category"],
            "source_validation_at": fields.Datetime.now(),
            "source_validation_result": validation,
        }
        self.with_context(_gt_claim_write_token=CLAIM_WRITE_TOKEN).write(values)
        self.env["gt.distributor.scheme.audit"]._record_event({
            "company_id": self.company_id.id,
            "scheme_id": self.scheme_id.id,
            "claim_id": self.id,
            "event_type": "claim_source_revalidated",
            "evidence": {
                "claim_id": self.id,
                "claim_number": self.name,
                "status": validation["status"],
                "change_category": validation["change_category"],
                "original": validation["original"],
                "current": validation["current"],
                "exception_codes": validation.get("exception_codes", []),
            },
        })

    def action_revalidate_sources(self):
        self.ensure_one()
        self._check_action_access()
        validation = self._compute_source_revalidation()
        self._store_revalidation(validation)
        return validation

    def action_submit(self):
        self.ensure_one()
        self._check_action_access()
        self.env.cr.execute("SELECT id FROM gt_distributor_scheme_claim WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        if self.state != "draft":
            raise UserError(_("Only a Draft claim can be submitted."))
        if self.period_id.state != "closed":
            raise UserError(_("Claims can be submitted only after their period is closed."))
        validation = self._compute_source_revalidation()
        if validation["status"] != "current":
            self._store_revalidation(validation)
            return self._blocked_action_message(validation)
        self.with_context(_gt_claim_write_token=CLAIM_WRITE_TOKEN).write({
            "state": "submitted",
            "submitted_by_id": self.env.user.id,
            "submitted_at": fields.Datetime.now(),
            "source_validation_status": "current",
            "source_change_category": "none",
            "source_validation_at": fields.Datetime.now(),
            "source_validation_result": validation,
        })
        self.env["gt.distributor.scheme.audit"]._record_event({
            "company_id": self.company_id.id,
            "scheme_id": self.scheme_id.id,
            "claim_id": self.id,
            "event_type": "claim_submitted",
            "evidence": {"claim_id": self.id, "claim_number": self.name, "previous_state": "draft", "new_state": "submitted", "snapshot_hash": self.snapshot_hash},
        })
        return True

    def action_start_review(self):
        self.ensure_one()
        self._check_action_access(manager_only=True)
        self.env.cr.execute("SELECT id FROM gt_distributor_scheme_claim WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        if self.state != "submitted":
            raise UserError(_("Only a Submitted claim can enter review."))
        validation = self._compute_source_revalidation()
        if validation["status"] != "current":
            self._store_revalidation(validation)
            return self._blocked_action_message(validation)
        self.with_context(_gt_claim_write_token=CLAIM_WRITE_TOKEN).write({
            "state": "under_review",
            "reviewed_by_id": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
            "source_validation_status": "current",
            "source_change_category": "none",
            "source_validation_at": fields.Datetime.now(),
            "source_validation_result": validation,
        })
        self.env["gt.distributor.scheme.audit"]._record_event({
            "company_id": self.company_id.id,
            "scheme_id": self.scheme_id.id,
            "claim_id": self.id,
            "event_type": "claim_review_started",
            "evidence": {"claim_id": self.id, "claim_number": self.name, "previous_state": "submitted", "new_state": "under_review", "snapshot_hash": self.snapshot_hash},
        })
        return True

    @api.model
    def _blocked_action_message(self, validation):
        if validation["status"] == "blocked":
            message = _("Claim submission is blocked because source attribution cannot be resolved.")
        elif validation["change_category"] == "source_changed_entitlement_unchanged":
            message = _("Claim submission is blocked: sources changed since the snapshot, although the reward entitlement is unchanged.")
        else:
            message = _("Claim submission is blocked because the current calculation changes the original entitlement.")
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Claim requires review"), "message": message, "type": "warning", "sticky": True,
        }}
