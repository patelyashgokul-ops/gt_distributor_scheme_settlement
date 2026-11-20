import csv
import io
from datetime import timedelta

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError, ValidationError


REPORT_ROLES = (
    "gt_distributor_scheme_settlement.group_scheme_operator",
    "gt_distributor_scheme_settlement.group_scheme_manager",
    "gt_distributor_scheme_settlement.group_scheme_auditor",
)
APPROVED_STATES = ("approved", "fulfillment_in_progress", "fulfilled", "settled", "adjustment_required")
REPORT_LIMIT = 5000
REPORT_TOKEN = object()


class DistributorSchemeDashboard(models.TransientModel):
    _name = "gt.distributor.scheme.dashboard"
    _description = "Distributor Scheme Operations Dashboard"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    scheme_id = fields.Many2one("gt.distributor.scheme", domain="[('company_id', '=', company_id)]")
    distributor_id = fields.Many2one("res.partner", domain="[('is_company', '=', True)]")
    claim_created_from = fields.Date(string="Claim Created From")
    claim_created_to = fields.Date(string="Claim Created To")
    active_scheme_count = fields.Integer(compute="_compute_metrics")
    pending_review_count = fields.Integer(compute="_compute_metrics")
    approved_count = fields.Integer(compute="_compute_metrics")
    fulfillment_count = fields.Integer(compute="_compute_metrics")
    settled_count = fields.Integer(compute="_compute_metrics")
    adjustment_count = fields.Integer(compute="_compute_metrics")
    late_refund_count = fields.Integer(compute="_compute_metrics")
    outstanding_delivery_count = fields.Integer(compute="_compute_metrics")
    blocked_outstanding_count = fields.Integer(compute="_compute_metrics")

    @api.model
    def _validate_scope(self, company_id):
        if not any(self.env.user.has_group(group) for group in REPORT_ROLES):
            raise AccessError(_("You are not authorized to view scheme reporting."))
        company = self.env["res.company"].browse(company_id).exists()
        if not company or company not in self.env.companies:
            raise AccessError(_("The selected company is outside your allowed company scope."))
        return company

    @api.model
    def _claim_domain(self, company, scheme=False, distributor=False, date_from=False, date_to=False):
        self._validate_scope(company.id)
        if scheme and (scheme.company_id != company or scheme not in self.env["gt.distributor.scheme"].search([("id", "=", scheme.id)])):
            raise AccessError(_("The selected scheme is not available in this company."))
        domain = [("company_id", "=", company.id)]
        if scheme:
            domain.append(("scheme_id", "=", scheme.id))
        if distributor:
            domain.append(("distributor_id", "=", distributor.id))
        # These report filters intentionally refer to claim creation time, not invoice,
        # scheme-period, approval, delivery, or settlement dates.
        if date_from:
            domain.append(("create_date", ">=", fields.Datetime.to_datetime(date_from)))
        if date_to:
            domain.append(("create_date", "<", fields.Datetime.to_datetime(date_to) + timedelta(days=1)))
        return domain

    @api.depends("company_id", "scheme_id", "distributor_id", "claim_created_from", "claim_created_to")
    def _compute_metrics(self):
        for dashboard in self:
            counts = dashboard._get_metrics()
            for name, value in counts.items():
                dashboard[name] = value

    def _get_metrics(self):
        self.ensure_one()
        company = self._validate_scope(self.company_id.id)
        if self.claim_created_from and self.claim_created_to and self.claim_created_from > self.claim_created_to:
            raise ValidationError(_("Claim Created From must be on or before Claim Created To."))
        claim_model = self.env["gt.distributor.scheme.claim"]
        domain = self._claim_domain(company, self.scheme_id, self.distributor_id,
                                    self.claim_created_from, self.claim_created_to)
        claims = claim_model.search(domain, order="id", limit=REPORT_LIMIT + 1)
        if len(claims) > REPORT_LIMIT:
            raise UserError(_("The dashboard scope exceeds 5,000 claims. Narrow the filters and retry."))
        unresolved_adjustment_claims = self.env["gt.distributor.scheme.claim.adjustment"].search([
            ("company_id", "=", company.id), ("status", "in", ["open", "under_review", "blocked", "reviewed"]),
            ("claim_id", "in", claims.ids or [0]),
        ]).mapped("claim_id")
        late_refunds = self.env["gt.distributor.scheme.claim.adjustment"].search_count([
            ("company_id", "=", company.id), ("status", "in", ["open", "under_review", "blocked", "reviewed"]),
            ("adjustment_type", "=", "late_refund"), ("claim_id", "in", claims.ids or [0]),
        ])
        releasable = claims.filtered(lambda c: c.state in ("approved", "fulfillment_in_progress")
                                     and c.source_validation_status == "current"
                                     and c not in unresolved_adjustment_claims
                                     and c.outstanding_quantity > 0)
        outstanding = claims.filtered(lambda c: c.state in APPROVED_STATES and c.outstanding_quantity > 0)
        scheme_domain = [("company_id", "=", company.id), ("state", "=", "active")]
        if self.scheme_id:
            scheme_domain.append(("id", "=", self.scheme_id.id))
        # Scheme KPI is intentionally independent of claim-created date filters.
        active = self.env["gt.distributor.scheme"].search_count(scheme_domain)
        return {
            "active_scheme_count": active,
            "pending_review_count": len(claims.filtered(lambda c: c.state in ("submitted", "under_review"))),
            "approved_count": len(claims.filtered(lambda c: c.state in APPROVED_STATES and bool(c.approved_at))),
            "fulfillment_count": len(claims.filtered(lambda c: c.state == "fulfillment_in_progress")),
            "settled_count": len(claims.filtered(lambda c: c.state == "settled")),
            "adjustment_count": len(claims.filtered(lambda c: c.state == "adjustment_required" or c in unresolved_adjustment_claims)),
            "late_refund_count": late_refunds,
            "outstanding_delivery_count": len(releasable),
            "blocked_outstanding_count": len(outstanding - releasable),
        }

    def action_open_report_wizard(self):
        self.ensure_one()
        self._validate_scope(self.company_id.id)
        return {
            "type": "ir.actions.act_window", "name": _("Settlement Reports"),
            "res_model": "gt.distributor.scheme.report.wizard", "view_mode": "form", "target": "new",
            "context": {"default_company_id": self.company_id.id, "default_scheme_id": self.scheme_id.id,
                        "default_distributor_id": self.distributor_id.id,
                        "default_date_from": self.claim_created_from, "default_date_to": self.claim_created_to},
        }


