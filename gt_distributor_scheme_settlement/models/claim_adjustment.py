from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .service_tokens import ADJUSTMENT_TOKEN


class DistributorSchemeClaimAdjustment(models.Model):
    _name = "gt.distributor.scheme.claim.adjustment"
    _description = "Distributor Scheme Claim Adjustment Evidence"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "adjustment_date desc, id desc"
    _check_company_auto = True

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, ondelete="restrict", check_company=True, index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True, readonly=True, index=True)
    scheme_id = fields.Many2one(related="claim_id.scheme_id", store=True, readonly=True, index=True)
    period_id = fields.Many2one(related="claim_id.period_id", store=True, readonly=True, index=True)
    distributor_id = fields.Many2one(related="claim_id.distributor_id", store=True, readonly=True, index=True)
    adjustment_date = fields.Date(required=True, default=fields.Date.context_today)
    quantity_delta = fields.Float(required=True, digits="Product Unit of Measure", help="Signed historical correction quantity.")
    reason = fields.Text(required=True)
    source_move_id = fields.Many2one("account.move", check_company=True, ondelete="restrict")
    adjustment_type = fields.Selection([
        ("source_change", "Source Changed"), ("late_refund", "Late Refund"),
        ("reward_return", "Reward Return"), ("over_fulfillment", "Over Fulfillment"),
        ("attribution_exception", "Attribution Exception"),
    ], required=True, default="source_change", readonly=True)
    fingerprint = fields.Char(required=True, readonly=True, index=True, copy=False)
    original_source_fingerprint = fields.Char(readonly=True)
    current_source_fingerprint = fields.Char(readonly=True)
    original_entitlement = fields.Float(readonly=True, digits="Product Unit of Measure")
    current_entitlement = fields.Float(readonly=True, digits="Product Unit of Measure")
    current_entitlement_known = fields.Boolean(readonly=True)
    already_fulfilled_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    remaining_undelivered_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    potential_excess_fulfillment = fields.Float(readonly=True, digits="Product Unit of Measure")
    validation_status = fields.Selection([
        ("current", "Current"), ("stale", "Stale"), ("blocked", "Blocked"),
    ], readonly=True)
    evidence_payload = fields.Json(readonly=True)
    status = fields.Selection([
        ("open", "Open"), ("under_review", "Under Review"),
        ("reviewed", "Reviewed, Correction Still Pending"), ("blocked", "Blocked"),
    ], required=True, default="open", readonly=True, index=True)
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_note = fields.Text(readonly=True)
    detected_by_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    created_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)

    _claim_fingerprint_uniq = models.Constraint(
        "unique(claim_id, fingerprint)", "A source discrepancy may only be recorded once per claim and fingerprint.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_adjustment_token") is not ADJUSTMENT_TOKEN:
            raise AccessError(_("Adjustment evidence can only be created by the authorized reconciliation service."))
        for vals in vals_list:
            vals.setdefault("detected_by_id", self.env.user.id)
            vals["created_by_id"] = vals["detected_by_id"]
        return super().create(vals_list)

    @api.constrains("quantity_delta", "reason", "claim_id", "source_move_id")
    def _check_adjustment(self):
        for rec in self:
            if not rec.quantity_delta and rec.adjustment_type != "source_change":
                raise ValidationError(_("Adjustment quantity must be non-zero."))
            if not rec.reason or not rec.reason.strip():
                raise ValidationError(_("An adjustment reason is required."))
            if rec.source_move_id and rec.source_move_id.company_id != rec.company_id:
                raise ValidationError(_("Adjustment source document must belong to the claim company."))
            if rec.potential_excess_fulfillment < 0:
                raise ValidationError(_("Potential excess fulfillment cannot be negative."))

    def action_record_review(self, note):
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may review adjustment evidence."))
        if not isinstance(note, str) or len(note.strip()) < 5:
            raise ValidationError(_("Enter a meaningful adjustment review note."))
        for rec in self:
            rec.check_access("read")
            if rec.company_id != self.env.company or rec.company_id not in self.env.companies:
                raise AccessError(_("Switch to the adjustment company before reviewing it."))
            if rec.status == "reviewed":
                continue
            rec.with_context(_gt_adjustment_token=ADJUSTMENT_TOKEN).write({
                "status": "reviewed", "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(), "review_note": note.strip(),
            })
            rec.env["gt.distributor.scheme.audit"]._record_event({
                "company_id": rec.company_id.id, "scheme_id": rec.scheme_id.id, "claim_id": rec.claim_id.id,
                "event_type": "claim_adjustment_reviewed",
                "evidence": {"adjustment_id": rec.id, "fingerprint": rec.fingerprint,
                             "status": "reviewed", "note": note.strip(),
                             "signed_difference": rec.quantity_delta,
                             "resolution": "Review recorded; no stock or financial recovery was performed."},
            })
        return True

    def action_open_review_wizard(self):
        self.ensure_one()
        self.check_access("read")
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may review adjustment evidence."))
        if self.company_id != self.env.company or self.company_id not in self.env.companies:
            raise AccessError(_("Switch to the adjustment company before reviewing it."))
        return {"type": "ir.actions.act_window", "name": _("Review Settlement Adjustment"),
                "res_model": "gt.distributor.scheme.adjustment.review.wizard", "view_mode": "form",
                "target": "new", "context": {"default_adjustment_id": self.id}}

    def write(self, vals):
        if self.env.context.get("_gt_adjustment_token") is ADJUSTMENT_TOKEN:
            return super().write(vals)
        raise ValidationError(_("Adjustment evidence is append-only."))

    def unlink(self):
        raise ValidationError(_("Adjustment evidence cannot be deleted."))
