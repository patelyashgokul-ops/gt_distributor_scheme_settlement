# P01-P02 Verification Report

Date: 2026-11-20

## Environment evidence

- Odoo source: `C:\PycharmProjects\odoo20\odoo-20.0`, release source reports 20.0.0 final.
- Community addons: `C:\PycharmProjects\odoo20\odoo-20.0\addons`.
- Project virtual environment: `C:\PycharmProjects\odoo20\.venv`, Python 3.14.6. It has `psycopg2` and `lxml`; Odoo is loaded from source.
- Odoo 20 source declares Python 3.12 minimum, Python 3.14 maximum exclusive, and PostgreSQL 16 minimum. Therefore the discovered Python 3.14.6 runtime is outside the supported range.
- PostgreSQL 18 Windows service is running. No credentials or database contents were inspected. No existing database was used.
- An isolated PostgreSQL 18 cluster initialized successfully under `.test/pgdata`. `pg_ctl start` failed with Windows sandbox restricted-token errors, but launching `postgres.exe` directly in the foreground worked on port 55498. Tests used only a disposable database and `.test` filestore; both were removed after verification. No existing service database was used.
- Odoo source inspection confirmed `sale.order` (`sale/models/sale_order.py`); `account.move` and `account.move.line` (`account/models`); `stock.picking` (`stock/models/stock_picking.py`); `product.product` (`product/models/product_product.py`); and `res.partner` (`odoo/addons/base/models/res_partner.py`). The inspected fields include move type/state/invoice date/reversed-entry link, move-line product/UoM/quantity/document links, picking state/company/return link, product UoM, and partner company identity. Odoo 20 core uses `<list>` views, `res.groups.privilege`, `res.users.group_ids`, `ir.access` permission/domain records, `models.Constraint`, and `fields.Json`.
- License evidence: the Community checkout's dependency manifests use LGPL-3. Odoo's published license documentation lists OPL-1 as a supported module manifest license and permits compatible licenses for modules using Odoo as a library. This addon contains no copied Odoo source. This is a technical compatibility check, not legal advice.

## Results

| Check | Result | Evidence |
|---|---|---|
| Odoo 20 Community source discovered | PASS | `odoo/release.py` reports 20.0; Community addons tree is present. |
| Runtime / PostgreSQL config verified | PARTIAL | Python 3.14.6 is outside Odoo 20's supported range. An isolated PostgreSQL 18 cluster and disposable database were successfully used for module tests. |
| Required source model/API inspection | PASS | All named source models and baseline accounting, product, partner, and stock fields listed above were inspected. Future workflow APIs still need focused verification when implemented. |
| Manifest metadata and dependency declarations | PASS | Odoo 20 manifest structure; dependencies are Community addons `sale`, `account`, `stock`, `mail`; version `20.0.2.0.0` after P02. |
| OPL-1 metadata and dependency licensing | PASS | OPL-1 manifest value; dependency manifests declare LGPL-3; no source copied. Publisher/distribution legal review remains outside this technical check. |
| Python syntax compilation | PASS | All 13 addon Python files compiled with Python 3.14.6. Odoo runtime compatibility remains limited by this unsupported interpreter. |
| XML well-formedness and manifest literal parsing | PASS | All 7 XML files parsed and manifest loaded as a Python literal; Odoo installation also validated view schemas and data references. |
| Registry setup, fresh install, ACL/rule evaluation, and module tests | PASS (unsupported interpreter) | Fresh module installation loaded the registry and addon XML/security. All 9 addon post-install tests passed on Python 3.14.6/PostgreSQL 18 using a disposable database. Odoo 20 declares Python 3.12–3.13 support; repeat on a supported interpreter before release. |

The successful P01 filtered run used `--update=gt_distributor_scheme_settlement --test-tags=/gt_distributor_scheme_settlement` on disposable database `gt_scheme_p01_test`; Odoo reported `0 failed, 0 error(s) of 9 tests`. The full run log is `.test/odoo-targeted-all.log`. A separate broad core test run on Python 3.14.6 hit an unrelated Odoo core attachment memory assertion; the P01 final run was filtered to this addon.

