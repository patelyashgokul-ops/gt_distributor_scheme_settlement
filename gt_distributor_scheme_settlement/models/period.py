import hashlib
import json

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .service_tokens import CLAIM_CREATE_TOKEN


class DistributorSchemePeriod(models.Model):
    _name = "gt.distributor.scheme.period"
    _description = "Distributor Scheme Calculation Period"
    _inherit = ["gt.distributor.scheme.company.guard.mixin"]
    _order = "date_start, id"
    _check_company_auto = True

    name = fields.Char(required=True)
    scheme_id = fields.Many2one("gt.distributor.scheme", required=True, ondelete="restrict", check_company=True, index=True)
    company_id = fields.Many2one(related="scheme_id.company_id", store=True, readonly=True, index=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    state = fields.Selection([("draft", "Draft"), ("open", "Open"), ("closed", "Closed")], default="open", required=True, copy=False, tracking=True)
    calculation_cutoff = fields.Datetime(string="Requested Calculation Cutoff", help="Required before closing. Records the requested as-of timestamp for the authoritative P03 calculation.")
    closing_cutoff = fields.Datetime(readonly=True, copy=False)
    closed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    closed_at = fields.Datetime(readonly=True, copy=False)
    calculation_fingerprint = fields.Char(readonly=True, copy=False, index=True)
    close_snapshot_hash = fields.Char(readonly=True, copy=False)
    source_count = fields.Integer(readonly=True, copy=False)
    generated_claim_count = fields.Integer(readonly=True, copy=False)
    exception_count = fields.Integer(readonly=True, copy=False)
    eligible_distributor_count = fields.Integer(readonly=True, copy=False)
    close_summary = fields.Json(readonly=True, copy=False, help="Immutable calculation outcomes for every eligible distributor, including not-eligible outcomes.")
    reward_totals = fields.Json(readonly=True, copy=False, help="Reward totals grouped by product and reward unit; unlike units are never combined.")
    claim_ids = fields.One2many("gt.distributor.scheme.claim", "period_id", string="Settlement Claims", readonly=True)

    _scheme_period_dates_uniq = models.Constraint(
        "unique(scheme_id, date_start, date_end)",
        "A scheme cannot have duplicate calculation periods.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "open") not in ("draft", "open"):
                raise ValidationError(_("A period must be created Draft or Open; closure requires the close service."))
            if any(vals.get(field) for field in (
                "closing_cutoff", "closed_by_id", "closed_at", "calculation_fingerprint",
                "close_snapshot_hash", "source_count", "generated_claim_count", "exception_count",
                "eligible_distributor_count", "close_summary", "reward_totals",
            )):
                raise ValidationError(_("Closing evidence is generated only by the period close service."))
            scheme = self.env["gt.distributor.scheme"].browse(vals.get("scheme_id")).exists()
            if not scheme:
                raise ValidationError(_("Select an existing scheme for the period."))
            scheme.check_access("read")
            if scheme.company_id != self.env.company or scheme.company_id not in self.env.companies:
                raise AccessError(_("Switch to the scheme company before creating its period."))
        return super().create(vals_list)

    def write(self, vals):
        protected = {
            "state", "closing_cutoff", "closed_by_id", "closed_at", "calculation_fingerprint",
            "close_snapshot_hash", "source_count", "generated_claim_count", "exception_count",
            "eligible_distributor_count", "close_summary", "reward_totals",
        }
        if protected.intersection(vals):
            raise ValidationError(_("Period lifecycle and closing evidence can only be changed by authorized period services."))
        if any(record.state == "closed" for record in self) and {"name", "scheme_id", "date_start", "date_end", "calculation_cutoff"}.intersection(vals):
            raise ValidationError(_("A closed period's identity and boundaries are immutable."))
        return super().write(vals)

    def unlink(self):
        if any(record.state == "closed" or record.claim_ids for record in self):
            raise UserError(_("Closed periods and periods with generated claims cannot be deleted."))
        return super().unlink()

    @api.constrains("date_start", "date_end", "scheme_id")
    def _check_dates(self):
        for rec in self:
            if not rec.date_start or not rec.date_end or rec.date_end < rec.date_start:
                raise ValidationError(_("A period requires valid inclusive start and end dates."))
            if rec.scheme_id and (rec.date_start < rec.scheme_id.date_start or rec.date_end > rec.scheme_id.date_end):
                raise ValidationError(_("A calculation period must be contained within the scheme validity dates."))
            overlapping = rec.scheme_id.period_ids.filtered(
                lambda other: other != rec and other.date_start <= rec.date_end and rec.date_start <= other.date_end
            )
            if overlapping:
                raise ValidationError(_("Calculation periods for the same scheme cannot overlap."))

    def _check_close_authorization(self):
        if not self.env.user.has_group("gt_distributor_scheme_settlement.group_scheme_manager"):
            raise AccessError(_("Only a scheme manager may open or close a settlement period."))
        self.check_access("write")
        if self.company_id != self.env.company or self.company_id not in self.env.companies:
            raise AccessError(_("Switch to the period company before managing this period."))

    def action_open_period(self):
        self.ensure_one()
        self._check_close_authorization()
        self.env.cr.execute("SELECT id FROM gt_distributor_scheme_period WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()
        if self.state != "draft":
            raise UserError(_("Only a Draft period can be opened."))
        if self.scheme_id.state != "active":
            raise UserError(_("Only an active scheme can have an open settlement period."))
        super(DistributorSchemePeriod, self).write({"state": "open"})
        self.env["gt.distributor.scheme.audit"]._record_event({
            "company_id": self.company_id.id,
            "scheme_id": self.scheme_id.id,
            "event_type": "period_opened",
            "evidence": {"period_id": self.id, "previous_state": "draft", "new_state": "open"},
        })
        return True

    def action_close_period(self):
        self.ensure_one()
        self._check_close_authorization()
        try:
            cutoff = fields.Datetime.to_datetime(self.calculation_cutoff)
        except (TypeError, ValueError):
            cutoff = False
        if not cutoff:
            raise ValidationError(_("Enter an explicit calculation cutoff before closing this period."))
        if cutoff > fields.Datetime.now():
            raise ValidationError(_("The calculation cutoff cannot be in the future."))
        with self.env.cr.savepoint():
            self.env.cr.execute("SELECT id FROM gt_distributor_scheme_period WHERE id = %s FOR UPDATE", [self.id])
            self.invalidate_recordset()
            if self.state == "closed":
                # Idempotent retries return the existing protected result.
                return self._claims_action()
            self._validate_close_boundary(cutoff)
            try:
                with self.env.cr.savepoint():
                    return self._close_locked(cutoff)
            except IntegrityError as error:
                if error.pgcode == errorcodes.UNIQUE_VIOLATION:
                    raise UserError(_("A claim or source line was allocated by a concurrent operation. No partial period close was committed.")) from error
                raise
            except Exception as error:
                if error.__class__.__name__ == "SerializationFailure":
                    raise UserError(_("A concurrent period or accounting update interrupted closing. No claims were committed; retry after the other transaction finishes.")) from error
                raise

    def _validate_close_boundary(self, cutoff):
        self.ensure_one()
        if self.state != "open":
            raise UserError(_("Only an Open period can be closed."))
        if self.scheme_id.state != "active":
            raise UserError(_("Only an active scheme can be closed into settlement claims."))
        if self.scheme_id.company_id != self.company_id:
            raise ValidationError(_("Period and scheme company do not match."))
        if self.date_end >= fields.Date.context_today(self):
            raise UserError(_("A period can be closed only after its inclusive end date has passed."))
        if self.date_start < self.scheme_id.date_start or self.date_end > self.scheme_id.date_end:
            raise ValidationError(_("The period must be fully inside the scheme validity dates."))
        if not self.scheme_id.distributor_ids:
            raise UserError(_("The active scheme has no eligible distributors to calculate."))
        if not self.scheme_id.slab_ids:
            raise UserError(_("Configure at least one valid purchase slab before closing this period."))
        if cutoff.date() < self.date_end:
            raise ValidationError(_("The calculation cutoff cannot precede the period end date."))
        if cutoff > fields.Datetime.now():
            raise ValidationError(_("The calculation cutoff cannot be in the future."))
        if self.claim_ids:
            raise UserError(_("Claims already exist for this open period. Resolve the conflicting claim records before closing."))

    def _close_locked(self, cutoff):
        self.ensure_one()
        scheme = self.scheme_id
        calculator = self.env["gt.distributor.scheme.calculator"]
        calculations = []
        for distributor in scheme.distributor_ids.sorted("id"):
            result = calculator.calculate_eligibility(
                scheme.id, distributor.id, self.date_start, self.date_end, cutoff
            )
            if result["calculation_status"] == "BLOCKED":
                blocking_codes = sorted({
                    item["code"] for item in result["exceptions"] if item["severity"] == "BLOCKING"
                })
                raise UserError(_(
                    "Period closing was blocked for distributor %(distributor)s due to unresolved eligibility exceptions: %(codes)s. No claims were committed.",
                    distributor=distributor.display_name,
                    codes=", ".join(blocking_codes),
                ))
            calculations.append((distributor, result))

        claim_model = self.env["gt.distributor.scheme.claim"]
        existing = claim_model.search([
            ("company_id", "=", self.company_id.id),
            ("scheme_id", "=", scheme.id),
            ("period_id", "=", self.id),
        ], limit=1)
        if existing:
            raise UserError(_("A claim already exists for this scheme period. Resolve the conflict before closing."))

        all_source_ids = set()
        for _distributor, result in calculations:
            if result["calculation_status"] != "ELIGIBLE":
                continue
            for row in result["invoice_sources"] + result["refund_sources"]:
                if row["line_classification"] == "QUALIFYING":
                    all_source_ids.add(row["invoice_line_id"])
        if all_source_ids:
            allocated = self.env["gt.distributor.scheme.claim.source"].search([
                ("company_id", "=", self.company_id.id),
                ("invoice_line_id", "in", sorted(all_source_ids)),
            ], limit=1)
            if allocated:
                raise UserError(_("An accounting source line is already allocated to a settlement entitlement."))
            # Lock visible source documents and product lines in a stable order.
            move_ids = sorted({
                row["move_id"]
                for _distributor, result in calculations
                for row in result["invoice_sources"] + result["refund_sources"]
                if row["line_classification"] == "QUALIFYING"
            })
            self.env.cr.execute("SELECT id FROM account_move WHERE id = ANY(%s) ORDER BY id FOR SHARE", [move_ids])
            self.env.cr.execute("SELECT id FROM account_move_line WHERE id = ANY(%s) ORDER BY id FOR SHARE", [sorted(all_source_ids)])

        # Re-run after source row locks. Odoo 20 uses Repeatable Read, so these
        # calculations share one database snapshot; later commits are found by
        # mandatory claim revalidation before submission/review.
        final_calculations = []
        for distributor, original_result in calculations:
            result = calculator.calculate_eligibility(
                scheme.id, distributor.id, self.date_start, self.date_end, cutoff
            )
            if result["calculation_status"] == "BLOCKED":
                raise UserError(_("A source exception appeared during closing. No claims were committed."))
            if result["source_fingerprint"] != original_result["source_fingerprint"]:
                raise UserError(_("Accounting sources changed while the period was closing. Retry after review; no claims were committed."))
            final_calculations.append((distributor, result))

        close_rows = []
        reward_totals = {}
        eligible_count = source_count = exception_count = 0
        created_claims = self.env["gt.distributor.scheme.claim"]
        audit_rows = []
        for distributor, result in final_calculations:
            source_rows = result["invoice_sources"] + result["refund_sources"]
            source_count += len(source_rows)
            exception_count += len(result["exceptions"])
            close_rows.append({
                "distributor_id": distributor.id,
                "calculation_status": result["calculation_status"],
                "gross_quantity": result["gross_quantity"],
                "refund_quantity": result["refund_quantity"],
                "net_quantity": result["net_quantity"],
                "qualifying_uom_id": result["qualifying_uom_id"],
                "slab_id": result["slab_id"],
                "reward_product_id": result["reward_product_id"] if result["calculation_status"] == "ELIGIBLE" else False,
                "reward_quantity": result["reward_quantity"] if result["calculation_status"] == "ELIGIBLE" else 0,
                "source_fingerprint": result["source_fingerprint"],
                "exceptions": sorted((item["code"], item["severity"]) for item in result["exceptions"]),
            })
            if result["calculation_status"] != "ELIGIBLE":
                continue
            eligible_count += 1
            reward_key = f"{result['reward_product_id']}:{self.env['product.product'].browse(result['reward_product_id']).uom_id.id}"
            reward_totals[reward_key] = reward_totals.get(reward_key, 0.0) + result["reward_quantity"]
            snapshot, source_fingerprint, snapshot_hash = claim_model._build_snapshot(
                scheme, self, distributor, result, cutoff
            )
            claim = claim_model.with_context(
                _gt_claim_create_token=CLAIM_CREATE_TOKEN
            ).create({
                "scheme_id": scheme.id,
                "period_id": self.id,
                "company_id": self.company_id.id,
                "distributor_id": distributor.id,
                "qualifying_product_id": scheme.qualifying_product_id.id,
                "qualifying_uom_id": scheme.qualifying_uom_id.id,
                "gross_quantity": result["gross_quantity"],
                "refund_quantity": result["refund_quantity"],
                "net_quantity": result["net_quantity"],
                "slab_id": result["slab_id"],
                "reward_product_id": result["reward_product_id"],
                "reward_uom_id": self.env["product.product"].browse(result["reward_product_id"]).uom_id.id,
                "reward_quantity": result["reward_quantity"],
                "entitlement_quantity": result["reward_quantity"],
                "calculation_cutoff": cutoff,
                "source_fingerprint": source_fingerprint,
                "calculation_fingerprint": result["source_fingerprint"],
                "snapshot_hash": snapshot_hash,
                "snapshot_version": 1,
                "snapshot_payload": snapshot,
                "source_evidence_count": sum(row["line_classification"] == "QUALIFYING" for row in source_rows),
                "calculation_snapshot_at": fields.Datetime.now(),
                "originating_scheme_code": scheme.code,
                "created_by_id": self.env.user.id,
            })
            source_values = claim_model._prepare_source_values(claim, result, source_fingerprint)
            if source_values:
                self.env["gt.distributor.scheme.claim.source"].with_context(
                    _gt_claim_source_token=CLAIM_CREATE_TOKEN
                ).create(source_values)
            created_claims |= claim
            audit_rows.append({
                "company_id": self.company_id.id,
                "scheme_id": scheme.id,
                "claim_id": claim.id,
                "event_type": "claim_generated",
                "evidence": {
                    "period_id": self.id,
                    "claim_number": claim.name,
                    "distributor_id": distributor.id,
                    "snapshot_hash": snapshot_hash,
                    "source_fingerprint": source_fingerprint,
                },
            })

        close_payload = {
            "version": 1,
            "period_id": self.id,
            "scheme_id": scheme.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.date_start),
            "period_end": fields.Date.to_string(self.date_end),
            "calculation_cutoff": fields.Datetime.to_string(cutoff),
            "distributors": sorted(close_rows, key=lambda row: row["distributor_id"]),
        }
        canonical = claim_model._canonical_json(close_payload)
        close_fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        close_hash = hashlib.sha256(json.dumps({
            "period": close_payload,
            "claims": sorted((claim.id, claim.snapshot_hash) for claim in created_claims),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        audit_rows.append({
            "company_id": self.company_id.id,
            "scheme_id": scheme.id,
            "event_type": "period_closed",
            "evidence": {
                "period_id": self.id,
                "previous_state": "open",
                "new_state": "closed",
                "calculation_cutoff": fields.Datetime.to_string(cutoff),
                "calculation_fingerprint": close_fingerprint,
                "close_snapshot_hash": close_hash,
                "source_count": source_count,
                "generated_claim_count": len(created_claims),
                "exception_count": exception_count,
            },
        })
        self.env["gt.distributor.scheme.audit"]._record_event_multi(audit_rows)
        super(DistributorSchemePeriod, self).write({
            "state": "closed",
            "closing_cutoff": cutoff,
            "closed_by_id": self.env.user.id,
            "closed_at": fields.Datetime.now(),
            "calculation_fingerprint": close_fingerprint,
            "close_snapshot_hash": close_hash,
            "source_count": source_count,
            "generated_claim_count": len(created_claims),
            "exception_count": exception_count,
            "eligible_distributor_count": eligible_count,
            "close_summary": close_payload,
            "reward_totals": reward_totals,
        })
        return self._claims_action()

    def _claims_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Settlement Claims"),
            "res_model": "gt.distributor.scheme.claim",
            "view_mode": "list,form",
            "domain": [("period_id", "=", self.id)],
            "context": {"default_period_id": self.id},
        }
