from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DistributorSchemeClaimAdjustment(models.Model):
    _name = "gt.distributor.scheme.claim.adjustment"
    _description = "Distributor Scheme Claim Adjustment Evidence"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "adjustment_date desc, id desc"
    _check_company_auto = True

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, ondelete="restrict", check_company=True, index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True, readonly=True, index=True)
    adjustment_date = fields.Date(required=True, default=fields.Date.context_today)
    quantity_delta = fields.Float(required=True, digits="Product Unit of Measure", help="Signed historical correction quantity.")
    reason = fields.Text(required=True)
    source_move_id = fields.Many2one("account.move", check_company=True, ondelete="restrict")
    created_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)

    @api.constrains("quantity_delta", "reason", "claim_id", "source_move_id")
    def _check_adjustment(self):
        for rec in self:
            if not rec.quantity_delta:
                raise ValidationError(_("Adjustment quantity must be non-zero."))
            if not rec.reason or not rec.reason.strip():
                raise ValidationError(_("An adjustment reason is required."))
            if rec.source_move_id and rec.source_move_id.company_id != rec.company_id:
                raise ValidationError(_("Adjustment source document must belong to the claim company."))

    def write(self, vals):
        raise ValidationError(_("Adjustment evidence is append-only."))

    def unlink(self):
        raise ValidationError(_("Adjustment evidence cannot be deleted."))
