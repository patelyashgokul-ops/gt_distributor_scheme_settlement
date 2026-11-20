from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DistributorSchemeSlab(models.Model):
    _name = "gt.distributor.scheme.slab"
    _description = "Distributor Scheme Purchase Slab"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "minimum_quantity, id"
    _check_company_auto = True
    _rec_name = "name"

    name = fields.Char(compute="_compute_name", store=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="scheme_id.company_id", store=True, readonly=True, index=True)
    minimum_quantity = fields.Float(required=True, digits="Product Unit of Measure")
    maximum_quantity = fields.Float(string="Exclusive Upper Boundary", digits="Product Unit of Measure", help="Optional exclusive upper boundary. Leave blank for no upper limit.")
    reward_quantity = fields.Float(required=True, digits="Product Unit of Measure")

    _scheme_minimum_quantity_uniq = models.Constraint(
        "unique(scheme_id, minimum_quantity)",
        "A scheme cannot have duplicate slab minimum quantities.",
    )

    @api.depends("minimum_quantity", "maximum_quantity", "reward_quantity")
    def _compute_name(self):
        for rec in self:
            upper = _("no upper limit") if not rec.maximum_quantity else _("below %(quantity)s", quantity=rec.maximum_quantity)
            rec.name = _("From %(minimum)s %(upper)s: %(reward)s reward", minimum=rec.minimum_quantity, upper=upper, reward=rec.reward_quantity)

    @api.constrains("minimum_quantity", "maximum_quantity", "reward_quantity")
    def _check_quantities(self):
        for rec in self:
            if rec.minimum_quantity <= 0 or rec.reward_quantity <= 0:
                raise ValidationError(_("Minimum and reward quantities must be greater than zero."))
            if rec.maximum_quantity and rec.maximum_quantity <= rec.minimum_quantity:
                raise ValidationError(_("The exclusive upper boundary must be greater than the minimum quantity."))

    @api.constrains("scheme_id", "minimum_quantity", "maximum_quantity")
    def _check_slab_overlap(self):
        for rec in self:
            others = rec.scheme_id.slab_ids - rec
            if any(not (rec.maximum_quantity and rec.maximum_quantity <= other.minimum_quantity or other.maximum_quantity and other.maximum_quantity <= rec.minimum_quantity) for other in others):
                raise ValidationError(_("Slab quantity ranges for a scheme cannot overlap."))

    @api.model_create_multi
    def create(self, vals_list):
        scheme_ids = {vals.get("scheme_id") for vals in vals_list if vals.get("scheme_id")}
        if self.env["gt.distributor.scheme"].browse(list(scheme_ids)).filtered(lambda scheme: scheme.state == "active"):
            raise ValidationError(_("Purchase slabs cannot be changed after their scheme is activated."))
        return super().create(vals_list)

    def write(self, vals):
        if any(slab.scheme_id.state == "active" for slab in self):
            raise ValidationError(_("Purchase slabs cannot be changed after their scheme is activated."))
        if "scheme_id" in vals:
            target = self.env["gt.distributor.scheme"].browse(vals["scheme_id"])
            if target.state == "active":
                raise ValidationError(_("A slab cannot be added to an active scheme."))
        return super().write(vals)

    def unlink(self):
        if any(slab.scheme_id.state == "active" for slab in self):
            raise ValidationError(_("Purchase slabs cannot be deleted after their scheme is activated."))
        return super().unlink()
