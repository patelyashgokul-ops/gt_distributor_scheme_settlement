from odoo import fields, models


class DistributorSchemeSourceGuard(models.Model):
    """Transaction coordination rows; never exposed through user ACLs."""

    _name = "gt.distributor.scheme.source.guard"
    _description = "Distributor Scheme Accounting Source Lock"
    _log_access = True

    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True)
    distributor_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    version = fields.Integer(required=True, default=0)

    _company_distributor_uniq = models.Constraint(
        "unique(company_id, distributor_id)",
        "Only one source coordination row is allowed per company and distributor.",
    )
