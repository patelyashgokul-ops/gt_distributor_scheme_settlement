from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from .service_tokens import PERIOD_SERVICE_TOKEN


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
    period_lock_version = fields.Integer(default=0, copy=False, readonly=True, groups="gt_distributor_scheme_settlement.group_scheme_manager")

    _scheme_code_company_uniq = models.Constraint(
        "unique(company_id, code)", "Scheme code must be unique per company."
    )
    _scheme_code_nonempty = models.Constraint(
        "CHECK (char_length(trim(code)) > 0)", "Scheme code cannot be blank."
    )

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
        if "period_lock_version" in vals and self.env.context.get("_gt_period_service_token") is not PERIOD_SERVICE_TOKEN:
            raise AccessError(_("Period coordination metadata is service-managed."))
        if "state" in vals and any(record.state != vals["state"] for record in self):
            raise ValidationError(_("Scheme lifecycle changes are reserved for a later workflow release."))
        configuration_fields = {
            "name", "code", "company_id", "qualifying_product_id", "reward_product_id",
            "distributor_ids", "date_start", "date_end", "qualifying_uom_id",
        }
        if configuration_fields.intersection(vals) and any(record.state == "active" for record in self):
            raise ValidationError(_("An active scheme's eligibility configuration is immutable."))
        return super().write(vals)

    def action_activate(self):
        self.ensure_one()
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may activate a scheme."))
        self.check_access("write")
        if self.company_id != self.env.company or self.company_id not in self.env.companies:
            raise AccessError(_("Switch to the scheme company before activating it."))
        self.env.cr.execute("SELECT id FROM gt_distributor_scheme WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        if self.state != "draft":
            raise ValidationError(_("Only a draft scheme can be activated."))
        if not self.distributor_ids:
            raise ValidationError(_("Add at least one eligible distributor before activation."))
        if not self.slab_ids:
            raise ValidationError(_("Add at least one purchase slab before activation."))
        if not self.qualifying_product_id.uom_id._has_common_reference(self.qualifying_uom_id):
            raise ValidationError(_("The qualifying unit must be compatible with the product's sales unit."))
        if not self.reward_product_id.uom_id:
            raise ValidationError(_("The reward product must have a unit of measure."))
        super(DistributorScheme, self).write({"state": "active"})
        self.env["gt.distributor.scheme.audit"]._record_event({
            "company_id": self.company_id.id,
            "scheme_id": self.id,
            "event_type": "scheme_activated",
            "evidence": {"scheme_code": self.code, "new_state": "active"},
        })
        return True

    def action_open_eligibility_preview(self):
        if not any(self.env.user.has_group(group) for group in (
            "gt_distributor_scheme_settlement.group_scheme_operator",
            "gt_distributor_scheme_settlement.group_scheme_manager",
        )):
            raise AccessError(_("You are not authorized to preview scheme eligibility."))
        self.ensure_one()
        self.check_access("read")
        if self.company_id != self.env.company or self.company_id not in self.env.companies:
            raise AccessError(_("Switch to the scheme company before opening its eligibility preview."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Preview Purchase Eligibility"),
            "res_model": "gt.distributor.scheme.preview.wizard",
            "view_mode": "form",
            "views": [(self.env.ref("gt_distributor_scheme_settlement.view_scheme_preview_wizard_form").id, "form")],
            "target": "new",
            "context": {
                "default_scheme_id": self.id,
                "default_date_start": self.date_start,
                "default_date_end": self.date_end,
            },
        }
