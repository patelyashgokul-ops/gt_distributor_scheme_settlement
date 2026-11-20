from odoo import fields, models, _
from odoo.exceptions import UserError


class DistributorSchemeClaimDecisionWizard(models.TransientModel):
    _name = "gt.distributor.scheme.claim.decision.wizard"
    _description = "Settlement Claim Decision"

    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, readonly=True)
    distributor_id = fields.Many2one(related="claim_id.distributor_id", readonly=True)
    scheme_id = fields.Many2one(related="claim_id.scheme_id", readonly=True)
    period_id = fields.Many2one(related="claim_id.period_id", readonly=True)
    net_quantity = fields.Float(related="claim_id.net_quantity", readonly=True)
    qualifying_uom_id = fields.Many2one(related="claim_id.qualifying_uom_id", readonly=True)
    reward_product_id = fields.Many2one(related="claim_id.reward_product_id", readonly=True)
    reward_quantity = fields.Float(related="claim_id.reward_quantity", readonly=True)
    source_validation_status = fields.Selection(related="claim_id.source_validation_status", readonly=True)
    decision = fields.Selection([
        ("approve", "Approve"), ("reject", "Reject"), ("revise", "Request Revision"),
    ], required=True, default="approve")
    reason = fields.Text(string="Decision Note / Reason", help="A reason is required for rejection and revision requests.")

    def action_confirm(self):
        self.ensure_one()
        claim = self.claim_id
        if self.decision == "approve":
            return claim.action_approve_claim(self.reason or False)
        if self.decision == "reject":
            return claim.action_reject_claim(self.reason)
        if self.decision == "revise":
            return claim.action_request_revision(self.reason)
        raise UserError(_("Choose a valid claim decision."))