## P02 results

| Check | Result | Evidence |
|---|---|---|
| Posted invoice/refund source selection | PASS (unsupported interpreter) | 11 addon tests passed on disposable database `gt_scheme_p02_test`; posted invoice quantities counted, draft invoice excluded, linked refund subtracted, and a refund linked to an invoice outside the period rejected for review. |
| Odoo 20 UoM conversion and highest qualifying slab | PASS (unsupported interpreter) | Test converts 120 units and a 24-unit refund to a net 8 dozen, then selects the [8, 12) slab only. Odoo 20 source uses the UoM common-reference hierarchy and Product Unit decimal precision. |
| Non-persisting entitlement service and authorization | PASS (unsupported interpreter) | Calculator returns explicit result/evidence without creating claims; role boundary test denies an unassigned user. |
| P02 Python syntax, XML, install, and registry | PASS (unsupported interpreter) | Fresh install plus module update/test loaded the registry and XML; static compilation and XML parsing repeated after final edits. |
| Supported Python runtime | NOT RUN | Available environment is Python 3.14.6; Odoo 20 declares Python 3.12 through 3.13. Repeat under a supported interpreter. |

Final P02 command (PowerShell; isolated cluster and database only):

```powershell
& C:\PycharmProjects\odoo20\.venv\Scripts\python.exe C:\PycharmProjects\odoo20\odoo-20.0\odoo-bin --addons-path=C:\PycharmProjects\odoo20\odoo-20.0\odoo\addons,C:\PycharmProjects\odoo20\custom_addons --data-dir=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-data --db_host=127.0.0.1 --db_port=55498 --db_user=odoo_test --db_password=odoo_test --database=gt_scheme_p02_test --update=gt_distributor_scheme_settlement --without-demo=all --test-enable --test-tags=/gt_distributor_scheme_settlement --stop-after-init --http-port=8095 --logfile=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-p02-rerun.log
```

Odoo reported `0 failed, 0 error(s) of 11 tests` in `.test/odoo-p02-rerun.log`. The disposable database, filestore, and temporary PostgreSQL cluster were removed/stopped after verification; logs remain under `.test`.

## P03 implementation and verification

### Implementation

- Reworked `models/calculator.py` into a reusable, permission-checked read-only service. The P02 `calculate_entitlement(scheme_id, distributor_id, period_id)` entry point remains as a compatibility wrapper and preserves its earlier `qualified` / `below_threshold` status and review exception behavior.
- Added `calculate_eligibility(scheme_id, distributor_id, date_start, date_end, as_of)`, explicit `ELIGIBLE` / `NOT_ELIGIBLE` / `BLOCKED` outcomes, scoped exception codes, deterministic sorted evidence, and a SHA-256 source fingerprint.
- Added native `gt.distributor.scheme.preview.wizard`, form, scheme button, role ACLs, result tamper guard, and source evidence display. Preview does not create persistent claims, stock moves, or accounting entries.
- The engine retains P02 commercial-partner matching. A test verifies that an invoice on a child contact resolves to its configured distributor company, matching P02 behavior.
- Uses only `account.move` and `account.move.line` with company, commercial partner, `out_invoice`/`out_refund`, posted state, invoice date, and qualifying product scope. Sales orders and stock records are not purchase fallbacks. Odoo 20 source confirms `move_type`, `state`, `invoice_date`, `commercial_partner_id`, `reversed_entry_id`, `display_type`, `product_id`, `product_uom_id`, `quantity`, `price_subtotal`, `create_date`, and `write_date`.
- Counts only `display_type == 'product'` qualifying lines with positive untaxed subtotal and positive quantity. Zero-value and fully discounted lines are retained as excluded evidence; negative value/quantity and incompatible UoMs block the preview.
- Refunds are attributed through Odoo 20 `reversed_entry_id`. Only a one-to-one qualifying product line on the source invoice and credit note is accepted. Ambiguous multi-line attribution, unlinked in-period credit notes, over-refunds, and late changes after the selected cutoff are exposed as blocking exceptions; no line is guessed. Posted invoices reversing posted credit notes restore their attributed quantity when one-to-one linkage is available.
- UoM compatibility uses Odoo 20's `_has_common_reference`; conversion calls `_compute_quantity(..., round=False)`. Aggregation uses `math.fsum` for invoice quantities, and comparisons use 12 decimal places so an input just below a slab boundary is not promoted by two-decimal rounding. Refunds use the same conversion path.
- Source evidence includes company/distributor, move and line IDs, document type/state/date, source UoM/quantity, normalized quantity, untaxed line subtotal, create/write timestamps, origin and classification. Stable identity sorting feeds the fingerprint. No persistent snapshot is claimed.
- Historical cutoff policy: current posted source rows are included only when their `create_date` and `write_date` are not later than the explicit cutoff. A relevant source written after it blocks the preview because Odoo does not preserve old line values. New backdated entries are therefore detected as a cutoff exception; a current-time preview includes them and changes the fingerprint. This is not a reconstruction of prior database states.
- Odoo 20 source `odoo/sql_db.py` sets `ISOLATION_LEVEL_REPEATABLE_READ`; the calculator performs no commits or writes. Concurrent read consistency relies on that transaction snapshot, but no concurrent integration test was run.

