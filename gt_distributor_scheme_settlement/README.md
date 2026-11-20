# Distributor Scheme Settlement

Odoo 20 Community addon by Golok Technology. Support: patelyash.gokul@gmail.com.

P01 provides the scheme, slab, period, claim, source, adjustment, audit, and company-security foundation. P02 added a non-persisting purchase calculator. P03 added a deterministic eligibility engine and authorized read-only preview over posted customer invoices and attributable credit notes. P04 adds protected period closing, draft claim generation, immutable ORM snapshots and source allocation, and CURRENT/STALE/BLOCKED source revalidation. P05 adds manager review, approval/rejection, self-approval prevention, mandatory source revalidation, frozen approval evidence, and controlled claim revisions. P06 adds authorized zero-priced reward orders, standard Odoo Sales/Inventory delivery linkage, delivered/returned quantity reconciliation, fulfillment adjustments, source monitoring, and settlement completion evidence.

## Installation

Copy this directory into an Odoo 20 Community addons path, update the Apps list, and install **Distributor Scheme Settlement**. Dependencies are `sale_stock`, `account`, and `mail`; the inspected Odoo 20 Community `sale_stock` addon depends on Community `sale`, `stock`, and `stock_account`. The module does not modify Odoo core or vendor addons.

The inspected Odoo 20 checkout declares Python 3.12–3.13 and PostgreSQL 16 minimum. Use a supported Python runtime and a disposable PostgreSQL database for automated tests. Run:

```powershell
python odoo-bin --addons-path="<odoo-addons>,<custom-addons>" --data-dir="<disposable-data-dir>" --db_host=127.0.0.1 --db_port=<disposable-port> --db_user=<test-user> --db_password=<test-password> --database=gt_scheme_p03_test --init=gt_distributor_scheme_settlement --test-tags=/gt_distributor_scheme_settlement --stop-after-init --without-demo
```

Do not point this command at production or shared databases. P01–P05 test evidence and environment limitations are in `TEST_REPORT.md`.

## Security roles

- **Distributor Scheme Operator** can read scheme configuration, submit permitted claims, and request a controlled revision. Operators cannot create claims directly, approve/reject claims, or edit claim calculations, allocations, decision fields, or audit evidence.
- **Distributor Scheme Manager** can configure and activate schemes, close eligible periods, review claims, and approve or reject them after mandatory source revalidation. A claim creator, submitter, historical revision requester, or preparer cannot approve that entitlement.
- **Distributor Scheme Auditor** has read-only access within allowed companies.

Eligibility preview uses the current active scheme company, accounting ACLs, and accounting record rules. Preview operators/managers need Odoo read access to customer invoices and invoice lines; the calculator never uses `sudo()` to obtain accounting data.

Company scoped `ir.access` domain restrictions apply to every model (Odoo 20 combines permission and domain restrictions in this model). Related records also enforce company consistency at ORM level. Audit and adjustment evidence cannot be updated or deleted through normal ORM calls. Odoo superuser mode bypasses access controls by design; privileged custom code must preserve these invariants.

## P03 eligibility preview contract

The preview reads posted customer invoices and linked posted customer credit notes using their business invoice dates, exact scheme company, qualifying product, and P02 commercial-partner distributor identity. It counts only positive quantity product lines with positive untaxed subtotal, normalizes through Odoo 20 UoM references, blocks uncertain refund attribution, selects one highest slab, and returns source evidence plus a deterministic SHA-256 fingerprint. It writes only the temporary wizard result; it does not create claim snapshots. Its explicit as-of cutoff blocks relevant current documents/lines changed after that time because Odoo does not retain old line versions. Odoo's PostgreSQL repeatable-read transaction provides a consistent read snapshot; parallel preview behavior has not been stress tested.

## P06 fulfillment and settlement contract

Only a manager may create a fulfillment order. The service revalidates the claim, uses the frozen approved reward, product, UoM, and quantity, requires an explicit warehouse if the company has multiple warehouses, and creates one protected zero-price `sale.order` per claim. Managers receive Sales User access because standard sale order creation and confirmation require it. A nonzero payable amount from configured taxes blocks order creation. The workflow does not create customer invoices, credit notes, or custom journal entries.

P05 source revalidation and approval coordinate with supported ORM posting/editing of customer invoices and refunds through a database guard row scoped to company and distributor. A source mutation racing with approval causes a safe transaction conflict. Direct SQL or external database writes bypass these Odoo hooks and are outside the addon-level guarantee; production database access must therefore remain restricted.

1. **Ownership and scope:** each claim is for exactly one scheme, scheme-specific period, distributor, and company. Every source invoice, refund, line, claim, adjustment, and fulfillment record must match that company and distributor. Reject cross-company, cross-distributor, out-of-period, or otherwise stale evidence.
2. **Period and claim policy:** P04 closes periods atomically and idempotently and creates at most one claim per scheme, company, distributor, and period. It persists calculation/source snapshots. Same-period close and cross-scheme source-allocation races passed independent-cursor tests.
3. **Evidence immutability and adjustments:** P04 protects claim and source snapshots through ORM guards and hashes; database administrators remain outside this application-level guarantee. Corrections append adjustment records; they never rewrite or erase source evidence. Late returns after period close need the P06 adjustment workflow.
4. **Stale claim and approval controls:** P04 compares current source state to its snapshot. P05 blocks stale approval, enforces manager authorization and separation of duties, freezes the approved entitlement, and stores controlled revisions without replacing the original snapshot.
5. **Free-goods fulfillment:** completed stock moves to a customer location count as outbound delivery; completed returns must link to those original moves. Internal transfers, drafts, reservations, and order quantities do not count. Standard routes/backorders remain authoritative. Partial quantities stay outstanding. Settlement requires actual net customer-facing delivery equal to the approved amount, with no material open adjustment.
6. **Failure and concurrency:** order creation uses a unique claim relationship and claim row lock; stock completion locks claim/source scope and checks the remaining entitlement at the standard move completion boundary. Adjustment evidence is append-only; review acknowledgement is not evidence of physical or financial recovery. Concurrent stock/warehouse race tests and multi-step-route coverage remain outstanding.

Odoo superuser/database administrator operations and direct SQL are outside addon-level tamper resistance. Unsupported tax setups, post-approval quantity changes, and fulfillment replacement after order cancellation are blocked for manual review rather than automatically corrected.

## Remaining work (P07–P08)

P07: reporting, secure exports/aggregations, security/usability and performance review. P08: upgrade/release verification, documentation, final package and publication checks. P06 does not make the application release-ready.

## License

The manifest declares `OPL-1`. This addon contains no copied Odoo source and depends only on the inspected Community addons, whose manifests declare LGPL-3. Odoo's [license terms](https://www.odoo.com/documentation/17.0/legal/licenses.html) describe modules using Odoo as a library and allow their distribution under a compatible license; its [manifest documentation](https://www.odoo.com/documentation/master/developer/reference/backend/module.html) recognizes `OPL-1`. The Community LGPL dependencies do not prevent declaring this addon OPL-1. Confirm publisher ownership and final distribution terms before release.
