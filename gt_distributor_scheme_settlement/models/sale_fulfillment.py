from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .service_tokens import FULFILLMENT_TOKEN


class SaleOrder(models.Model):
    _inherit = "sale.order"

    scheme_claim_id = fields.Many2one(
        "gt.distributor.scheme.claim", string="Scheme Settlement Claim", copy=False,
        index=True, check_company=True, ondelete="restrict",
    )
    is_scheme_fulfillment = fields.Boolean(default=False, copy=False, index=True)

    _scheme_claim_order_uniq = models.Constraint(
        "unique(scheme_claim_id)", "A claim may have only one linked fulfillment order, including a cancelled order.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        protected = any(vals.get("scheme_claim_id") or vals.get("is_scheme_fulfillment") for vals in vals_list)
        if protected and self.env.context.get("_gt_fulfillment_token") is not FULFILLMENT_TOKEN:
            raise AccessError(_("Scheme fulfillment orders can only be created by the approved claim service."))
        orders = super().create(vals_list)
        for order in orders.filtered("scheme_claim_id"):
            order._check_scheme_fulfillment_integrity()
        return orders

    def write(self, vals):
        protected = {"scheme_claim_id", "is_scheme_fulfillment", "partner_id", "company_id", "warehouse_id", "order_line", "currency_id"}
        if any(order.scheme_claim_id for order in self) and protected.intersection(vals):
            if self.env.context.get("_gt_fulfillment_token") is not FULFILLMENT_TOKEN:
                raise AccessError(_("Linked scheme fulfillment order identity and reward lines are service-protected."))
        result = super().write(vals)
        for order in self.filtered("scheme_claim_id"):
            order._check_scheme_fulfillment_integrity()
        return result

    def unlink(self):
        if any(self.mapped("scheme_claim_id")):
            raise UserError(_("A scheme fulfillment order is historical evidence and cannot be deleted."))
        return super().unlink()

    def copy(self, default=None):
        if self.scheme_claim_id:
            raise UserError(_("A linked scheme fulfillment order cannot be copied."))
        return super().copy(default)

    def _check_scheme_fulfillment_integrity(self):
        for order in self.filtered("scheme_claim_id"):
            claim = order.scheme_claim_id
            if not order.is_scheme_fulfillment or order.company_id != claim.company_id or order.partner_id != claim.distributor_id:
                raise ValidationError(_("Fulfillment order company, distributor, and claim linkage must match."))
            if order.warehouse_id.company_id != claim.company_id:
                raise ValidationError(_("Fulfillment warehouse must belong to the claim company."))
            lines = order.order_line.filtered(lambda line: not line.display_type)
            if len(lines) != 1:
                raise ValidationError(_("A scheme fulfillment order must contain exactly one reward line."))
            line = lines[0]
            if (line.scheme_claim_id != claim or not line.is_scheme_reward_line
                or line.product_id != claim.approved_reward_product_id
                or line.product_uom_id != claim.approved_reward_uom_id
                or claim.approved_reward_uom_id.compare(line.product_uom_qty, claim.approved_reward_quantity) != 0
                or not order.currency_id.is_zero(line.price_unit)):
                raise ValidationError(_("Fulfillment reward line must exactly match the frozen approved product, unit, quantity, and zero price."))
        return True

    def action_confirm(self):
        scheme_orders = self.filtered("scheme_claim_id")
        for order in scheme_orders:
            if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
                raise AccessError(_("Only an authorized scheme manager may confirm a fulfillment order."))
            if order.company_id != self.env.company or order.company_id not in self.env.companies:
                raise AccessError(_("Switch to the fulfillment company before confirming this order."))
            order._check_scheme_fulfillment_integrity()
            claim = order.scheme_claim_id
            if claim.state not in ("approved", "fulfillment_in_progress"):
                raise UserError(_("The claim is not authorized for fulfillment."))
            if claim._has_blocking_adjustments():
                raise UserError(_("A blocking claim adjustment prevents order confirmation."))
            validation = claim._active_validation()
            if not claim._p06_reviewed_source_change_is_safe(validation):
                claim.action_revalidate_sources()
                return claim._p06_notification(_("Order confirmation blocked"), _("Claim sources changed after approval. Review the adjustment before confirming fulfillment."), "warning")
        result = super().action_confirm()
        for order in scheme_orders:
            order._check_scheme_fulfillment_integrity()
        return result


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    scheme_claim_id = fields.Many2one("gt.distributor.scheme.claim", copy=False, check_company=True, ondelete="restrict", index=True)
    is_scheme_reward_line = fields.Boolean(default=False, copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        protected = any(vals.get("scheme_claim_id") or vals.get("is_scheme_reward_line") for vals in vals_list)
        if protected and self.env.context.get("_gt_fulfillment_token") is not FULFILLMENT_TOKEN:
            raise AccessError(_("Scheme reward order lines can only be created by the approved claim service."))
        lines = super().create(vals_list)
        for line in lines.filtered(lambda rec: rec.order_id.scheme_claim_id):
            line.order_id._check_scheme_fulfillment_integrity()
        return lines

    def write(self, vals):
        protected = {"scheme_claim_id", "is_scheme_reward_line", "order_id", "product_id", "product_uom_id", "product_uom_qty", "price_unit", "discount", "tax_id", "display_type"}
        linked = self.filtered(lambda line: line.order_id.scheme_claim_id or line.scheme_claim_id)
        if linked and protected.intersection(vals) and self.env.context.get("_gt_fulfillment_token") is not FULFILLMENT_TOKEN:
            raise AccessError(_("A scheme reward line cannot be altered after creation."))
        result = super().write(vals)
        for order in linked.mapped("order_id"):
            order._check_scheme_fulfillment_integrity()
        return result

    def unlink(self):
        if any(line.order_id.scheme_claim_id or line.scheme_claim_id for line in self):
            raise UserError(_("A scheme reward line cannot be deleted."))
        return super().unlink()

    def copy(self, default=None):
        if self.order_id.scheme_claim_id or self.scheme_claim_id:
            raise UserError(_("A scheme reward line cannot be copied."))
        return super().copy(default)
