from odoo import api, fields, models, _
from odoo.exceptions import AccessError


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
        for vals in vals_list:
            vals["actor_id"] = self.env.user.id
            vals["event_date"] = fields.Datetime.now()
        return super().create(vals_list)

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
