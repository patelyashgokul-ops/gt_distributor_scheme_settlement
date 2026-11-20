# P01-P04 Verification Report

Date: 2026-11-20

## Environment evidence

- Odoo source: `C:\PycharmProjects\odoo20\odoo-20.0`, release source reports 20.0.0 final.
- Community addons: `C:\PycharmProjects\odoo20\odoo-20.0\addons`.
- Project virtual environment: `C:\PycharmProjects\odoo20\.venv`, Python 3.14.6. System Python 3.11.9 is also installed; neither is in Odoo 20's supported 3.12–3.13 range. The project environment has `psycopg2` and `lxml`; Odoo is loaded from source.
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
- Manifest version is now `20.0.3.0.0`; the addon still depends only on Community `sale`, `account`, `stock`, and `mail`. No core or vendor source was modified.
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
| Clean install, registry, wizard view and ACL load | PASS (Python 3.14.6 unsupported) | Fresh disposable database `gt_scheme_p03_test`; Odoo loaded the addon, new transient model, ACL rows, and preview XML in the final clean install run. |
| P01/P02 regression and P03 ORM suite | PASS (Python 3.14.6 unsupported) | Fresh disposable DB. Odoo final result: `0 failed, 0 error(s) of 31 tests`; module statistics: 31 tests, 7,491 queries. 29 addon test methods started. `.test/odoo-p03-completion.log`. |
| 1,000-line accounting volume check | PASS (Python 3.14.6 unsupported) | Real posted invoice containing 1,000 qualifying product lines was previewed; all lines were counted once, with correct aggregate quantity and one source invoice. Included in the final suite. This is a functional volume check, not a broad load benchmark. |
| Explicit cross-company scheme-ID injection | PASS (Python 3.14.6 unsupported) | A company-A manager directly called the calculator with a company-B scheme ID and was denied by server-side access checks. Included in the final suite. |
| Python syntax / XML / manifest | PASS | 15 Python files parsed, 8 XML files parsed, manifest literal loaded using Python 3.14.6 after final source changes. |
| P03 production Python support | NOT RUN | Only Python 3.14.6 was available; Odoo 20 source declares Python 3.12–3.13. |
| Targeted source-scoping/performance profile | PASS (Python 3.14.6 unsupported) | Disposable Odoo DB with 100 distributors, 1,002 posted customer invoices, and 10 posted credit notes. The target preview included 12 invoices / 10 refunds, returned 22 source rows, calculated 39 net units in 0.1744s and 30 SQL queries. This is a measured synthetic sample, not a broad load sweep. `.test/odoo-p03-performance.log`. |
| Concurrent preview with source posting | PASS (Python 3.14.6 unsupported) | Two independent Odoo/PostgreSQL transactions: reader established its Repeatable Read snapshot; a writer posted a new relevant customer invoice and committed; reader returned the original 10-unit result, while a fresh preview returned 30 units with a changed fingerprint. `.test/odoo-p03-concurrency.log`; probe code `.test/concurrency_probe.py`. |
| Broad load sweep / query scaling | NOT RUN | A single synthetic 100-distributor / 1,002-invoice dataset was measured. Larger dataset sweeps and production-like query plans were not run. |

Final passing command (PowerShell; isolated UTF-8 PostgreSQL 18 cluster, port 55498; disposable DB and filestore only):

