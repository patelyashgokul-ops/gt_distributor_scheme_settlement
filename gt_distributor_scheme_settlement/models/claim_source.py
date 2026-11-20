from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .service_tokens import CLAIM_CREATE_TOKEN


class DistributorSchemeClaimSource(models.Model):
    _name = "gt.distributor.scheme.claim.source"
    _description = "Distributor Scheme Claim Source Evidence"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "invoice_date, id"
    _check_company_auto = True

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, ondelete="restrict", check_company=True, index=True)
    scheme_id = fields.Many2one(related="claim_id.scheme_id", store=True, readonly=True, index=True)
    period_id = fields.Many2one(related="claim_id.period_id", store=True, readonly=True, index=True)
    distributor_id = fields.Many2one(related="claim_id.distributor_id", store=True, readonly=True, index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True, readonly=True, index=True)
    move_id = fields.Many2one("account.move", string="Source Accounting Document", required=True, check_company=True, ondelete="restrict", index=True)
    invoice_line_id = fields.Many2one("account.move.line", string="Source Accounting Line", required=True, check_company=True, ondelete="restrict", index=True)
    origin_invoice_id = fields.Many2one("account.move", string="Original Purchase Invoice", check_company=True, ondelete="restrict", index=True)
    source_role = fields.Selection([("invoice", "Invoice"), ("refund", "Refund")], required=True, index=True)
    invoice_date = fields.Date(required=True, index=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    product_uom_id = fields.Many2one("uom.uom", required=True, string="Source UoM")
    normalized_uom_id = fields.Many2one("uom.uom", required=True, string="Qualifying UoM")
    source_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    normalized_quantity = fields.Float(required=True, digits=(16, 12), help="Signed source quantity after conversion to the qualifying UoM.")
    quantity = fields.Float(required=True, digits=(16, 12), help="Signed contribution to net purchases: positive invoices and negative refunds; a credit note reversal restores a positive contribution.")
    unit_price = fields.Monetary(currency_field="currency_id")
    line_subtotal = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", required=True)
    monetary_classification = fields.Char(required=True)
    source_fingerprint_component = fields.Char(required=True, index=True)
    claim_source_fingerprint = fields.Char(required=True, index=True)
    snapshot_payload = fields.Json(required=True, readonly=True, copy=False)

    _company_source_line_uniq = models.Constraint(
        "unique(company_id, invoice_line_id)",
        "An accounting line can be allocated to only one settlement entitlement per company.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_claim_source_token") is not CLAIM_CREATE_TOKEN:
            raise AccessError(_("Claim source allocations can only be created by the authorized period close service."))
        line_ids = [vals.get("invoice_line_id") for vals in vals_list if vals.get("invoice_line_id")]
        if len(line_ids) != len(set(line_ids)):
            raise ValidationError(_("The same accounting line was included more than once in a claim allocation."))
        existing = self.search([("invoice_line_id", "in", line_ids)], limit=1) if line_ids else self
        if existing:
            raise ValidationError(_("An accounting line is already allocated to a settlement entitlement."))
        return super().create(vals_list)

    @api.constrains("claim_id", "scheme_id", "period_id", "distributor_id", "company_id", "move_id", "invoice_line_id", "origin_invoice_id", "product_id", "source_quantity", "quantity")
    def _check_source_identity(self):
        for rec in self:
            line = rec.invoice_line_id
            move = rec.move_id
            claim = rec.claim_id
            if claim.period_id.state != "closed" and self.env.context.get("_gt_claim_source_token") is not CLAIM_CREATE_TOKEN:
                raise ValidationError(_("Source allocations require a closed scheme period."))
            if rec.scheme_id != claim.scheme_id or rec.period_id != claim.period_id or rec.distributor_id != claim.distributor_id or rec.company_id != claim.company_id:
                raise ValidationError(_("Source allocation ownership must match its claim."))
            if line.move_id != move:
                raise ValidationError(_("The source accounting line must belong to the selected document."))
            if move.state != "posted" or move.company_id != rec.company_id or move.commercial_partner_id != rec.distributor_id.commercial_partner_id:
                raise ValidationError(_("The source document must be a posted document for the claim company and distributor."))
            if line.product_id != rec.product_id or line.product_id != claim.qualifying_product_id:
                raise ValidationError(_("The source product must match the claim's qualifying product."))
            if rec.source_role == "invoice" and move.move_type != "out_invoice":
                raise ValidationError(_("Invoice source allocations require a posted customer invoice."))
            if rec.source_role == "refund" and move.move_type not in ("out_refund", "out_invoice"):
                raise ValidationError(_("Refund source allocations require a posted customer credit note or its posted reversal."))
            if rec.origin_invoice_id and (rec.origin_invoice_id.company_id != rec.company_id or rec.origin_invoice_id.commercial_partner_id != rec.distributor_id.commercial_partner_id):
                raise ValidationError(_("The original purchase invoice must match the claim company and distributor."))
            if rec.source_quantity <= 0:
                raise ValidationError(_("Allocated source quantity must be positive in the captured accounting record."))

    def write(self, vals):
        raise AccessError(_("Claim source evidence is immutable."))

    def unlink(self):
        raise AccessError(_("Claim source evidence cannot be deleted."))
