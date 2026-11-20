from odoo import fields, models, _
from odoo.exceptions import AccessError


class DistributorSchemeAdjustmentReviewWizard(models.TransientModel):
    _name = "gt.distributor.scheme.adjustment.review.wizard"
    _description = "Review Distributor Scheme Adjustment"

    adjustment_id = fields.Many2one("gt.distributor.scheme.claim.adjustment", required=True, readonly=True)
    review_note = fields.Text(required=True)

    def action_confirm_review(self):
        self.ensure_one()
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may review adjustment evidence."))
        return self.adjustment_id.action_record_review(self.review_note)