### Final test evidence

| Check | Result | Evidence |
|---|---|---|
| Clean install, registry, wizard view and ACL load | PASS (Python 3.14.6 unsupported) | Fresh disposable database `gt_scheme_p03_test`; Odoo loaded the addon, new transient model, ACL rows, and preview XML. The initial full run then exposed test defects; the final module update run below passed. |
| P01/P02 regression and P03 ORM suite | PASS (Python 3.14.6 unsupported) | Odoo final result: `0 failed, 0 error(s) of 27 tests`; module test statistics: 29 tests (Odoo framework accounting differs by two from the result summary). `.test/odoo-p03-rerun.log`. |
| Python syntax / XML / manifest | PASS | 15 Python files parsed, 8 XML files parsed, manifest literal loaded using Python 3.14.6 after final source changes. |
| P03 production Python support | NOT RUN | Only Python 3.14.6 was available; Odoo 20 source declares Python 3.12–3.13. |
| Large-volume performance benchmark | NOT RUN | No 1,000-line or representative distributor-volume benchmark was executed. Final Odoo run reported 6,774 module-stat queries across tests, not a performance benchmark. |
| Real concurrent preview/source-write test | NOT RUN | Repeatable-read behavior was verified in source; tests were sequential and do not establish concurrency behavior under parallel requests. |

Final passing command (PowerShell; isolated UTF-8 PostgreSQL 18 cluster, port 55498; disposable DB and filestore only):

```powershell
& C:\PycharmProjects\odoo20\.venv\Scripts\python.exe C:\PycharmProjects\odoo20\odoo-20.0\odoo-bin --addons-path=C:\PycharmProjects\odoo20\odoo-20.0\odoo\addons,C:\PycharmProjects\odoo20\custom_addons --data-dir=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-data --db_host=127.0.0.1 --db_port=55498 --db_user=odoo_test --db_password= --database=gt_scheme_p03_test --update=gt_distributor_scheme_settlement --without-demo --test-enable --test-tags=/gt_distributor_scheme_settlement --stop-after-init --http-port=8095 --logfile=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-p03-rerun.log
```

### Acceptance matrix