class DistributorSchemeReportWizard(models.TransientModel):
    _name = "gt.distributor.scheme.report.wizard"
    _description = "Distributor Scheme Reporting"

    report_type = fields.Selection([
        ("scheme", "Scheme Performance"), ("distributor", "Distributor Settlements"),
        ("outstanding", "Outstanding Free Goods"), ("adjustment", "Adjustment Exceptions"),
    ], required=True, default="distributor")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    scheme_id = fields.Many2one("gt.distributor.scheme", domain="[('company_id', '=', company_id)]")
    distributor_id = fields.Many2one("res.partner", domain="[('is_company', '=', True)]")
    date_from = fields.Date(string="Claim Created From")
    date_to = fields.Date(string="Claim Created To")
    line_ids = fields.One2many("gt.distributor.scheme.report.line", "wizard_id", readonly=True)
    generated_at = fields.Datetime(readonly=True)
    row_count = fields.Integer(readonly=True)

    def _assert_report_access(self):
        self.ensure_one()
        DistributorSchemeDashboard._validate_scope(self.env["gt.distributor.scheme.dashboard"], self.company_id.id)
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(_("Claim Created From must be on or before Claim Created To."))

    def _get_claims(self):
        self._assert_report_access()
        domain = self.env["gt.distributor.scheme.dashboard"]._claim_domain(
            self.company_id, self.scheme_id, self.distributor_id, self.date_from, self.date_to)
        records = self.env["gt.distributor.scheme.claim"].search(domain, order="scheme_id, distributor_id, id", limit=REPORT_LIMIT + 1)
        if len(records) > REPORT_LIMIT:
            raise UserError(_("The report exceeds 5,000 claim rows. Narrow the filters and retry."))
        return records

    @staticmethod
    def _is_approved(claim):
        return claim.state in APPROVED_STATES and bool(claim.approved_at)

    def _claim_row_values(self, claim, report_type):
        approved = self._is_approved(claim)
        adjustments = claim.adjustment_ids.filtered(lambda a: a.status in ("open", "under_review", "blocked", "reviewed"))
        blocked = bool(adjustments) or claim.source_validation_status != "current" or claim.state == "adjustment_required"
        outstanding = claim.outstanding_quantity if approved else 0.0
        if report_type == "outstanding" and outstanding <= 0:
            return False
        deliverable = outstanding if not blocked and claim.state in ("approved", "fulfillment_in_progress") else 0.0
        return {
            "report_type": report_type, "company_id": claim.company_id.id, "company_name": claim.company_id.display_name,
            "scheme_state": claim.scheme_id.state, "claim_id": claim.id,
            "scheme_id": claim.scheme_id.id, "period_id": claim.period_id.id,
            "distributor_id": claim.distributor_id.id,
            "scheme_name": claim.scheme_id.name, "distributor_name": claim.distributor_id.display_name,
            "claim_reference": claim.name, "claim_state": claim.state,
            "source_validation_status": claim.source_validation_status,
            "qualifying_product_name": claim.qualifying_product_id.display_name,
            "qualifying_uom_name": claim.qualifying_uom_id.display_name,
            "gross_quantity": claim.gross_quantity, "refund_quantity": claim.refund_quantity,
            "net_quantity": claim.net_quantity, "slab_name": claim.slab_id.display_name,
            "reward_product_id": (claim.approved_reward_product_id if approved else claim.reward_product_id).id,
            "reward_product_name": (claim.approved_reward_product_id if approved else claim.reward_product_id).display_name,
            "reward_uom_id": (claim.approved_reward_uom_id if approved else claim.reward_uom_id).id,
            "reward_uom_name": (claim.approved_reward_uom_id if approved else claim.reward_uom_id).display_name,
            "approved_quantity": claim.approved_reward_quantity if approved else 0.0,
            "delivered_quantity": claim.fulfilled_quantity if approved else 0.0,
            "returned_quantity": claim.returned_quantity if approved else 0.0,
            "outstanding_quantity": outstanding, "releasable_quantity": deliverable,
            "held": blocked, "adjustment_count": len(adjustments),
        }

    def _build_values(self):
        claims = self._get_claims()
        if self.report_type in ("distributor", "outstanding"):
            rows = [self._claim_row_values(claim, self.report_type) for claim in claims]
            return [row for row in rows if row]
        if self.report_type == "adjustment":
            adjustments = self.env["gt.distributor.scheme.claim.adjustment"].search([
                ("company_id", "=", self.company_id.id), ("claim_id", "in", claims.ids or [0]),
                ("status", "in", ["open", "under_review", "blocked", "reviewed"]),
            ], order="adjustment_date desc, id desc", limit=REPORT_LIMIT + 1)
            if len(adjustments) > REPORT_LIMIT:
                raise UserError(_("The adjustment report exceeds 5,000 rows. Narrow the filters and retry."))
            rows = []
            for adj in adjustments:
                claim = adj.claim_id
                rows.append({
                    "report_type": "adjustment", "company_id": adj.company_id.id, "company_name": adj.company_id.display_name, "claim_id": claim.id,
                    "adjustment_id": adj.id, "adjustment_reference": f"ADJ-{adj.id}",
                    "scheme_id": claim.scheme_id.id, "period_id": claim.period_id.id,
                    "distributor_id": claim.distributor_id.id, "scheme_name": claim.scheme_id.name,
                    "distributor_name": claim.distributor_id.display_name, "claim_reference": claim.name,
                    "claim_state": claim.state, "source_validation_status": adj.validation_status,
                    "reward_product_name": (claim.approved_reward_product_id or claim.reward_product_id).display_name,
                    "reward_uom_name": (claim.approved_reward_uom_id or claim.reward_uom_id).display_name,
                    "approved_quantity": adj.original_entitlement, "current_entitlement": adj.current_entitlement,
                    "signed_difference": adj.quantity_delta, "delivered_quantity": adj.already_fulfilled_quantity,
                    "outstanding_quantity": adj.remaining_undelivered_quantity,
                    "potential_excess": adj.potential_excess_fulfillment, "adjustment_type": adj.adjustment_type,
                    "adjustment_status": adj.status, "adjustment_date": adj.adjustment_date,
                    "adjustment_reason": adj.reason,
                })
            return rows
        # Scheme performance groups by company, scheme, reward product, and reward UoM.
        grouped = {}
        for claim in claims:
            approved = self._is_approved(claim)
            product = claim.approved_reward_product_id if approved else claim.reward_product_id
            uom = claim.approved_reward_uom_id if approved else claim.reward_uom_id
            key = (claim.company_id.id, claim.scheme_id.id, product.id, uom.id)
            row = grouped.setdefault(key, {
                "report_type": "scheme", "company_id": claim.company_id.id, "company_name": claim.company_id.display_name, "scheme_id": claim.scheme_id.id,
                "scheme_name": claim.scheme_id.name, "scheme_state": claim.scheme_id.state, "reward_product_id": product.id,
                "reward_product_name": product.display_name, "reward_uom_id": uom.id,
                "reward_uom_name": uom.display_name, "eligible_distributor_count": 0,
                "claim_count": 0, "approved_count": 0, "rejected_count": 0, "settled_count": 0,
                "approved_quantity": 0.0, "delivered_quantity": 0.0, "outstanding_quantity": 0.0,
                "open_adjustments": 0,
            })
            row["claim_count"] += 1
            row["eligible_distributor_count"] += 1
            row["approved_count"] += int(approved)
            row["rejected_count"] += int(claim.state == "rejected")
            row["settled_count"] += int(claim.state == "settled")
            if approved:
                row["approved_quantity"] += claim.approved_reward_quantity
                row["delivered_quantity"] += claim.net_fulfilled_quantity
                row["outstanding_quantity"] += claim.outstanding_quantity
            row["open_adjustments"] += len(claim.adjustment_ids.filtered(lambda a: a.status in ("open", "under_review", "blocked", "reviewed")))
        # A distributor may hold more than one claim for this scheme over time; count it once.
        for key, row in grouped.items():
            row["eligible_distributor_count"] = len(self.env["gt.distributor.scheme"].browse(key[1]).distributor_ids)
        return list(grouped.values())

    def action_generate(self):
        self.ensure_one()
        rows = self._build_values()
        self.line_ids.with_context(_gt_report_line_cleanup=REPORT_TOKEN).unlink()
        Line = self.env["gt.distributor.scheme.report.line"]
        for offset in range(0, len(rows), 500):
            Line.with_context(_gt_report_line_create=REPORT_TOKEN).create([dict(row, wizard_id=self.id) for row in rows[offset:offset + 500]])
        self.with_context(_gt_report_write=REPORT_TOKEN).write({"generated_at": fields.Datetime.now(), "row_count": len(rows)})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}

    def action_export(self, file_type="csv"):
        self.ensure_one()
        self.check_access("read")
        self._assert_report_access()
        file_type = self.env.context.get("file_type", file_type)
        if not self.generated_at:
            raise UserError(_("Generate the report before exporting it."))
        if file_type not in ("csv", "xlsx"):
            raise ValidationError(_("Unsupported report format."))
        return {"type": "ir.actions.act_url", "url": f"/gt_scheme_settlement/report/{self.id}/{file_type}", "target": "self"}

    def write(self, vals):
        internal = self.env.context.get("_gt_report_write") is REPORT_TOKEN
        filter_fields = {"report_type", "company_id", "scheme_id", "distributor_id", "date_from", "date_to"}
        if not internal and set(vals) - filter_fields:
            raise AccessError(_("Report output fields are service managed."))
        if not internal and vals.get("company_id"):
            self.env["gt.distributor.scheme.dashboard"]._validate_scope(vals["company_id"])
        result = super().write(vals)
        if not internal and set(vals).intersection(filter_fields):
            self.with_context(_gt_report_write=REPORT_TOKEN).write({"generated_at": False, "row_count": 0})
            self.line_ids.with_context(_gt_report_line_cleanup=REPORT_TOKEN).unlink()
        return result


