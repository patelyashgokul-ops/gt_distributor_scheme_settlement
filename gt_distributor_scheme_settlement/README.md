# Distributor Scheme Settlement

Odoo 20 Community addon by Golok Technology. Support: patelyash.gokul@gmail.com.

The P01 foundation stores schemes, purchase slabs, periods, claims, source evidence, adjustments, and append-only audit records. P02 adds a permission-checked, non-persisted purchase calculation from posted invoices and linked refunds, including UoM conversion and highest-slab selection. It does not create claims, transition workflows, approve claims, create sales orders, reconcile deliveries, or settle claims.

## Installation

Copy this directory into an Odoo 20 Community addons path, update the Apps list, and install **Distributor Scheme Settlement**. Dependencies are `sale`, `account`, `stock`, and `mail`, all Community addons in the inspected Odoo 20.0 checkout. The module does not modify Odoo core or vendor addons.

The inspected Odoo 20 checkout declares Python 3.12–3.13 and PostgreSQL 16 minimum. Use a supported Python runtime and a disposable PostgreSQL database for automated tests. Run:

```powershell
python odoo-bin --addons-path="<odoo-addons>,<custom-addons>" --data-dir="<disposable-data-dir>" --db_host=127.0.0.1 --db_port=<disposable-port> --db_user=<test-user> --db_password=<test-password> --database=gt_scheme_p02_test --init=gt_distributor_scheme_settlement --test-tags=/gt_distributor_scheme_settlement --stop-after-init --without-demo
```

Do not point this command at production or shared databases. P01 and P02 test evidence and environment limitations are in `TEST_REPORT.md`.

## Security roles

- **Distributor Scheme Operator** can read scheme configuration, create and edit draft claim records, and append source evidence. Operators cannot modify scheme configuration, lifecycle state, approval metadata, fulfillment metadata, adjustments, or audit evidence.
- **Distributor Scheme Manager** can configure schemes, slabs, and periods, and manage claims. Workflow state transitions and approval/fulfillment metadata remain server-blocked until their workflows are implemented.
- **Distributor Scheme Auditor** has read-only access within allowed companies.

Company scoped `ir.access` domain restrictions apply to every model (Odoo 20 combines permission and domain restrictions in this model). Related records also enforce company consistency at ORM level. Audit and adjustment evidence cannot be updated or deleted through normal ORM calls. Odoo superuser mode bypasses access controls by design; privileged custom code must preserve these invariants.

## Remaining business contracts (P03–P08)

These are design contracts, not implemented behavior. Future services must expose explicit success/failure results and be safe under direct ORM/RPC/import and concurrent invocation.

1. **Eligibility and source evidence:** P02's calculator selects only same-company, same-distributor `out_invoice` and `out_refund` documents in `posted` state and within the requested period. It filters to the scheme qualifying product. Draft/cancelled documents are excluded. Unlinked refunds and refunds linked outside the period's eligible invoices raise review exceptions. Immutable persisted source snapshots remain future work.
2. **Ownership and scope:** each claim is for exactly one scheme, scheme-specific period, distributor, and company. Every source invoice, refund, line, claim, adjustment, and fulfillment record must match that company and distributor. Reject cross-company, cross-distributor, out-of-period, or otherwise stale evidence.
3. **Quantity policy:** convert invoice quantities into the scheme qualifying UoM using Odoo 20's UoM common-reference hierarchy and conversion API. Reject incompatible UoMs; do not compare raw quantities across units.
4. **Slab policy:** apply only the single highest qualifying slab. A slab's minimum is inclusive and its optional upper boundary is exclusive. Overlapping slabs are invalid. Do not cumulate rewards from multiple slabs.
5. **Period and claim policy:** period close must be idempotent and serialized against competing close runs. Create at most one claim per scheme, company, distributor, and period. Persist the exact calculation inputs and source evidence used.
6. **Evidence immutability and adjustments:** persist an immutable snapshot of each qualifying posted invoice/refund line, including document identity, company, partner, dates, product, UoM, quantity, currency, amounts, and relevant links. Corrections append adjustment records; they never rewrite or erase source evidence. Late returns after period close must create an explicit exception and adjustment workflow.
7. **Stale claim and approval controls:** before approval, compare current source state with the stored evidence and flag changed, reversed, or newly returned source documents. Approval must be manager-authorized on the server, auditable, and maker-checker protected; stale claims require review instead of silent approval.
8. **Free-goods fulfillment:** fulfillment creates a sales order for the reward product at zero price, with explicit company, distributor, and claim links. Enforce an idempotency key/unique claim link so fulfilled free goods cannot be issued twice. Reconcile fulfillment against actual completed delivery quantities from stock pickings; an order alone is not delivery.
9. **Failure and concurrency:** database uniqueness and row-level locking or equivalent serialization must prevent duplicate claims and duplicate fulfillment under concurrent runs. A failed or partial operation must never report success; retries must not duplicate claims, orders, or deliveries.

## License

The manifest declares `OPL-1`. This addon contains no copied Odoo source and depends only on the inspected Community addons, whose manifests declare LGPL-3. Odoo's [license terms](https://www.odoo.com/documentation/17.0/legal/licenses.html) describe modules using Odoo as a library and allow their distribution under a compatible license; its [manifest documentation](https://www.odoo.com/documentation/master/developer/reference/backend/module.html) recognizes `OPL-1`. The Community LGPL dependencies do not prevent declaring this addon OPL-1. Confirm publisher ownership and final distribution terms before release.
