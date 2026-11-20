from odoo import api, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class DistributorSchemeCalculator(models.AbstractModel):
    _name = "gt.distributor.scheme.calculator"
    _description = "Distributor Scheme Purchase Calculator"

    @api.model
    def calculate_entitlement(self, scheme_id, distributor_id, period_id):
        """Calculate a non-persisted entitlement from posted customer invoices.

        This method does not create or update claims. Source invoice/refund evidence
        is returned for review. Returns linked outside this period are rejected for
        a later-period adjustment workflow instead of being silently ignored.
        """
        if not (
            self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_operator")
            or self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager")
        ):
            raise AccessError(_("You need the Distributor Scheme Operator role to calculate a purchase entitlement."))

        scheme = self.env["gt.distributor.scheme"].browse(scheme_id).exists()
        distributor = self.env["res.partner"].browse(distributor_id).exists()
        period = self.env["gt.distributor.scheme.period"].browse(period_id).exists()
        if not scheme or not distributor or not period:
            raise ValidationError(_("Select an existing scheme, distributor, and calculation period."))
        scheme.ensure_one()
        distributor.ensure_one()
        period.ensure_one()
        scheme.check_access("read")
        distributor.check_access("read")
        period.check_access("read")

        if period.scheme_id != scheme or period.company_id != scheme.company_id:
            raise ValidationError(_("The calculation period must belong to the selected scheme and company."))
        if distributor not in scheme.distributor_ids:
            raise ValidationError(_("The distributor is not eligible for the selected scheme."))
        if period.state != "open":
            raise UserError(_("A closed calculation period cannot be recalculated."))
        if not period.date_start or not period.date_end or period.date_end < period.date_start:
            raise ValidationError(_("The calculation period has invalid dates."))

        moves = self.env["account.move"]
        lines = self.env["account.move.line"]
        moves.check_access("read")
        lines.check_access("read")

        common_domain = [
            ("company_id", "=", scheme.company_id.id),
            ("commercial_partner_id", "=", distributor.commercial_partner_id.id),
            ("state", "=", "posted"),
            ("invoice_date", ">=", period.date_start),
            ("invoice_date", "<=", period.date_end),
            ("line_ids.product_id", "=", scheme.qualifying_product_id.id),
        ]
        invoices = moves.search(common_domain + [("move_type", "=", "out_invoice")])
        refunds = moves.search(common_domain + [("move_type", "=", "out_refund")])
        invoice_ids = set(invoices.ids)
        source_lines = []
        refund_lines = []
        qualifying_quantity = 0.0

        for move in invoices:
            for line in move.line_ids.filtered(
                lambda item: item.display_type == "product" and item.product_id == scheme.qualifying_product_id
            ):
                quantity = self._convert_quantity(line.quantity, line.product_uom_id, scheme.qualifying_uom_id)
                quantity = abs(quantity)
                qualifying_quantity += quantity
                source_lines.append(self._line_evidence(move, line, quantity))

        for refund in refunds:
            product_lines = refund.line_ids.filtered(
                lambda item: item.display_type == "product" and item.product_id == scheme.qualifying_product_id
            )
            if not product_lines:
                continue
            if not refund.reversed_entry_id:
                raise UserError(_("Posted refund %(refund)s has no linked source invoice; review it before calculation.", refund=refund.display_name))
            if refund.reversed_entry_id.id not in invoice_ids:
                raise UserError(_("Posted refund %(refund)s is linked outside this period's eligible invoices; review it as a period adjustment.", refund=refund.display_name))
            for line in product_lines:
                quantity = abs(self._convert_quantity(line.quantity, line.product_uom_id, scheme.qualifying_uom_id))
                qualifying_quantity -= quantity
                refund_lines.append(self._line_evidence(refund, line, -quantity))

        precision = self.env["decimal.precision"].precision_get("Product Unit")
        qualifying_quantity = float_round(qualifying_quantity, precision_digits=precision)
        if float_compare(qualifying_quantity, 0.0, precision_digits=precision) < 0:
            raise UserError(_("Posted refunds exceed eligible purchases in this period; review the source documents."))

        slab = self._select_highest_slab(scheme, qualifying_quantity)
        status = "qualified" if slab else "below_threshold"
        return {
            "status": status,
            "message": _("Highest qualifying purchase slab selected.") if slab else _("No purchase slab qualifies for this quantity."),
            "scheme_id": scheme.id,
            "distributor_id": distributor.id,
            "period_id": period.id,
            "company_id": scheme.company_id.id,
            "qualifying_product_id": scheme.qualifying_product_id.id,
            "qualifying_uom_id": scheme.qualifying_uom_id.id,
            "qualifying_quantity": qualifying_quantity,
            "slab_id": slab.id if slab else False,
            "reward_product_id": scheme.reward_product_id.id,
            "reward_quantity": slab.reward_quantity if slab else 0.0,
            "source_lines": source_lines,
            "refund_lines": refund_lines,
        }

    @api.model
    def _convert_quantity(self, quantity, source_uom, target_uom):
        if not source_uom or not target_uom or not source_uom._has_common_reference(target_uom):
            raise ValidationError(_("Invoice line UoM is incompatible with the scheme qualifying UoM."))
        return source_uom._compute_quantity(quantity, target_uom, round=False)

    @api.model
    def _select_highest_slab(self, scheme, quantity):
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        for slab in scheme.slab_ids.sorted("minimum_quantity", reverse=True):
            if float_compare(quantity, slab.minimum_quantity, precision_digits=precision) < 0:
                continue
            if slab.maximum_quantity and float_compare(quantity, slab.maximum_quantity, precision_digits=precision) >= 0:
                continue
            return slab
        return self.env["gt.distributor.scheme.slab"]

    @api.model
    def _line_evidence(self, move, line, qualifying_quantity):
        return {
            "move_id": move.id,
            "move_name": move.name,
            "move_type": move.move_type,
            "invoice_date": move.invoice_date,
            "invoice_line_id": line.id,
            "product_id": line.product_id.id,
            "source_uom_id": line.product_uom_id.id,
            "source_quantity": line.quantity,
            "qualifying_quantity": qualifying_quantity,
            "reversed_entry_id": move.reversed_entry_id.id or False,
        }
