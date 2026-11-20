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

Odoo reported `0 failed, 0 error(s) of 11 tests` in `.test/odoo-p02-rerun.log`. The database and filestore are under `.test`; the temporary PostgreSQL cluster was stopped after verification.

## Acceptance checks

- **AC-01 fresh install and registry:** PASS (Python 3.14.6 unsupported) — module installed into a fresh disposable Odoo 20 database; registry loaded.
- **AC-02 required fields and validations:** PASS (Python 3.14.6 unsupported) — required fields, invalid dates and slab quantities, and unimplemented-state guards covered by addon tests.
- **AC-03 company isolation and authorization:** PASS (Python 3.14.6 unsupported) — ACLs, Odoo 20 company-scoped `ir.access` domains, and cross-company checks covered by addon tests.
- **AC-04 immutable audit/evidence:** PASS (Python 3.14.6 unsupported) — audit modification restrictions covered by tests; source and adjustment evidence are append-only at ORM level.
- **AC-05 native views and menu references:** PASS (Python 3.14.6 unsupported) — Odoo view schemas and menu/action references loaded successfully; test verifies key external IDs.
- **AC-06 no unimplemented workflow claims:** PASS — no calculate, approve, close, fulfill, or settle actions/services are exposed; claim lifecycle and metadata writes are server-blocked.

## Security limitations and deferred work

- Odoo superuser mode intentionally bypasses access controls. Future privileged services need their own explicit authorization and invariant checks.
- Full multi-company access combinations, import/RPC vectors, and concurrent attempts still require targeted runtime tests. Tests used the discovered unsupported Python 3.14.6 runtime. A broad Odoo core test run also hit an unrelated core attachment memory assertion, so the successful run was filtered to this addon.
- Purchase calculation, refund linkage, UoM conversion, period closing, claim generation, immutable document snapshot capture, stale evidence detection, manager approval, zero-priced sales orders, delivery reconciliation, and late-return exceptions are deferred to P02–P08 as specified in `README.md`.
- This P01 module is an install foundation, not a functional settlement workflow and not ready to publish.
