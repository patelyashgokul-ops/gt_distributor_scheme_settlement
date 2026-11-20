# Distributor Scheme Settlement

Odoo 20 Community addon by Golok Technology. Support: patelyash.gokul@gmail.com.

P01 provides the scheme, slab, period, claim, source, adjustment, audit, and company-security foundation. P02 added a non-persisting purchase calculator. P03 added a deterministic eligibility engine and authorized read-only preview over posted customer invoices and attributable credit notes. P04 adds protected period closing, draft claim generation, immutable ORM snapshots and source allocation, and CURRENT/STALE/BLOCKED source revalidation. Claims are not approved and no sales order, stock delivery, or financial settlement is created.

## Installation

Copy this directory into an Odoo 20 Community addons path, update the Apps list, and install **Distributor Scheme Settlement**. Dependencies are `sale`, `account`, `stock`, and `mail`, all Community addons in the inspected Odoo 20.0 checkout. The module does not modify Odoo core or vendor addons.

The inspected Odoo 20 checkout declares Python 3.12–3.13 and PostgreSQL 16 minimum. Use a supported Python runtime and a disposable PostgreSQL database for automated tests. Run:

```powershell
python odoo-bin --addons-path="<odoo-addons>,<custom-addons>" --data-dir="<disposable-data-dir>" --db_host=127.0.0.1 --db_port=<disposable-port> --db_user=<test-user> --db_password=<test-password> --database=gt_scheme_p03_test --init=gt_distributor_scheme_settlement --test-tags=/gt_distributor_scheme_settlement --stop-after-init --without-demo
```

Do not point this command at production or shared databases. P01–P03 test evidence and environment limitations are in `TEST_REPORT.md`.

## Security roles

- **Distributor Scheme Operator** can read scheme configuration and use authorized claim submission where source revalidation remains current. Operators cannot create claims directly or edit claim calculations, allocations, lifecycle state, adjustments, or audit evidence.
- **Distributor Scheme Manager** can configure and activate schemes, configure periods, close eligible periods, and start claim review after source revalidation. Approval and fulfillment metadata remain server-blocked for P05/P06.
- **Distributor Scheme Auditor** has read-only access within allowed companies.

Eligibility preview uses the current active scheme company, accounting ACLs, and accounting record rules. Preview operators/managers need Odoo read access to customer invoices and invoice lines; the calculator never uses `sudo()` to obtain accounting data.

Company scoped `ir.access` domain restrictions apply to every model (Odoo 20 combines permission and domain restrictions in this model). Related records also enforce company consistency at ORM level. Audit and adjustment evidence cannot be updated or deleted through normal ORM calls. Odoo superuser mode bypasses access controls by design; privileged custom code must preserve these invariants.

## P03 eligibility preview contract

The preview reads posted customer invoices and linked posted customer credit notes using their business invoice dates, exact scheme company, qualifying product, and P02 commercial-partner distributor identity. It counts only positive quantity product lines with positive untaxed subtotal, normalizes through Odoo 20 UoM references, blocks uncertain refund attribution, selects one highest slab, and returns source evidence plus a deterministic SHA-256 fingerprint. It writes only the temporary wizard result; it does not create claim snapshots. Its explicit as-of cutoff blocks relevant current documents/lines changed after that time because Odoo does not retain old line versions. Odoo's PostgreSQL repeatable-read transaction provides a consistent read snapshot; parallel preview behavior has not been stress tested.

## Remaining business contracts (P05–P08)

These are design contracts, not implemented behavior. Future services must expose explicit success/failure results and be safe under direct ORM/RPC/import and concurrent invocation.

1. **Ownership and scope:** each claim is for exactly one scheme, scheme-specific period, distributor, and company. Every source invoice, refund, line, claim, adjustment, and fulfillment record must match that company and distributor. Reject cross-company, cross-distributor, out-of-period, or otherwise stale evidence.
2. **Period and claim policy:** P04 closes periods atomically and idempotently and creates at most one claim per scheme, company, distributor, and period. It persists calculation/source snapshots. True concurrent close and cross-scheme allocation races still need independent-cursor tests.
3. **Evidence immutability and adjustments:** P04 protects claim and source snapshots through ORM guards and hashes; database administrators remain outside this application-level guarantee. Corrections append adjustment records; they never rewrite or erase source evidence. Late returns after period close need the P06 adjustment workflow.
4. **Stale claim and approval controls:** P04 compares current source state to the snapshot and blocks stale claim submission/review. P05 must enforce mandatory revalidation before manager approval, maker-checker authorization, approval freezing, and controlled revisions.
5. **Free-goods fulfillment:** fulfillment creates a sales order for the reward product at zero price, with explicit company, distributor, and claim links. Enforce an idempotency key/unique claim link so fulfilled free goods cannot be issued twice. Reconcile fulfillment against actual completed delivery quantities from stock pickings; an order alone is not delivery.
6. **Failure and concurrency:** database uniqueness and row-level locking or equivalent serialization must prevent duplicate claims and duplicate fulfillment under concurrent runs. A failed or partial operation must never report success; retries must not duplicate claims, orders, or deliveries.

## License

The manifest declares `OPL-1`. This addon contains no copied Odoo source and depends only on the inspected Community addons, whose manifests declare LGPL-3. Odoo's [license terms](https://www.odoo.com/documentation/17.0/legal/licenses.html) describe modules using Odoo as a library and allow their distribution under a compatible license; its [manifest documentation](https://www.odoo.com/documentation/master/developer/reference/backend/module.html) recognizes `OPL-1`. The Community LGPL dependencies do not prevent declaring this addon OPL-1. Confirm publisher ownership and final distribution terms before release.