class DistributorSchemeReportLine(models.TransientModel):
    _name = "gt.distributor.scheme.report.line"
    _description = "Distributor Scheme Report Line"

    wizard_id = fields.Many2one("gt.distributor.scheme.report.wizard", required=True, ondelete="cascade", index=True)
    report_type = fields.Selection(related="wizard_id.report_type", store=True)
    company_id = fields.Many2one("res.company", readonly=True)
    company_name = fields.Char(readonly=True)
    claim_id = fields.Many2one("gt.distributor.scheme.claim", readonly=True)
    adjustment_id = fields.Many2one("gt.distributor.scheme.claim.adjustment", readonly=True)
    adjustment_reference = fields.Char(readonly=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", readonly=True)
    period_id = fields.Many2one("gt.distributor.scheme.period", readonly=True)
    distributor_id = fields.Many2one("res.partner", readonly=True)
    scheme_name = fields.Char(readonly=True)
    scheme_state = fields.Char(readonly=True)
    distributor_name = fields.Char(readonly=True)
    claim_reference = fields.Char(readonly=True)
    claim_state = fields.Char(readonly=True)
    source_validation_status = fields.Char(readonly=True)
    qualifying_product_name = fields.Char(readonly=True)
    qualifying_uom_name = fields.Char(readonly=True)
    gross_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    refund_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    net_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    slab_name = fields.Char(readonly=True)
    reward_product_id = fields.Many2one("product.product", readonly=True)
    reward_product_name = fields.Char(readonly=True)
    reward_uom_id = fields.Many2one("uom.uom", readonly=True)
    reward_uom_name = fields.Char(readonly=True)
    approved_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    delivered_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    returned_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    outstanding_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    releasable_quantity = fields.Float(readonly=True, digits="Product Unit of Measure")
    held = fields.Boolean(readonly=True)
    adjustment_count = fields.Integer(readonly=True)
    current_entitlement = fields.Float(readonly=True, digits="Product Unit of Measure")
    signed_difference = fields.Float(readonly=True, digits="Product Unit of Measure")
    potential_excess = fields.Float(readonly=True, digits="Product Unit of Measure")
    adjustment_type = fields.Char(readonly=True)
    adjustment_status = fields.Char(readonly=True)
    adjustment_date = fields.Date(readonly=True)
    adjustment_reason = fields.Text(readonly=True)
    eligible_distributor_count = fields.Integer(readonly=True)
    claim_count = fields.Integer(readonly=True)
    approved_count = fields.Integer(readonly=True)
    rejected_count = fields.Integer(readonly=True)
    settled_count = fields.Integer(readonly=True)
    open_adjustments = fields.Integer(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_report_line_create") is not REPORT_TOKEN:
            raise AccessError(_("Report rows can only be created by the authorized report service."))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("Generated report rows are read only."))

    def unlink(self):
        # Transient rows are removed when their wizard is regenerated or vacuumed.
        if self.env.context.get("_gt_report_line_cleanup") is REPORT_TOKEN:
            return super().unlink()
        raise AccessError(_("Generated report rows cannot be deleted directly."))


def _spreadsheet_safe_text(value):
    text = "" if value is None else str(value)
    probe = text.lstrip("\ufeff\x00\t\r\n \u00a0")
    if probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _report_csv(wizard):
    wizard._assert_report_access()
    lines = wizard.line_ids
    if len(lines) > REPORT_LIMIT:
        raise UserError(_("The export exceeds 5,000 rows. Narrow the report filters."))
    columns = wizard._export_columns()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([label for _name, label, _kind in columns])
    for line in lines:
        out = []
        for name, _label, kind in columns:
            value = getattr(line, name)
            if kind == "text":
                out.append(_spreadsheet_safe_text(value))
            elif kind == "number":
                out.append("" if value is False else format(value or 0, ".12g"))
            elif kind == "date":
                out.append(fields.Date.to_string(value) if value else "")
            else:
                out.append(value or "")
        writer.writerow(out)
    return buffer.getvalue().encode("utf-8-sig")


def _report_xlsx(wizard):
    wizard._assert_report_access()
    lines = wizard.line_ids
    if len(lines) > REPORT_LIMIT:
        raise UserError(_("The export exceeds 5,000 rows. Narrow the report filters."))
    try:
        import xlsxwriter
    except ImportError as exc:
        raise UserError(_("XLSX export is unavailable because the Odoo runtime does not include XlsxWriter.")) from exc
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet("Scheme Report")
    columns = wizard._export_columns()
    header = workbook.add_format({"bold": True, "bg_color": "#E9EEF5", "border": 1})
    for col, (_name, label, _kind) in enumerate(columns):
        sheet.write_string(0, col, label, header)
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, len(lines), max(len(columns) - 1, 0))
    for row_idx, line in enumerate(lines, start=1):
        for col, (name, _label, kind) in enumerate(columns):
            value = getattr(line, name)
            if kind == "number":
                sheet.write_number(row_idx, col, float(value or 0))
            elif kind == "date" and value:
                sheet.write_string(row_idx, col, fields.Date.to_string(value))
            else:
                sheet.write_string(row_idx, col, _spreadsheet_safe_text(value))
    workbook.close()
    return buffer.getvalue()


