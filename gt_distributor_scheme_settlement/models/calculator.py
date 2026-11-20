import hashlib
import json
from collections import defaultdict
from math import fsum

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class DistributorSchemeCalculator(models.AbstractModel):
    _name = "gt.distributor.scheme.calculator"
    _description = "Distributor Scheme Purchase Eligibility Calculator"

    _CALCULATION_GROUPS = (
        "gt_distributor_scheme_settlement.group_scheme_operator",
        "gt_distributor_scheme_settlement.group_scheme_manager",
    )

    @api.model
    def calculate_entitlement(self, scheme_id, distributor_id, period_id):
        """P02-compatible wrapper; calculation remains read-only."""
        self._check_calculation_role()
        period = self.env["gt.distributor.scheme.period"].browse(period_id).exists()
        if len(period) != 1:
            raise ValidationError(_("Select an existing calculation period."))
        period.check_access("read")
        scheme = self.env["gt.distributor.scheme"].browse(scheme_id).exists()
        if len(scheme) != 1:
            raise ValidationError(_("Select an existing scheme."))
        scheme.check_access("read")
        if period.scheme_id != scheme or period.company_id != scheme.company_id:
            raise ValidationError(_("The calculation period must belong to the selected scheme and company."))
        if period.state != "open":
            raise UserError(_("A closed calculation period cannot be recalculated."))
        result = self.calculate_eligibility(
            scheme_id,
            distributor_id,
            period.date_start,
            period.date_end,
            fields.Datetime.now(),
        )
        if result["calculation_status"] == "BLOCKED":
            message = next((item["message"] for item in result["exceptions"] if item["severity"] == "BLOCKING"), None)
            raise UserError(message or _("This calculation needs review before it can be trusted."))
        return result

    @api.model
    def calculate_eligibility(self, scheme_id, distributor_id, date_start, date_end, as_of):
        """Return a deterministic, read-only eligibility preview.

        Odoo's commercial partner identity is deliberately retained from P02:
        invoices on contacts whose commercial partner is the configured company
        distributor belong to that distributor. The explicit cutoff is compared
        with move and line create/write timestamps. A relevant record changed after
        the cutoff blocks historical reconstruction because Odoo stores no prior
        accounting-line versions for this addon to reproduce.
        """
        self._check_calculation_role()
        scheme, distributor = self._validate_request(scheme_id, distributor_id, date_start, date_end, as_of)
        cutoff = fields.Datetime.to_datetime(as_of)
        start = fields.Date.to_date(date_start)
        end = fields.Date.to_date(date_end)
        effective_end = min(end, cutoff.date())
        exceptions = []
        invoice_evidence = []
        refund_evidence = []
        gross = refund_quantity = 0.0

        moves = self.env["account.move"]
        lines = self.env["account.move.line"]
        # Keep the caller's normal accounting ACLs and record rules. No sudo/search
        # bypass is used, and every search is company/partner/product/date scoped.
        moves.check_access("read")
        lines.check_access("read")
        common = [
            ("company_id", "=", scheme.company_id.id),
            ("commercial_partner_id", "=", distributor.commercial_partner_id.id),
            ("state", "=", "posted"),
            ("move_type", "=", "out_invoice"),
        ]
        product_domain = [("line_ids.product_id", "=", scheme.qualifying_product_id.id)]
        invoices = moves.search(common + product_domain + [
            ("invoice_date", ">=", start), ("invoice_date", "<=", effective_end),
        ], order="invoice_date, id") if effective_end >= start else moves

        missing_date_invoices = moves.search(common + product_domain + [("invoice_date", "=", False)])
        if missing_date_invoices:
            self._exception(exceptions, "MISSING_INVOICE_DATE", "BLOCKING", _(
                "A posted qualifying customer invoice for this distributor has no invoice date. Review accounting source records."
            ))

        invoice_ids = set(invoices.ids)
        eligible_invoice_lines = defaultdict(list)
        gross_parts = []
        for move in invoices:
            if not self._source_is_available_at_cutoff(move, cutoff, exceptions, scheme.qualifying_product_id):
                continue
            move_lines = move.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            ).sorted("id")
            for line in move_lines:
                classification = self._classify_product_line(line, exceptions)
                if classification == "ZERO_VALUE":
                    invoice_evidence.append(self._build_line_evidence(
                        move, line, 0.0, "EXCLUDED_ZERO_VALUE", classification=classification
                    ))
                    continue
                if classification != "QUALIFYING":
                    continue
                if move.reversed_entry_id and move.reversed_entry_id.move_type == "out_refund":
                    # Reversing a credit note restores the quantity it previously
                    # deducted. It is handled with refund attribution below.
                    continue
                quantity = self._normalize_purchase_quantity(line, scheme, exceptions)
                if quantity is None:
                    continue
                gross_parts.append(quantity)
                eligible_invoice_lines[move.id].append((line, quantity))
                invoice_evidence.append(self._build_line_evidence(move, line, quantity, "INVOICE"))

        refunds = self._find_relevant_refunds(moves, common, product_domain, invoices, start, end, cutoff)
        seen_refund_line_ids = set()
        seen_refund_move_ids = set()
        refund_totals_by_invoice_line = defaultdict(float)
        for refund in refunds.sorted("id"):
            if refund.id in seen_refund_move_ids:
                continue
            seen_refund_move_ids.add(refund.id)
            origin = refund.reversed_entry_id
            refund_product_lines = refund.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            ).sorted("id")
            if not refund_product_lines:
                continue
            # A refund dated in the target period but linked to an invoice outside
            # it was P02's explicit review boundary. Do not guess another period.
            if not origin or origin.id not in invoice_ids:
                if refund.invoice_date and start <= refund.invoice_date <= min(end, cutoff.date()):
                    self._exception(exceptions, "UNATTRIBUTED_REFUND", "BLOCKING", _(
                        "A posted qualifying credit note in this period is not linked to an eligible source invoice. Review its attribution."
                    ))
                continue
            if origin.company_id != scheme.company_id or origin.commercial_partner_id != distributor.commercial_partner_id:
                self._exception(exceptions, "REFUND_ORIGIN_SCOPE_MISMATCH", "BLOCKING", _(
                    "A qualifying credit note does not match the scheme company and distributor. Review its attribution."
                ))
                continue
            if not self._source_is_available_at_cutoff(refund, cutoff, exceptions, scheme.qualifying_product_id):
                continue
            if refund.invoice_date and refund.invoice_date > cutoff.date():
                # Invoice date is the effective accounting date; a future-dated
                # credit note must not reduce a preview before that date.
                continue
            origin_lines = origin.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            ).sorted("id")
            eligible_origin_lines = [line for line, qty in eligible_invoice_lines.get(origin.id, [])]
            if not eligible_origin_lines:
                continue
            if len(origin_lines) != 1 or len(refund_product_lines) != 1 or origin_lines[0] != eligible_origin_lines[0]:
                self._exception(exceptions, "AMBIGUOUS_REFUND_LINE_ATTRIBUTION", "BLOCKING", _(
                    "A credit note contains multiple qualifying lines or its source invoice has multiple qualifying lines; line attribution is unresolved."
                ))
                continue
            refund_line = refund_product_lines[0]
            if refund_line.id in seen_refund_line_ids:
                self._exception(exceptions, "DUPLICATE_REFUND_SOURCE", "BLOCKING", _(
                    "A credit note line was encountered more than once; calculation was blocked to prevent double deduction."
                ))
                continue
            seen_refund_line_ids.add(refund_line.id)
            classification = self._classify_product_line(refund_line, exceptions)
            if classification == "ZERO_VALUE":
                refund_evidence.append(self._build_line_evidence(
                    refund, refund_line, 0.0, "EXCLUDED_ZERO_VALUE", origin=origin, classification=classification
                ))
                continue
            if classification != "QUALIFYING":
                continue
            quantity = self._normalize_purchase_quantity(refund_line, scheme, exceptions)
            if quantity is None:
                continue
            origin_line = eligible_origin_lines[0]
            refund_totals_by_invoice_line[origin_line.id] += quantity
            if float_compare(refund_totals_by_invoice_line[origin_line.id],
                             eligible_invoice_lines[origin.id][0][1], precision_digits=self._quantity_precision()) > 0:
                self._exception(exceptions, "REFUND_EXCEEDS_PURCHASE", "BLOCKING", _(
                    "Attributed posted credit notes exceed the qualifying quantity of their source invoice line. Review accounting records."
                ))
            # Keep unrounded values until after all source lines and reversals are
            # aggregated. No line-by-line UoM rounding is applied.
            refund_quantity += quantity
            refund_evidence.append(self._build_line_evidence(refund, refund_line, quantity, "CREDIT_NOTE", origin=origin))
            if refund.invoice_date and refund.invoice_date > end:
                refund_evidence[-1]["late_refund"] = True
                self._exception(exceptions, "LATE_REFUND", "WARNING", _(
                    "A posted credit note dated after the purchase period reduces this preview because it was available by the selected cutoff."
                ))

        # A later customer invoice that reverses an eligible credit note cancels
        # that deduction. Only a one-to-one product-line reversal is defensible.
        refund_quantity = self._apply_refund_reversals(
            scheme, moves, common, product_domain, invoices, eligible_invoice_lines,
            refunds, refund_evidence, refund_quantity, cutoff, exceptions,
        )

        precision = self._quantity_precision()
        gross = fsum(gross_parts)
        refund_quantity = float_round(refund_quantity, precision_digits=precision)
        raw_net = gross - refund_quantity
        net = float_round(raw_net, precision_digits=precision)
        if float_compare(raw_net, 0.0, precision_digits=precision) < 0:
            self._exception(exceptions, "NEGATIVE_NET_QUANTITY", "BLOCKING", _(
                "Attributed posted refunds exceed the eligible purchase quantity. Review the source documents."
            ))
        slab = self._select_highest_slab(scheme, max(raw_net, 0.0))
        if not scheme.slab_ids:
            self._exception(exceptions, "NO_SLAB_CONFIGURATION", "BLOCKING", _(
                "The scheme has no purchase slabs configured; eligibility cannot be determined."
            ))
        blocking = any(item["severity"] == "BLOCKING" for item in exceptions)
        status = "BLOCKED" if blocking else "ELIGIBLE" if slab else "NOT_ELIGIBLE"
        canonical_sources = sorted(invoice_evidence + refund_evidence, key=self._source_sort_key)
        fingerprint_data = {
            "scheme_id": scheme.id,
            "company_id": scheme.company_id.id,
            "distributor_id": distributor.id,
            "period_start": fields.Date.to_string(start),
            "period_end": fields.Date.to_string(end),
            "as_of": fields.Datetime.to_string(cutoff),
            "qualifying_product_id": scheme.qualifying_product_id.id,
            "qualifying_uom_id": scheme.qualifying_uom_id.id,
            "sources": canonical_sources,
            "exceptions": sorted((item["code"], item["severity"]) for item in exceptions),
            "slab_id": slab.id or False,
            "reward_quantity": slab.reward_quantity if slab else 0.0,
        }
        fingerprint = hashlib.sha256(json.dumps(
            fingerprint_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        return {
            # P02 compatibility fields.
            "status": "qualified" if status == "ELIGIBLE" else "below_threshold" if status == "NOT_ELIGIBLE" else "blocked",
            "qualifying_quantity": net,
            "source_lines": invoice_evidence,
            "refund_lines": refund_evidence,
            # P03 canonical preview contract.
            "calculation_status": status,
            "scheme_id": scheme.id,
            "company_id": scheme.company_id.id,
            "distributor_id": distributor.id,
            "period_start": fields.Date.to_string(start),
            "period_end": fields.Date.to_string(end),
            "as_of": fields.Datetime.to_string(cutoff),
            "gross_quantity": gross,
            "refund_quantity": refund_quantity,
            "net_quantity": net,
            "qualifying_uom_id": scheme.qualifying_uom_id.id,
            "slab_id": slab.id or False,
            "reward_product_id": scheme.reward_product_id.id,
            "reward_quantity": slab.reward_quantity if slab else 0.0,
            "invoice_count": len({item["move_id"] for item in invoice_evidence if item["line_classification"] == "QUALIFYING"}),
            "refund_count": len({item["move_id"] for item in refund_evidence if item["line_classification"] == "QUALIFYING"}),
            "invoice_sources": sorted(invoice_evidence, key=self._source_sort_key),
            "refund_sources": sorted(refund_evidence, key=self._source_sort_key),
            "exceptions": exceptions,
            "source_fingerprint": fingerprint,
            "message": _("Read-only eligibility preview; no claim or stock operation was created."),
        }

    @api.model
    def _check_calculation_role(self):
        if not any(self.env.user.has_group(group) for group in self._CALCULATION_GROUPS):
            raise AccessError(_("You are not authorized to preview distributor scheme eligibility."))

    @api.model
    def _validate_request(self, scheme_id, distributor_id, date_start, date_end, as_of):
        try:
            scheme_id, distributor_id = int(scheme_id), int(distributor_id)
        except (TypeError, ValueError):
            raise ValidationError(_("Select one valid scheme and distributor."))
        scheme = self.env["gt.distributor.scheme"].browse(scheme_id).exists()
        distributor = self.env["res.partner"].browse(distributor_id).exists()
        if len(scheme) != 1 or len(distributor) != 1:
            raise ValidationError(_("Select one valid scheme and distributor."))
        try:
            start = fields.Date.to_date(date_start)
            end = fields.Date.to_date(date_end)
            cutoff = fields.Datetime.to_datetime(as_of)
        except (TypeError, ValueError):
            raise ValidationError(_("The preview dates and as-of cutoff must be valid."))
        if not start or not end or not cutoff or end < start:
            raise ValidationError(_("The preview period dates and as-of cutoff are required and valid."))
        scheme.check_access("read")
        distributor.check_access("read")
        if scheme.company_id != self.env.company or scheme.company_id not in self.env.companies:
            raise AccessError(_("Switch to a company authorized for this scheme before previewing eligibility."))
        if start < scheme.date_start or end > scheme.date_end:
            raise ValidationError(_("The requested preview period must be fully inside scheme validity dates."))
        if cutoff > fields.Datetime.now():
            raise ValidationError(_("The as-of cutoff cannot be in the future."))
        if distributor not in scheme.distributor_ids:
            raise ValidationError(_("The selected distributor is not eligible for this scheme."))
        return scheme, distributor

    @api.model
    def _find_relevant_refunds(self, moves, common, product_domain, invoices, start, end, cutoff):
        if invoices:
            invoice_ids = invoices.ids
        else:
            invoice_ids = []
        cutoff_date = cutoff.date()
        period_refund_range = [
            ("invoice_date", ">=", start),
            ("invoice_date", "<=", min(end, cutoff_date)),
        ]
        domain = [
            ("company_id", "=", common[0][2]),
            ("commercial_partner_id", "=", common[1][2]),
            ("state", "=", "posted"),
            ("move_type", "=", "out_refund"),
        ] + product_domain
        if invoice_ids and min(end, cutoff_date) >= start:
            domain += ["|", "&", *period_refund_range, ("reversed_entry_id", "in", invoice_ids)]
        elif min(end, cutoff_date) >= start:
            domain += period_refund_range
        else:
            return moves
        return moves.search(domain, order="invoice_date, id")

    @api.model
    def _source_is_available_at_cutoff(self, move, cutoff, exceptions, product):
        if move.create_date and move.create_date > cutoff or move.write_date and move.write_date > cutoff:
            self._exception(exceptions, "SOURCE_CHANGED_AFTER_CUTOFF", "BLOCKING", _(
                "A currently posted source document was created or modified after the selected cutoff; Odoo has no prior line version to reproduce this historical preview."
            ))
            return False
        for line in move.line_ids.filtered(lambda item: item.display_type == "product" and item.product_id == product):
            if line.create_date and line.create_date > cutoff or line.write_date and line.write_date > cutoff:
                self._exception(exceptions, "SOURCE_LINE_CHANGED_AFTER_CUTOFF", "BLOCKING", _(
                    "A currently posted source line was created or modified after the selected cutoff; historical line values cannot be reconstructed."
                ))
                return False
        return True

    @api.model
    def _classify_product_line(self, line, exceptions):
        if line.display_type != "product" or not line.product_id:
            return "EXCLUDED"
        if line.quantity <= 0:
            self._exception(exceptions, "INVALID_LINE_QUANTITY", "BLOCKING", _(
                "A qualifying product line has a zero or negative quantity and needs accounting review."
            ))
            return "BLOCKED"
        currency = line.currency_id
        subtotal = line.price_subtotal
        if currency and currency.is_zero(subtotal):
            return "ZERO_VALUE"
        if not currency or subtotal < 0:
            self._exception(exceptions, "INVALID_LINE_VALUE", "BLOCKING", _(
                "A qualifying product line has a negative or unavailable untaxed subtotal and needs accounting review."
            ))
            return "BLOCKED"
        if not line.product_uom_id:
            self._exception(exceptions, "MISSING_LINE_UOM", "BLOCKING", _(
                "A paid qualifying product line has no unit of measure."
            ))
            return "BLOCKED"
        return "QUALIFYING"

    @api.model
    def _normalize_purchase_quantity(self, line, scheme, exceptions):
        try:
            if not line.product_uom_id._has_common_reference(scheme.qualifying_uom_id):
                self._exception(exceptions, "INCOMPATIBLE_UOM", "BLOCKING", _(
                    "A qualifying invoice or credit note uses a unit incompatible with the scheme unit."
                ))
                return None
            quantity = line.product_uom_id._compute_quantity(
                line.quantity, scheme.qualifying_uom_id, round=False
            )
        except (UserError, ValidationError):
            self._exception(exceptions, "INVALID_UOM_CONVERSION", "BLOCKING", _(
                "A qualifying invoice or credit note quantity could not be converted to the scheme unit."
            ))
            return None
        if quantity <= 0:
            self._exception(exceptions, "INVALID_NORMALIZED_QUANTITY", "BLOCKING", _(
                "A qualifying accounting line converted to a non-positive quantity."
            ))
            return None
        return quantity

    @api.model
    def _apply_refund_reversals(self, scheme, moves, common, product_domain, invoices,
                                eligible_invoice_lines, refunds, refund_evidence,
                                refund_quantity, cutoff, exceptions):
        refund_ids = refunds.ids
        if not refund_ids:
            return refund_quantity
        reversal_domain = [
            ("company_id", "=", common[0][2]),
            ("commercial_partner_id", "=", common[1][2]),
            ("state", "=", "posted"),
            ("move_type", "=", "out_invoice"),
            ("reversed_entry_id", "in", refund_ids),
        ] + product_domain
        reversals = moves.search(reversal_domain, order="id")
        seen = set()
        reversed_credit_quantities = defaultdict(float)
        for move in reversals:
            if move.invoice_date and move.invoice_date > cutoff.date():
                continue
            origin_refund = move.reversed_entry_id
            origin_invoice = origin_refund.reversed_entry_id
            if not origin_invoice:
                self._exception(exceptions, "CREDIT_NOTE_REVERSAL_ORIGIN_UNRESOLVED", "BLOCKING", _(
                    "A posted customer invoice reverses a credit note, but its original purchase attribution is unresolved."
                ))
                continue
            if origin_invoice.id not in eligible_invoice_lines:
                continue
            lines = move.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            )
            credit_lines = origin_refund.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            )
            original_lines = origin_invoice.line_ids.filtered(
                lambda line: line.display_type == "product" and line.product_id == scheme.qualifying_product_id
            )
            if len(original_lines) != 1 or len(lines) != 1 or len(credit_lines) != 1:
                self._exception(exceptions, "CREDIT_NOTE_REVERSAL_LINE_AMBIGUOUS", "BLOCKING", _(
                    "A credit note reversal cannot be attributed one-to-one to its qualifying purchase line."
                ))
                continue
            reverse_line = lines[0]
            if reverse_line.id in seen:
                self._exception(exceptions, "DUPLICATE_REFUND_REVERSAL", "BLOCKING", _(
                    "A credit note reversal line was encountered more than once."
                ))
                continue
            seen.add(reverse_line.id)
            if not self._source_is_available_at_cutoff(move, cutoff, exceptions, scheme.qualifying_product_id):
                continue
            if self._classify_product_line(reverse_line, exceptions) != "QUALIFYING":
                continue
            quantity = self._normalize_purchase_quantity(reverse_line, scheme, exceptions)
            if quantity is not None:
                if not self._source_is_available_at_cutoff(origin_refund, cutoff, exceptions, scheme.qualifying_product_id):
                    continue
                if self._classify_product_line(credit_lines[0], exceptions) != "QUALIFYING":
                    continue
                credit_quantity = self._normalize_purchase_quantity(credit_lines[0], scheme, exceptions)
                if credit_quantity is None:
                    continue
                reversed_credit_quantities[credit_lines[0].id] += quantity
                if float_compare(reversed_credit_quantities[credit_lines[0].id], credit_quantity,
                                 precision_digits=self._quantity_precision()) > 0:
                    self._exception(exceptions, "CREDIT_NOTE_REVERSAL_EXCEEDS_CREDIT", "BLOCKING", _(
                        "Posted reversals exceed the quantity of their source credit note. Review the accounting records."
                    ))
                refund_quantity -= quantity
                refund_evidence.append(self._build_line_evidence(
                    move, reverse_line, -quantity, "CREDIT_NOTE_REVERSAL", origin=origin_refund
                ))
        return refund_quantity

    @api.model
    def _build_line_evidence(self, move, line, qualifying_quantity, role, origin=None, classification=None):
        return {
            "company_id": move.company_id.id,
            "distributor_id": move.commercial_partner_id.id,
            "partner_id": move.partner_id.id,
            "move_id": move.id,
            "move_name": move.name,
            "move_type": move.move_type,
            "move_state": move.state,
            "invoice_date": fields.Date.to_string(move.invoice_date) if move.invoice_date else False,
            "move_create_date": fields.Datetime.to_string(move.create_date) if move.create_date else False,
            "move_write_date": fields.Datetime.to_string(move.write_date) if move.write_date else False,
            "invoice_line_id": line.id,
            "product_id": line.product_id.id,
            "source_uom_id": line.product_uom_id.id,
            "source_quantity": line.quantity,
            "normalized_quantity": qualifying_quantity,
            "line_subtotal": line.price_subtotal,
            "currency_id": move.currency_id.id,
            "line_classification": classification or ("QUALIFYING" if qualifying_quantity else "ZERO_VALUE"),
            "source_write_date": fields.Datetime.to_string(line.write_date) if line.write_date else False,
            "source_role": role,
            "origin_move_id": origin.id if origin else False,
            "reversed_entry_id": origin.id if role == "CREDIT_NOTE" and origin else False,
            "attribution_status": "LINKED_UNAMBIGUOUS" if role in ("CREDIT_NOTE", "CREDIT_NOTE_REVERSAL") else "NOT_APPLICABLE",
        }

    @api.model
    def _source_sort_key(self, source):
        return source["company_id"], source["move_id"], source["invoice_line_id"], source["source_role"]

    @api.model
    def _quantity_precision(self):
        # Conversion remains unrounded per line. Twelve decimal places provide a
        # stable aggregate/comparison boundary without promoting 199.999999 to 200.
        return 12

    @api.model
    def _select_highest_slab(self, scheme, quantity):
        precision = self._quantity_precision()
        for slab in scheme.slab_ids.sorted("minimum_quantity", reverse=True):
            if float_compare(quantity, slab.minimum_quantity, precision_digits=precision) < 0:
                continue
            if slab.maximum_quantity and float_compare(quantity, slab.maximum_quantity, precision_digits=precision) >= 0:
                continue
            return slab
        return self.env["gt.distributor.scheme.slab"]

    @api.model
    def _exception(self, exceptions, code, severity, message):
        identity = code, severity
        if not any((item["code"], item["severity"]) == identity for item in exceptions):
            exceptions.append({"code": code, "severity": severity, "message": message})
