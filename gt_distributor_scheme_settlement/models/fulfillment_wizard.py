from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class DistributorSchemeFulfillmentWizard(models.TransientModel):
    _name = "gt.distributor.scheme.fulfillment.wizard"
    _description = "Prepare Distributor Scheme Free Goods Fulfillment"

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, readonly=True)
    company_id = fields.Many2one(related="claim_id.company_id", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, domain="[('company_id', '=', company_id)]")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may prepare free goods fulfillment."))
        return super().create(vals_list)

    def action_prepare(self):
        self.ensure_one()
        claim = self.claim_id
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may prepare free goods fulfillment."))
        claim._check_fulfillment_manager()
        if self.warehouse_id.company_id != claim.company_id:
            raise ValidationError(_("Select a warehouse belonging to the claim company."))
        return claim.action_prepare_free_goods_fulfillment(self.warehouse_id.id)