```powershell
& C:\PycharmProjects\odoo20\.venv\Scripts\python.exe C:\PycharmProjects\odoo20\odoo-20.0\odoo-bin --addons-path=C:\PycharmProjects\odoo20\odoo-20.0\odoo\addons,C:\PycharmProjects\odoo20\custom_addons --data-dir=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-data --db_host=127.0.0.1 --db_port=55498 --db_user=odoo_test --db_password= --database=gt_scheme_p03_final_test --init=gt_distributor_scheme_settlement --without-demo --test-enable --test-tags=/gt_distributor_scheme_settlement --stop-after-init --http-port=8095 --logfile=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-p03-completion.log
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
- A functional 1,000-line test, targeted 1,002-invoice performance profile, and real concurrent preview/source-posting probe pass on the isolated database. Broad load sweeps and import-specific vectors beyond direct unauthorized method/ID calls remain unverified. At P03, no settlement snapshot was persisted. Period closing, claim generation, and snapshots are implemented in P04; approval, fulfillment, post-approval adjustments, and financial settlement remain later work.
- Odoo 20 supported-Python testing is still outstanding: this machine exposes Python 3.11.9 and 3.14.6 only. The successful run used 3.14.6, outside the declared 3.12–3.13 range. The addon is not ready to publish until the module suite passes on a supported runtime; broader load sweeps and import-specific security vectors remain additional validation.

## Acceptance checks

- **AC-01 fresh install and registry:** PASS (Python 3.14.6 unsupported) — module installed into a fresh disposable Odoo 20 database; registry loaded.
- **AC-02 required fields and validations:** PASS (Python 3.14.6 unsupported) — required fields, invalid dates and slab quantities, and unimplemented-state guards covered by addon tests.
- **AC-03 company isolation and authorization:** PASS (Python 3.14.6 unsupported) — ACLs, Odoo 20 company-scoped `ir.access` domains, and cross-company checks covered by addon tests.
- **AC-04 immutable audit/evidence:** PASS (Python 3.14.6 unsupported) — audit modification restrictions covered by tests; source and adjustment evidence are append-only at ORM level.
- **AC-05 native views and menu references:** PASS (Python 3.14.6 unsupported) — Odoo view schemas and menu/action references loaded successfully; test verifies key external IDs.
- **AC-06 no unimplemented workflow claims:** PASS - no calculation action is exposed in the UI; the P02/P03 calculator is a permission-checked, non-persisting service and the P03 preview wizard is read-only. No claim-close, approval, fulfillment, or settlement operation is exposed; claim lifecycle and metadata writes remain server-blocked.

## Security limitations and deferred work

- Odoo superuser mode intentionally bypasses access controls. Future privileged services need their own explicit authorization and invariant checks.
- Direct cross-company scheme-ID injection and concurrent posting/read snapshot behavior are covered. Broader multi-company source-access combinations and import-specific vectors remain to be tested. Tests used the discovered unsupported Python 3.14.6 runtime. A broad Odoo core test run also hit an unrelated core attachment memory assertion, so successful module runs are filtered to this addon.
- P03 itself provides read-only eligibility previews only. P04 now adds period closing, claim generation, immutable source snapshots, and stale claim revalidation. Manager approval, zero-priced sales orders, delivery reconciliation, and late-return adjustment workflow remain deferred to P05–P08.
- The addon is not ready to publish; supported-Python validation and broad load-sweep work remain.

## P04 period closing, claims, and snapshots

### Implemented

- Added a manager-authorized scheme activation action because P04 period closing requires an active scheme. Active scheme configuration and slab rules are server-protected from ordinary edits. Period create/date changes are serialized by a scheme row lock/version update; inclusive period overlap is rejected and adjacent periods are accepted.
- Added explicit period close cutoff, closed actor/time, source/claim/exception counts, distributor outcomes, reward totals grouped by product/UoM, and a deterministic close hash. Period close verifies scheme/company/period end/configuration, calculates every eligible distributor, and is all-or-nothing: a BLOCKED outcome aborts; NOT_ELIGIBLE is retained in the close summary without a positive claim.
- Period closing locks the period, gathers and locks source accounting rows in stable ID order, recalculates before allocation, then creates draft claims, immutable source rows, audit events, and closed-period metadata in one Odoo transaction. No manual commit is used. Repeated close of a closed period returns its existing claims.
- Added one draft claim per scheme/distributor/period with company-scoped database uniqueness constraints. Claim creation and protected fields require in-process service capabilities; direct ORM creation, entitlement edits, lifecycle forgery, copying, deletion, and source evidence modification are denied. Only draft submission and manager review-start transitions exist; neither action approves a claim.
- Claim evidence captures scheme, period, distributor, slab, UoMs, quantities, cutoff, sorted invoice/refund evidence, and hashes. Canonical JSON uses sorted keys, normalized numeric strings, and sorted source identities with SHA-256. ORM immutability plus integrity checks detect snapshot tampering; this does not protect against database administrators.
- Claim source line identity is unique per company across this MVP, intentionally preventing one accounting line from being consumed by two scheme claims. A later product policy may need an explicit source-sharing/revision rule if campaigns should stack.
- Revalidation returns CURRENT, STALE, or BLOCKED. A source change is classified as entitlement changed only when the reward product or reward quantity changes; otherwise it is `source_changed_entitlement_unchanged`. Revalidation preserves the original claim snapshot; stale or blocked claims cannot be submitted or sent to review.
- Updated native period/claim forms and lists show lifecycle, closing summaries, quantities, fingerprints, source lines, snapshots, and audit history. No approval, sales order, stock, or accounting settlement action is exposed.

### Actual P04 execution evidence

| Check | Result | Evidence |
|---|---|---|
| Python syntax / XML parsing | PASS | Python AST parsed 18 addon files; XML parser parsed 8 files after final changes. |
| Fresh Community install, registry, security, menus and views | PASS (unsupported interpreter) | Disposable PostgreSQL 18 database `gt_scheme_p04_test`; clean install loaded 90 Odoo modules and addon registry/views/security. First clean run completed tests but exposed defects that were fixed before the final update run. |
| P01-P03 regressions plus P04 ORM suite | PASS (unsupported interpreter) | Final Odoo result: `46 post-tests`, `0 failed`, `0 errors`; Odoo stats show 48 tests and 11,397 queries. `.test/odoo-p04-final.log`. Includes real invoice/refund ORM records, P03 calculator integration, 1,000-line preview test, company isolation, period close, draft claim evidence, source allocations, stale revalidation, and lifecycle guards. |
| Period close atomic rollback / duplicate prevention / snapshot protection | PASS (unsupported interpreter) | Tests assert blocked calculations leave no claims, repeated close is idempotent, source/claim uniqueness rejects duplicate allocation, snapshots remain unchanged after accounting source changes, and direct evidence mutation is denied. Included in final log. |
| Claim revalidation source-change categories | PASS (unsupported interpreter) | Tests cover unchanged source, backdated new invoice, late refund, reward changed, and source changed while reward entitlement remains unchanged. |
| Actual concurrent P04 close/allocation transactions | PASS (unsupported interpreter) | `.test/p04_concurrency_probe.py` ran with independent Odoo registry cursors/PostgreSQL transactions. Two requests closing the same period yielded one closed period, one claim, and one safe retry error. Two different schemes competing for the same qualifying invoice line yielded one closed period, one open/rolled-back period, and one allocated line/claim; the losing close returned a user-facing conflict error. Probe stdout/results are retained in `.test/p04-concurrency-results.txt`. |
| Broad multi-thousand-line close benchmark / query plans | NOT RUN | A real 1,000-line preview passed; no 1,000-line period-close scaling run or production query-plan sweep was performed. |
| Odoo-supported Python 3.12/3.13 run | NOT RUN | Only Python 3.14.6 was available; Odoo 20 source declares support for Python 3.12–3.13. |

Final successful command (PowerShell; disposable database and isolated local PostgreSQL cluster):

```powershell
& C:\PycharmProjects\odoo20\.venv\Scripts\python.exe C:\PycharmProjects\odoo20\odoo-20.0\odoo-bin --addons-path=C:\PycharmProjects\odoo20\odoo-20.0\odoo\addons,C:\PycharmProjects\odoo20\custom_addons --data-dir=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-data --db_host=127.0.0.1 --db_port=55498 --db_user=odoo_test --db_password= --database=gt_scheme_p04_test --update=gt_distributor_scheme_settlement --without-demo --test-enable --test-tags=/gt_distributor_scheme_settlement --stop-after-init --http-port=8095 --logfile=C:\PycharmProjects\odoo20\custom_addons\gt_distributor_scheme_settlement\.test\odoo-p04-final.log
```

### P04 acceptance matrix

- **AC-17 closed-period calculation: PASS.** Real tests cover authorization, explicit cutoff, end-date requirement, active scheme, all-distributor calculation, blocked rollback, and period snapshot. An independent-transaction same-period close race also produced one complete close and one safe retry outcome.
- **AC-18 duplicate prevention: PASS (tested concurrency scenarios).** Database uniqueness, idempotent close, two concurrent closes, and two competing scheme allocations against one source line were tested with separate cursors.
- **AC-19 entitlement accuracy: PASS.** Tests compare invoice/refund/UoM/slab results with generated draft claim values and saved source contributions.
- **AC-20 immutable snapshot: PASS (application ORM guarantee).** Snapshot/hash/source protections and tamper checks pass. Privileged database-level tampering remains outside the guarantee.
- **AC-21 stale change detection: PASS (tested source-change cases).** Current/stale/blocked paths and late/backdated changes are tested; a broad correction/reversal matrix is not exhaustive.

### P04 limitations and P05-P08 work

- Periods retain the P01 default `open` state for compatibility. Explicit Draft-to-Open manager action is available; closing requires an active scheme and an ended period. The cutoff is recorded, but Odoo cannot reconstruct prior values for a source changed after cutoff; closure captures a contemporaneous transaction snapshot and the cutoff is not a historical database reconstruction.
- Independent-transaction tests cover same-period close and cross-scheme source allocation. A source posting/update racing during the close snapshot was not separately tested; P04 locks source rows and claim revalidation catches post-snapshot changes before submission/review.
- P05: maker-checker claim approval, self-approval prevention, approval-time mandatory revalidation, approved entitlement freeze, controlled revisions/rejections, and approval audit.
- P06: zero-priced free-goods sales orders, actual delivery reconciliation, and late return adjustment exceptions.
- P07: reporting and premium dashboard.
- P08: packaging, documentation polish, supported-runtime verification, and publication readiness review.
- This work does not make the application ready to publish.
