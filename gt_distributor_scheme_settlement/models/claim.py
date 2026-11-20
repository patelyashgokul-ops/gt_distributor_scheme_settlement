from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    entitlement_quantity = fields.Float(required=True, digits="Product Unit of Measure", help="Reserved entitlement field; no calculation is performed in this release.")
    state = fields.Selection([("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled")], default="draft", required=True, copy=False, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    fulfillment_order_id = fields.Many2one("sale.order", readonly=True, copy=False, check_company=True)
    fulfillment_picking_ids = fields.Many2many("stock.picking", string="Fulfillment Transfers", readonly=True, copy=False)
    source_ids = fields.One2many("gt.distributor.scheme.claim.source", "claim_id", string="Source Evidence")
    adjustment_ids = fields.One2many("gt.distributor.scheme.claim.adjustment", "claim_id", string="Adjustments")
    note = fields.Text()

    _claim_scheme_distributor_period_uniq = models.Constraint(
        "unique(scheme_id, distributor_id, period_id)",
        "Only one claim is allowed per scheme, distributor, and period.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise ValidationError(_("A claim must be created in Draft; workflow transitions are reserved for a later release."))
            if {"approved_by_id", "approved_at", "fulfillment_order_id", "fulfillment_picking_ids"} & vals.keys():
                raise ValidationError(_("Approval and fulfillment metadata are managed by future workflow services."))
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gt.distributor.scheme.claim") or "New"
        return super().create(vals_list)

    @api.constrains("entitlement_quantity")
    def _check_entitlement(self):
        if any(rec.entitlement_quantity < 0 for rec in self):
            raise ValidationError(_("Entitlement quantity cannot be negative."))

    @api.constrains("scheme_id", "distributor_id", "period_id", "company_id")
    def _check_relations(self):
        for rec in self:
            if rec.scheme_id and rec.scheme_id.company_id != rec.company_id:
                raise ValidationError(_("Claim and scheme must belong to the same company."))
            if rec.period_id and (rec.period_id.scheme_id != rec.scheme_id or rec.period_id.company_id != rec.company_id):
                raise ValidationError(_("Claim period must belong to the selected scheme and company."))
            if rec.distributor_id and rec.distributor_id not in rec.scheme_id.distributor_ids:
                raise ValidationError(_("The distributor must be eligible for the selected scheme."))

    def write(self, vals):
        if "state" in vals and any(record.state != vals["state"] for record in self):
            raise ValidationError(_("Claim workflow transitions are reserved for a later release."))
        if {"approved_by_id", "approved_at", "fulfillment_order_id", "fulfillment_picking_ids"} & vals.keys():
            raise ValidationError(_("Approval and fulfillment metadata are managed by future workflow services."))
        return super().write(vals)
