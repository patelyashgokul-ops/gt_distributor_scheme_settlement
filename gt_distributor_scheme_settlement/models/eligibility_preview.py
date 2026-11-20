import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class DistributorSchemePreviewWizard(models.TransientModel):
    _name = "gt.distributor.scheme.preview.wizard"
    _description = "Distributor Scheme Eligibility Preview"

    scheme_id = fields.Many2one("gt.distributor.scheme", required=True, readonly=True)
    distributor_id = fields.Many2one("res.partner", required=True, domain="[('id', 'in', scheme_distributor_ids)]")
    scheme_distributor_ids = fields.Many2many(related="scheme_id.distributor_ids")
    company_id = fields.Many2one(related="scheme_id.company_id")
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    as_of = fields.Datetime(required=True, default=fields.Datetime.now, help="Only accounting sources available by this cutoff can be reproduced. Source records changed after it block the preview.")
    calculation_status = fields.Selection([
        ("ELIGIBLE", "Eligible"), ("NOT_ELIGIBLE", "Not Eligible"), ("BLOCKED", "Blocked"),
    ], readonly=True)
    gross_quantity = fields.Float(readonly=True, digits="Product Unit")
    refund_quantity = fields.Float(readonly=True, digits="Product Unit")
    net_quantity = fields.Float(readonly=True, digits="Product Unit")
    qualifying_uom_id = fields.Many2one("uom.uom", readonly=True)
    slab_id = fields.Many2one("gt.distributor.scheme.slab", readonly=True)
    reward_product_id = fields.Many2one("product.product", readonly=True)
    reward_quantity = fields.Float(readonly=True, digits="Product Unit")
    invoice_count = fields.Integer(readonly=True)
    refund_count = fields.Integer(readonly=True)
    source_fingerprint = fields.Char(readonly=True, copy=False)
    exception_summary = fields.Text(readonly=True)
    source_evidence = fields.Text(readonly=True, help="Read-only accounting source evidence for authorized reviewers.")

    _OUTPUT_FIELDS = {
        "calculation_status", "gross_quantity", "refund_quantity", "net_quantity",
        "qualifying_uom_id", "slab_id", "reward_product_id", "reward_quantity",
        "invoice_count", "refund_count", "source_fingerprint", "exception_summary", "source_evidence",
    }

    @api.model_create_multi
    def create(self, vals_list):
        self.env["gt.distributor.scheme.calculator"]._check_calculation_role()
        return super().create(vals_list)

    def write(self, vals):
        if self._OUTPUT_FIELDS.intersection(vals):
            raise AccessError(_("Eligibility preview results can only be written by the calculation service."))
        return super().write(vals)

    def action_calculate(self):
        self.ensure_one()
        calculator = self.env["gt.distributor.scheme.calculator"]
        calculator._check_calculation_role()
        result = calculator.calculate_eligibility(
            self.scheme_id.id,
            self.distributor_id.id,
            self.date_start,
            self.date_end,
            self.as_of,
        )
        values = {
            "calculation_status": result["calculation_status"],
            "gross_quantity": result["gross_quantity"],
            "refund_quantity": result["refund_quantity"],
            "net_quantity": result["net_quantity"],
            "qualifying_uom_id": result["qualifying_uom_id"],
            "slab_id": result["slab_id"],
            "reward_product_id": result["reward_product_id"],
            "reward_quantity": result["reward_quantity"],
            "invoice_count": result["invoice_count"],
            "refund_count": result["refund_count"],
            "source_fingerprint": result["source_fingerprint"],
            "exception_summary": "\n".join(
                f"[{item['severity']}] {item['code']}: {item['message']}" for item in result["exceptions"]
            ) or _("No calculation exceptions."),
            "source_evidence": json.dumps({
                "invoice_sources": result["invoice_sources"],
                "refund_sources": result["refund_sources"],
            }, sort_keys=True, indent=2, ensure_ascii=False),
        }
        super(DistributorSchemePreviewWizard, self).write(values)
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "views": [(self.env.ref(
                    "gt_distributor_scheme_settlement.view_scheme_preview_wizard_form").id, "form")],
                "target": "new"}
