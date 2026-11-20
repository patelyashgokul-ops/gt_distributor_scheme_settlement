from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from .service_tokens import AUDIT_CREATE_TOKEN, AUDIT_SYSTEM_TOKEN


class DistributorSchemeAudit(models.Model):
    _name = "gt.distributor.scheme.audit"
    _description = "Distributor Scheme Audit Evidence"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", check_company=True, ondelete="restrict", index=True)
    claim_id = fields.Many2one("gt.distributor.scheme.claim", check_company=True, ondelete="restrict", index=True)
    event_type = fields.Char(required=True, index=True)
    actor_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, ondelete="restrict")
    event_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    evidence = fields.Json(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_audit_service_token") is not AUDIT_CREATE_TOKEN:
            raise AccessError(_("Audit events can only be created by an authorized business service."))
        for vals in vals_list:
            vals["actor_id"] = self.env.user.id
            vals["event_date"] = fields.Datetime.now()
        return super().create(vals_list)

    @api.model
    def _record_event(self, values):
        return self._record_event_multi([values])

    @api.model
    def _record_event_multi(self, values_list):
        if not any(self.env.user.has_group(group) for group in (
            "gt_distributor_scheme_settlement.group_scheme_operator",
            "gt_distributor_scheme_settlement.group_scheme_manager",
        )):
            raise AccessError(_("You are not authorized to record scheme audit events."))
        return self.with_context(_gt_audit_service_token=AUDIT_CREATE_TOKEN).create(values_list)

    @api.model
    def _record_system_event_for_actor(self, values, actor_id, token=None):
        if token is not AUDIT_SYSTEM_TOKEN:
            raise AccessError(_("System audit events require an internal verified workflow."))
        actor = self.env["res.users"].browse(actor_id).exists()
        if not actor:
            raise AccessError(_("The actor for this fulfillment event is unavailable."))
        return self.with_user(actor).sudo().with_context(_gt_audit_service_token=AUDIT_CREATE_TOKEN).create(values)

    @api.constrains("scheme_id", "claim_id", "company_id")
    def _check_company_relations(self):
        for rec in self:
            if rec.scheme_id and rec.scheme_id.company_id != rec.company_id:
                raise AccessError(_("Audit and scheme must belong to the same company."))
            if rec.claim_id and rec.claim_id.company_id != rec.company_id:
                raise AccessError(_("Audit and claim must belong to the same company."))

    def write(self, vals):
        raise AccessError(_("Audit evidence cannot be modified."))

    def unlink(self):
        raise AccessError(_("Audit evidence cannot be deleted."))
