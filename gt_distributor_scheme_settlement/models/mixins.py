from odoo import api, models, _
from odoo.exceptions import AccessError


class CompanyGuardMixin(models.AbstractModel):
    _name = "gt.distributor.scheme.company.guard.mixin"
    _description = "Company consistency guard for distributor scheme records"

    @api.model_create_multi
    def create(self, vals_list):
        companies = self.env.companies
        for vals in vals_list:
            company_id = vals.get("company_id", self.env.company.id)
            if company_id not in companies.ids:
                raise AccessError(_("You cannot create a record for a company you cannot access."))
        return super().create(vals_list)

    def write(self, vals):
        if "company_id" in vals and vals["company_id"] not in self.env.companies.ids:
            raise AccessError(_("You cannot assign a record to a company you cannot access."))
        return super().write(vals)