- **AC-11 posted invoice source only: PASS.** Actual ORM tests cover posted/draft invoices, posted/unposted credit notes, and vendor bills. The query also restricts the document type to `out_invoice` and state to `posted`; no sale order, purchase order, or stock source is searched.
- **AC-12 customer, product, company and date matching: PASS.** Actual tests cover product and invoice-date filtering, same shared product in two companies, the other-company invoice exclusion, exact eligible distributor company partner through P02 commercial-partner matching, and child-contact identity behavior.
- **AC-13 free and zero-value exclusion: PASS.** Actual test covers zero-price and fully discounted qualifying product lines and verifies only paid quantity contributes.
- **AC-14 refund adjustments: PASS for supported attribution cases.** Actual tests cover linked partial/multiple/late refunds, unposted/unlinked/out-of-period refunds, ambiguous line attribution, credit notes exceeding original quantity, and an invoice reversing a credit note. Ambiguous product-line mappings block; they are not guessed.
- **AC-15 UoM conversion and boundaries: PASS.** P02 regression test performs actual unit-to-dozen invoice/refund conversion; P03 tests incompatible UoM blocking and the exclusive slab boundary immediately below minimum without rounding up.
- **AC-16 period and cutoff policy: PASS.** Scheme/request date containment, invoice-date filtering, explicit cutoff, late linked credit note, post-cutoff backdated source blocking, stable fingerprints, and changed-source fingerprints are covered. Historical prior line values are not reconstructed.

### Remaining security and implementation limits

- Preview requires scheme operator/manager membership **and** standard accounting read access to `account.move` and `account.move.line`; this intentionally does not bypass accounting ACLs. Production role setup must grant these rights where previews are needed.
- The source search is scoped by company, commercial partner, document type, posted state, date, and product. A same-company wrong-distributor credit note or a different-company credit note is excluded by normal source visibility and cannot be used to reduce the entitlement. No source data is returned for records outside the request scope.
- Account data has no historical line-version store. As-of behavior uses current `create_date`/`write_date` as conservative availability guards; relevant after-cutoff changes block. This avoids fabricated historical quantities but cannot reconstruct data overwritten before the first preview.
- Performance with 1,000+ invoice lines, parallel preview calls, direct import vectors, and parallel accounting writes remain unverified. No settlement claim snapshot is persisted. Period closure/claim generation, immutable evidence, approval, fulfillment, post-approval adjustments, and financial settlement remain P04–P08 work.
- P03 is not ready to publish; supported-Python testing and the deferred scale/concurrency checks are still required before a production release.

## Acceptance checks

- **AC-01 fresh install and registry:** PASS (Python 3.14.6 unsupported) — module installed into a fresh disposable Odoo 20 database; registry loaded.
- **AC-02 required fields and validations:** PASS (Python 3.14.6 unsupported) — required fields, invalid dates and slab quantities, and unimplemented-state guards covered by addon tests.
- **AC-03 company isolation and authorization:** PASS (Python 3.14.6 unsupported) — ACLs, Odoo 20 company-scoped `ir.access` domains, and cross-company checks covered by addon tests.
- **AC-04 immutable audit/evidence:** PASS (Python 3.14.6 unsupported) — audit modification restrictions covered by tests; source and adjustment evidence are append-only at ORM level.
- **AC-05 native views and menu references:** PASS (Python 3.14.6 unsupported) — Odoo view schemas and menu/action references loaded successfully; test verifies key external IDs.
- **AC-06 no unimplemented workflow claims:** PASS - no calculation action is exposed in the UI; the P02 calculator is a permission-checked, non-persisting service only. No claim-close, approval, fulfillment, or settlement operation is exposed; claim lifecycle and metadata writes remain server-blocked.

## Security limitations and deferred work

- Odoo superuser mode intentionally bypasses access controls. Future privileged services need their own explicit authorization and invariant checks.
- Full multi-company access combinations, import/RPC vectors, and concurrent attempts still require targeted runtime tests. Tests used the discovered unsupported Python 3.14.6 runtime. A broad Odoo core test run also hit an unrelated core attachment memory assertion, so the successful run was filtered to this addon.
- Period closing, claim generation, immutable document snapshot capture, stale evidence detection, manager approval, zero-priced sales orders, delivery reconciliation, and late-return adjustment workflow remain deferred to P03–P08. P02's calculator is non-persisting; refunds linked outside the requested period raise a review exception instead of being adjusted automatically.
- The addon now includes a non-persisting P02 purchase calculator, but period closing through settlement remains unfinished; it is not ready to publish.
