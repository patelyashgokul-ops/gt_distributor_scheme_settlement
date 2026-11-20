import hashlib

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .service_tokens import ADJUSTMENT_TOKEN, AUDIT_SYSTEM_TOKEN, CLAIM_WRITE_TOKEN, STOCK_DONE_TOKEN


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state") == "done" and vals.get("sale_line_id"):
                line = self.env["sale.order.line"].browse(vals["sale_line_id"])
                if line.order_id.scheme_claim_id:
                    raise AccessError(_("Scheme reward movements must be completed through the standard validated stock workflow."))
        return super().create(vals_list)

    def write(self, vals):
        protected = self.filtered(lambda move: move._scheme_claim_for_p06())
        if protected:
            if vals.get("state") == "done" and self.env.context.get("_gt_stock_done_token") is not STOCK_DONE_TOKEN:
                raise AccessError(_("Scheme reward stock moves can only be completed through validated stock operations."))
            if "sale_line_id" in vals and any(move.sale_line_id.id != (vals["sale_line_id"] or False) for move in protected):
                raise AccessError(_("A scheme reward move's originating order line cannot be replaced."))
            if "origin_returned_move_id" in vals and any(move.origin_returned_move_id.id != (vals["origin_returned_move_id"] or False) for move in protected):
                raise AccessError(_("A scheme reward move's stock return origin cannot be replaced."))
            if any(move.state == "done" for move in protected) and self.env.context.get("_gt_stock_done_token") is not STOCK_DONE_TOKEN:
                immutable = {"quantity", "product_uom_qty", "uom_id", "product_id", "company_id", "sale_line_id", "origin_returned_move_id", "location_id", "location_dest_id", "picking_id"}
                if immutable.intersection(vals):
                    raise AccessError(_("Completed scheme reward movement evidence is immutable."))
        return super().write(vals)

    def unlink(self):
        if any(move.state == "done" and move._scheme_claim_for_p06() for move in self):
            raise UserError(_("Completed scheme reward movements are historical evidence and cannot be deleted."))
        return super().unlink()

    def _scheme_claim_for_p06(self):
        line = self.sale_line_id
        if line and line.order_id.scheme_claim_id:
            return line.order_id.scheme_claim_id
        origin = self.origin_returned_move_id
        if origin and origin.sale_line_id and origin.sale_line_id.order_id.scheme_claim_id:
            return origin.sale_line_id.order_id.scheme_claim_id
        return self.env["gt.distributor.scheme.claim"]

    @api.model
    def _p06_stock_source_validation(self, claim):
        """Evaluate only claim-scoped sources under the original submitter's permissions."""
        validator = claim.submitted_by_id
        if not validator or not any(validator.has_group(group) for group in (
            "gt_distributor_scheme_settlement.group_scheme_operator",
            "gt_distributor_scheme_settlement.group_scheme_manager",
        )) or claim.company_id not in validator.company_ids:
            raise AccessError(_("A claim source reviewer with accounting access is unavailable. Ask a scheme manager to revalidate sources."))
        scoped_claim = claim.with_user(validator).with_company(claim.company_id).with_context(
            allowed_company_ids=[claim.company_id.id]
        )
        return scoped_claim._active_validation()

    def _action_done(self, cancel_backorder=False):
        scoped = self.filtered(lambda move: move._scheme_claim_for_p06())
        claim_ids = sorted({move._scheme_claim_for_p06().id for move in scoped})
        claims = self.env["gt.distributor.scheme.claim"].sudo().browse(claim_ids)
        if claims:
            self.env.cr.execute(
                "SELECT id FROM gt_distributor_scheme_claim WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                [claims.ids],
            )
            claims.invalidate_recordset()
            for claim in claims:
                if claim.company_id != self.env.company or claim.company_id not in self.env.companies:
                    raise AccessError(_("Switch to the claim company before validating its delivery."))
                self.env["account.move"]._gt_lock_scheme_source_scope(
                    claim.company_id.id, claim.distributor_id.commercial_partner_id.id
                )
                claim_moves = scoped.filtered(lambda move: move._scheme_claim_for_p06() == claim)
                for move in claim_moves:
                    if (move.company_id != claim.company_id or move.product_id != claim.approved_reward_product_id
                        or move.sale_line_id and move.sale_line_id.order_id != claim.fulfillment_order_id):
                        raise ValidationError(_("A linked stock move does not match the approved claim, company, product, and fulfillment order."))
                outgoing = claim_moves.filtered(lambda move:
                    not move.origin_returned_move_id and move.location_dest_id.usage == "customer"
                    and move.location_id.usage != "customer"
                )
                returning = claim_moves.filtered(lambda move:
                    move.origin_returned_move_id and move.location_id.usage == "customer"
                    and move.location_dest_id.usage != "customer"
                )
                if outgoing:
                    if claim.state not in ("approved", "fulfillment_in_progress"):
                        raise UserError(_("The approved claim is not open for customer delivery."))
                    if claim._has_blocking_adjustments():
                        raise UserError(_("An unresolved adjustment blocks this reward delivery."))
                    validation = self._p06_stock_source_validation(claim)
                    if not claim._p06_reviewed_source_change_is_safe(validation):
                        raise UserError(_("Delivery blocked: claim accounting sources changed after approval. Ask a scheme manager to review the adjustment."))
                    metrics = claim._fulfillment_metrics()
                    add_qty = sum(move.uom_id._compute_quantity(move.quantity, claim.approved_reward_uom_id, round=False) for move in outgoing)
                    if claim.approved_reward_uom_id.compare(metrics["net"] + add_qty, claim.approved_reward_quantity) > 0:
                        raise UserError(_("Delivery blocked: the proposed completed quantity exceeds the approved entitlement."))
                if returning:
                    metrics = claim._fulfillment_metrics()
                    return_qty = sum(move.uom_id._compute_quantity(move.quantity, claim.approved_reward_uom_id, round=False) for move in returning)
                    if claim.approved_reward_uom_id.compare(metrics["net"] - return_qty, 0.0) < 0:
                        raise UserError(_("The linked reward return exceeds the verified completed delivery quantity."))
        result = super(StockMove, self.with_context(_gt_stock_done_token=STOCK_DONE_TOKEN))._action_done(cancel_backorder=cancel_backorder)
        for claim in claims:
            moves = scoped.filtered(lambda move: move._scheme_claim_for_p06() == claim)
            pickings = moves.mapped("picking_id")
            updates = {"fulfillment_picking_ids": [(4, picking.id) for picking in pickings]}
            returns = moves.filtered(lambda move: move.origin_returned_move_id and move.state == "done")
            if returns and claim.state == "settled":
                qty = sum(move.uom_id._compute_quantity(move.quantity, claim.approved_reward_uom_id, round=False) for move in returns)
                fingerprint = hashlib.sha256(
                    f"reward-return:{claim.id}:{','.join(map(str, sorted(returns.ids)))}:{qty:.12f}".encode()
                ).hexdigest()
                adjustment_model = self.env["gt.distributor.scheme.claim.adjustment"].sudo()
                if not adjustment_model.search_count([("claim_id", "=", claim.id), ("fingerprint", "=", fingerprint)]):
                    adjustment_model.with_context(_gt_adjustment_token=ADJUSTMENT_TOKEN).create({
                        "claim_id": claim.id, "quantity_delta": -qty,
                        "reason": _("A completed customer return affects a previously settled free-goods claim."),
                        "adjustment_type": "reward_return", "fingerprint": fingerprint,
                        "original_entitlement": claim.approved_reward_quantity,
                        "current_entitlement": claim.approved_reward_quantity,
                        "already_fulfilled_quantity": claim.net_fulfilled_quantity,
                        "remaining_undelivered_quantity": claim.outstanding_quantity,
                        "potential_excess_fulfillment": 0.0,
                        "validation_status": claim.source_validation_status,
                        "evidence_payload": {"return_move_ids": sorted(returns.ids), "returned_quantity": qty,
                                             "uom_id": claim.approved_reward_uom_id.id},
                        "detected_by_id": self.env.uid,
                        "status": "open",
                    })
                updates["state"] = "adjustment_required"
            elif claim.state in ("approved", "fulfillment_in_progress"):
                updates["state"] = "fulfillment_in_progress"
            claim.with_context(_gt_claim_write_token=CLAIM_WRITE_TOKEN).write(updates)
            self.env["gt.distributor.scheme.audit"]._record_system_event_for_actor({
                "company_id": claim.company_id.id, "scheme_id": claim.scheme_id.id, "claim_id": claim.id,
                "event_type": "claim_stock_fulfillment_reconciled",
                "evidence": {"claim_id": claim.id, "picking_ids": sorted(pickings.ids),
                             "outbound_move_ids": sorted(moves.filtered(lambda m: m.location_dest_id.usage == "customer").ids),
                             "return_move_ids": sorted(returns.ids), "claim_state": claim.state},
            }, self.env.uid, token=AUDIT_SYSTEM_TOKEN)
        return result


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            move = self.env["stock.move"].browse(vals.get("move_id"))
            if move.state == "done" and move._scheme_claim_for_p06():
                raise AccessError(_("Completed scheme reward operation lines cannot be added."))
        return super().create(vals_list)

    def write(self, vals):
        linked = self.filtered(lambda line: line.move_id._scheme_claim_for_p06())
        if linked and any(line.move_id.state == "done" for line in linked):
            if self.env.context.get("_gt_stock_done_token") is not STOCK_DONE_TOKEN:
                protected = {"move_id", "product_id", "quantity", "quantity_product_uom", "lot_id", "lot_name", "location_id", "location_dest_id", "company_id"}
                if protected.intersection(vals):
                    raise AccessError(_("Completed scheme reward operation lines are immutable."))
        return super().write(vals)

    def unlink(self):
        linked = self.filtered(lambda line: line.move_id.state == "done" and line.move_id._scheme_claim_for_p06())
        if linked:
            raise UserError(_("Completed scheme reward operation lines are historical evidence and cannot be deleted."))
        return super().unlink()
