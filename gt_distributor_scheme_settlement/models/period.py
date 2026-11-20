from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DistributorSchemePeriod(models.Model):
    _name = "gt.distributor.scheme.period"
    _description = "Distributor Scheme Calculation Period"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "date_start, id"
    _check_company_auto = True

    name = fields.Char(required=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="scheme_id.company_id", store=True, readonly=True, index=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    state = fields.Selection([("open", "Open"), ("closed", "Closed")], default="open", required=True)

    _scheme_period_dates_uniq = models.Constraint(
        "unique(scheme_id, date_start, date_end)",
        "A scheme cannot have duplicate calculation periods.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "open") != "open":
                raise ValidationError(_("A scheme period must be created Open; closure is reserved for a later release."))
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals and any(record.state != vals["state"] for record in self):
            raise ValidationError(_("Period closure is reserved for a later release."))
        return super().write(vals)

    @api.constrains("date_start", "date_end", "scheme_id")
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(_("A period end date must be on or after its start date."))
            if rec.scheme_id and (rec.date_start < rec.scheme_id.date_start or rec.date_end > rec.scheme_id.date_end):
                raise ValidationError(_("A calculation period must be contained within the scheme validity dates."))
            overlapping = rec.scheme_id.period_ids.filtered(lambda other: other != rec and other.date_start <= rec.date_end and rec.date_start <= other.date_end)
            if overlapping:
                raise ValidationError(_("Calculation periods for the same scheme cannot overlap."))
