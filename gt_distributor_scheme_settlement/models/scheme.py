from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DistributorScheme(models.Model):
    _name = "gt.distributor.scheme"
    _description = "Distributor Scheme"
    _inherit = ["gt.distributor.scheme.company.guard.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, name"
    _check_company_auto = True
    _rec_name = "name"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, copy=False, index=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    qualifying_product_id = fields.Many2one("product.product", string="Qualifying Product", required=True, check_company=True)
    reward_product_id = fields.Many2one("product.product", string="Free Reward Product", required=True, check_company=True)
    distributor_ids = fields.Many2many("res.partner", string="Eligible Distributors", domain=[("is_company", "=", True)])
    date_start = fields.Date(required=True, default=fields.Date.context_today)
    date_end = fields.Date(required=True)
    qualifying_uom_id = fields.Many2one("uom.uom", required=True, string="Qualifying Unit of Measure")
    slab_ids = fields.One2many("gt.distributor.scheme.slab", "scheme_id", string="Purchase Slabs", copy=True)
    period_ids = fields.One2many("gt.distributor.scheme.period", "scheme_id", string="Calculation Periods", copy=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("closed", "Closed"), ("cancelled", "Cancelled")], default="draft", required=True, copy=False, tracking=True)
    notes = fields.Text()

    _sql_constraints = [
        ("scheme_code_company_uniq", "unique(company_id, code)", "Scheme code must be unique per company."),
        ("scheme_code_nonempty", "CHECK (char_length(trim(code)) > 0)", "Scheme code cannot be blank."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise ValidationError(_("A scheme must be created in Draft; lifecycle transitions are reserved for a later release."))
        return super().create(vals_list)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end < record.date_start:
                raise ValidationError(_("The scheme end date must be on or after its start date."))

    @api.constrains("distributor_ids")
    def _check_distributors(self):
        for record in self:
            invalid = record.distributor_ids.filtered(lambda p: not p.is_company or (p.company_id and p.company_id != record.company_id))
            if invalid:
                raise ValidationError(_("Eligible distributors must be company partners compatible with the scheme company."))

    def write(self, vals):
        if "state" in vals and any(record.state != vals["state"] for record in self):
            raise ValidationError(_("Scheme lifecycle changes are reserved for a later workflow release."))
        return super().write(vals)