def _export_columns(self):
    mapping = {
        "scheme": [("scheme_name", "Scheme", "text"), ("company_name", "Company", "text"), ("scheme_state", "Scheme State", "text"), ("reward_product_name", "Reward Product", "text"), ("reward_uom_name", "Reward UoM", "text"), ("eligible_distributor_count", "Eligible Distributors", "number"), ("claim_count", "Claims", "number"), ("approved_count", "Approved Claims", "number"), ("rejected_count", "Rejected Claims", "number"), ("settled_count", "Settled Claims", "number"), ("approved_quantity", "Approved Quantity", "number"), ("delivered_quantity", "Net Delivered Quantity", "number"), ("outstanding_quantity", "Outstanding Quantity", "number"), ("open_adjustments", "Open Adjustments", "number")],
        "distributor": [("claim_reference", "Claim", "text"), ("distributor_name", "Distributor", "text"), ("scheme_name", "Scheme", "text"), ("gross_quantity", "Gross Purchase Qty", "number"), ("refund_quantity", "Refund Qty", "number"), ("net_quantity", "Net Purchase Qty", "number"), ("slab_name", "Slab", "text"), ("reward_product_name", "Reward Product", "text"), ("reward_uom_name", "Reward UoM", "text"), ("approved_quantity", "Approved Qty", "number"), ("delivered_quantity", "Net Delivered Qty", "number"), ("outstanding_quantity", "Outstanding Qty", "number"), ("releasable_quantity", "Currently Releasable Qty", "number"), ("claim_state", "Claim State", "text"), ("source_validation_status", "Source Validation", "text")],
        "outstanding": [("claim_reference", "Claim", "text"), ("distributor_name", "Distributor", "text"), ("scheme_name", "Scheme", "text"), ("company_name", "Company", "text"), ("scheme_state", "State", "text"), ("reward_product_name", "Reward Product", "text"), ("reward_uom_name", "Reward UoM", "text"), ("approved_quantity", "Approved Qty", "number"), ("delivered_quantity", "Delivered Qty", "number"), ("returned_quantity", "Returned Qty", "number"), ("outstanding_quantity", "Outstanding Qty", "number"), ("releasable_quantity", "Releasable Qty", "number"), ("held", "Blocked", "text"), ("claim_state", "Claim State", "text"), ("source_validation_status", "Source Validation", "text")],
        "adjustment": [("adjustment_reference", "Adjustment", "text"), ("claim_reference", "Claim", "text"), ("distributor_name", "Distributor", "text"), ("scheme_name", "Scheme", "text"), ("adjustment_type", "Type", "text"), ("adjustment_date", "Detected Date", "date"), ("approved_quantity", "Original Approved Qty", "number"), ("current_entitlement", "Current Theoretical Qty", "number"), ("signed_difference", "Signed Difference", "number"), ("delivered_quantity", "Net Delivered Qty", "number"), ("potential_excess", "Potential Excess Qty", "number"), ("adjustment_status", "Status", "text"), ("adjustment_reason", "Reason", "text")],
    }
    return mapping[self.report_type]


DistributorSchemeReportWizard._export_columns = _export_columns
DistributorSchemeReportWizard._render_csv = _report_csv
DistributorSchemeReportWizard._render_xlsx = _report_xlsx



