import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .service_tokens import REVISION_CREATE_TOKEN, REVISION_WRITE_TOKEN


class DistributorSchemeClaimRevision(models.Model):
    _name = "gt.distributor.scheme.claim.revision"
    _description = "Distributor Scheme Claim Revision"
    _order = "claim_id, revision_number desc"
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True, copy=False)
    claim_id = fields.Many2one("gt.distributor.scheme.claim", required=True, ondelete="restrict", check_company=True, index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True, readonly=True, index=True)
    revision_number = fields.Integer(required=True, readonly=True, copy=False)
    prior_revision_id = fields.Many2one("gt.distributor.scheme.claim.revision", readonly=True, ondelete="restrict", check_company=True)
    state = fields.Selection([
        ("proposed", "Proposed"), ("approved", "Approved"),
        ("superseded", "Superseded"), ("rejected", "Rejected"),
    ], required=True, default="proposed", readonly=True, copy=False, index=True)
    requested_by_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    requested_at = fields.Datetime(required=True, readonly=True)
    prepared_by_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    prepared_at = fields.Datetime(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    source_validation_status = fields.Selection([
        ("current", "Current"), ("stale", "Stale"), ("blocked", "Blocked"),
    ], required=True, readonly=True, index=True)
    calculation_cutoff = fields.Datetime(required=True, readonly=True)
    qualifying_product_id = fields.Many2one("product.product", required=True, readonly=True, check_company=True)
    qualifying_uom_id = fields.Many2one("uom.uom", required=True, readonly=True)
    gross_quantity = fields.Float(required=True, readonly=True, digits="Product Unit of Measure")
    refund_quantity = fields.Float(required=True, readonly=True, digits="Product Unit of Measure")
    net_quantity = fields.Float(required=True, readonly=True, digits="Product Unit of Measure")
    slab_id = fields.Many2one("gt.distributor.scheme.slab", required=True, readonly=True, ondelete="restrict")
    reward_product_id = fields.Many2one("product.product", required=True, readonly=True, check_company=True)
    reward_uom_id = fields.Many2one("uom.uom", required=True, readonly=True)
    reward_quantity = fields.Float(required=True, readonly=True, digits="Product Unit of Measure")
    source_fingerprint = fields.Char(required=True, readonly=True, index=True)
    calculation_fingerprint = fields.Char(required=True, readonly=True)
    snapshot_payload = fields.Json(required=True, readonly=True, copy=False)
    snapshot_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    source_validation_result = fields.Json(readonly=True, copy=False)
    decision_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    decision_at = fields.Datetime(readonly=True, copy=False)

    _revision_number_uniq = models.Constraint(
        "unique(claim_id, revision_number)", "Claim revision numbers must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("_gt_revision_create_token") is not REVISION_CREATE_TOKEN:
            raise AccessError(_("Claim revisions can only be prepared by the authorized revision service."))
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("_gt_revision_write_token") is not REVISION_WRITE_TOKEN:
            raise AccessError(_("Claim revision evidence is immutable."))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_("Claim revision history cannot be deleted."))

    def copy(self, default=None):
        raise AccessError(_("Claim revisions cannot be copied."))

    @api.constrains("claim_id", "company_id", "prior_revision_id", "snapshot_payload", "snapshot_hash", "gross_quantity", "refund_quantity", "net_quantity", "reward_quantity")
    def _check_integrity(self):
        for revision in self:
            if revision.company_id != revision.claim_id.company_id:
                raise ValidationError(_("Claim revisions must remain in the claim company."))
            if revision.prior_revision_id and revision.prior_revision_id.claim_id != revision.claim_id:
                raise ValidationError(_("A prior revision must belong to the same logical claim."))
            if revision.gross_quantity < 0 or revision.refund_quantity < 0 or revision.net_quantity < 0 or revision.reward_quantity <= 0:
                raise ValidationError(_("Revision quantities must be non-negative and reward entitlement must be positive."))
            if not revision.snapshot_payload or revision._hash_payload(revision.snapshot_payload) != revision.snapshot_hash:
                raise ValidationError(_("Claim revision snapshot integrity verification failed."))

    @api.model
    def _hash_payload(self, payload):
        canonical = self.env["gt.distributor.scheme.claim"]._canonical_json(payload)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
