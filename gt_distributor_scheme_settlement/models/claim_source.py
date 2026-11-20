from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DistributorSchemeClaimSource(models.Model):
    _name = "gt.distributor.scheme.claim.source"
    _description = "Distributor Scheme Claim Source Evidence"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "invoice_date, id"
    _check_company_auto = True

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True, readonly=True, index=True)
    move_id = fields.Many2one("account.move", string="Source Invoice", check_company=True, ondelete="restrict")
    invoice_line_id = fields.Many2one("account.move.line", string="Source Invoice Line", check_company=True, ondelete="restrict")
    invoice_date = fields.Date(required=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    product_uom_id = fields.Many2one("uom.uom", required=True)
    quantity = fields.Float(required=True, digits="Product Unit of Measure")
    unit_price = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", required=True)
    snapshot_payload = fields.Json(readonly=True, help="Reserved for immutable accounting source snapshots; capture service is not in this release.")

    @api.constrains("quantity", "unit_price", "claim_id", "move_id", "invoice_line_id")
    def _check_values_and_company(self):
        for rec in self:
            if rec.quantity < 0 or rec.unit_price < 0:
                raise ValidationError(_("Source quantities and unit prices cannot be negative."))
            if rec.claim_id and rec.company_id != rec.claim_id.company_id:
                raise ValidationError(_("Source evidence and claim must belong to the same company."))
            if rec.move_id and rec.move_id.company_id != rec.company_id:
                raise ValidationError(_("Source invoice must belong to the claim company."))
            if rec.invoice_line_id and rec.move_id and rec.invoice_line_id.move_id != rec.move_id:
                raise ValidationError(_("Source invoice line must belong to the selected invoice."))

    def write(self, vals):
        raise ValidationError(_("Source evidence is append-only."))

    def unlink(self):
        raise ValidationError(_("Source evidence cannot be deleted."))
