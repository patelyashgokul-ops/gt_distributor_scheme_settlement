"""Coordinate accounting source mutations with scheme calculations.

The guard serializes supported ORM writes for the same company/distributor
against period closing and claim approval. It does not cover raw SQL or
external database writers.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .service_tokens import SOURCE_GUARD_TOKEN


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _gt_lock_scheme_source_scope(self, company_id, distributor_id):
        if not company_id or not distributor_id:
            return
        self.env.cr.execute(
            "SELECT 1 FROM gt_distributor_scheme "
            "WHERE company_id = %s AND state = 'active' LIMIT 1",
            [company_id],
        )
        if not self.env.cr.fetchone():
            return
        now = fields.Datetime.to_string(fields.Datetime.now())
        uid = self.env.uid
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "INSERT INTO gt_distributor_scheme_source_guard "
                    "(company_id, distributor_id, version, create_uid, create_date, write_uid, write_date) "
                    "VALUES (%s, %s, 1, %s, %s, %s, %s) "
                    "ON CONFLICT (company_id, distributor_id) DO UPDATE SET "
                    "version = gt_distributor_scheme_source_guard.version + 1, "
                    "write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date",
                    [company_id, distributor_id, uid, now, uid, now],
                )
        except Exception as error:
            if error.__class__.__name__ == "SerializationFailure":
                raise UserError(_("A concurrent accounting source update is in progress for this distributor. Retry after it finishes.")) from error
            raise

    @api.model
    def _gt_lock_scheme_move_scopes(self, moves):
        if self.env.context.get("_gt_source_guard_token") is SOURCE_GUARD_TOKEN:
            return
        scopes = set()
        for move in moves.exists():
            if move.move_type in ("out_invoice", "out_refund") and move.partner_id:
                scopes.add((move.company_id.id, move.partner_id.commercial_partner_id.id))
        for company_id, distributor_id in sorted(scopes):
            self._gt_lock_scheme_source_scope(company_id, distributor_id)

    def action_post(self):
        if self.env.context.get("_gt_source_guard_token") is SOURCE_GUARD_TOKEN:
            return super().action_post()
        self._gt_lock_scheme_move_scopes(self)
        return super(AccountMove, self.with_context(_gt_source_guard_token=SOURCE_GUARD_TOKEN)).action_post()

    def write(self, vals):
        if self.env.context.get("_gt_source_guard_token") is not SOURCE_GUARD_TOKEN:
            relevant = self.filtered(
                lambda move: move.state == "posted" and move.move_type in ("out_invoice", "out_refund")
            )
            if relevant:
                self._gt_lock_scheme_move_scopes(relevant)
        return super().write(vals)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._gt_guard_lines(records)
        return records

    def write(self, vals):
        if self.env.context.get("_gt_source_guard_token") is not SOURCE_GUARD_TOKEN:
            moves = self.mapped("move_id")
            if vals.get("move_id"):
                moves |= self.env["account.move"].browse(vals["move_id"])
            posted = moves.filtered(lambda move: move.state == "posted" and move.move_type in ("out_invoice", "out_refund"))
            self.env["account.move"]._gt_lock_scheme_move_scopes(posted)
        return super().write(vals)

    def unlink(self):
        if self.env.context.get("_gt_source_guard_token") is not SOURCE_GUARD_TOKEN:
            posted = self.mapped("move_id").filtered(
                lambda move: move.state == "posted" and move.move_type in ("out_invoice", "out_refund")
            )
            self.env["account.move"]._gt_lock_scheme_move_scopes(posted)
        return super().unlink()

    @api.model
    def _gt_guard_lines(self, lines):
        if self.env.context.get("_gt_source_guard_token") is SOURCE_GUARD_TOKEN:
            return
        posted = lines.mapped("move_id").filtered(
            lambda move: move.state == "posted" and move.move_type in ("out_invoice", "out_refund")
        )
        self.env["account.move"]._gt_lock_scheme_move_scopes(posted)
