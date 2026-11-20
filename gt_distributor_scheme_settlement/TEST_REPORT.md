# P01 Verification Report

Date: 2026-11-20

## Environment evidence

- Odoo source: `C:\PycharmProjects\odoo20\odoo-20.0`, release source reports 20.0.0 final.
- Community addons: `C:\PycharmProjects\odoo20\odoo-20.0\addons`.
- Project virtual environment: `C:\PycharmProjects\odoo20\.venv`, Python 3.14.6. It has `psycopg2` and `lxml`; Odoo is loaded from source.
- Odoo 20 source declares Python 3.12 minimum, Python 3.14 maximum exclusive, and PostgreSQL 16 minimum. Therefore the discovered Python 3.14.6 runtime is outside the supported range.
- PostgreSQL 18 Windows service is running. No credentials or database contents were inspected. No existing database was used.
- An isolated PostgreSQL 18 cluster initialized successfully under `.test/pgdata`. `pg_ctl start` failed with Windows sandbox restricted-token errors, but launching `postgres.exe` directly in the foreground worked on port 55498. Tests used only the disposable database and `.test` filestore; no existing service database was used.
- Odoo source inspection confirmed `sale.order` (`sale/models/sale_order.py`); `account.move` and `account.move.line` (`account/models`); `stock.picking` (`stock/models/stock_picking.py`); `product.product` (`product/models/product_product.py`); and `res.partner` (`odoo/addons/base/models/res_partner.py`). The inspected fields include move type/state/invoice date/reversed-entry link, move-line product/UoM/quantity/document links, picking state/company/return link, product UoM, and partner company identity. Odoo 20 core uses `<list>` views, `res.groups.privilege`, `res.users.group_ids`, `ir.access` permission/domain records, `models.Constraint`, and `fields.Json`.
- License evidence: the Community checkout's dependency manifests use LGPL-3. Odoo's published license documentation lists OPL-1 as a supported module manifest license and permits compatible licenses for modules using Odoo as a library. This addon contains no copied Odoo source. This is a technical compatibility check, not legal advice.

## Results

| Check | Result | Evidence |
|---|---|---|
| Odoo 20 Community source discovered | PASS | `odoo/release.py` reports 20.0; Community addons tree is present. |
| Runtime / PostgreSQL config verified | PARTIAL | Python 3.14.6 and PostgreSQL 18 service found; supported Python 3.12–3.13 runtime and a dedicated disposable DB configuration were not available. |
| Required source model/API inspection | PASS | All named source models and baseline accounting, product, partner, and stock fields listed above were inspected. Future workflow APIs still need focused verification when implemented. |
| Manifest metadata and dependency declarations | PASS | Odoo 20 manifest structure; dependencies are Community addons `sale`, `account`, `stock`, `mail`; version `20.0.1.0.0`. |
| OPL-1 metadata and dependency licensing | PASS | OPL-1 manifest value; dependency manifests declare LGPL-3; no source copied. Publisher/distribution legal review remains outside this technical check. |
| Python syntax compilation | PASS | All 13 addon Python files compiled with Python 3.14.6. Odoo runtime compatibility is separate and NOT RUN. |
| XML well-formedness and manifest literal parsing | PASS | All 8 XML files parsed and manifest loaded as a Python literal. This does not validate Odoo's XML schema/registry. |
| Registry setup, fresh install, ACL/rule evaluation, and module tests | PASS (unsupported interpreter) | Fresh module installation loaded the registry and addon XML/security. All 9 addon post-install tests passed on Python 3.14.6/PostgreSQL 18 using a disposable database. Odoo 20 declares Python 3.12–3.13 support; repeat on a supported interpreter before release. |

## Acceptance checks

- **AC-01 fresh install and registry:** PASS (Python 3.14.6 unsupported) — module installed into a fresh disposable Odoo 20 database; registry loaded.
- **AC-02 required fields and validations:** PASS (Python 3.14.6 unsupported) — required fields, invalid dates and slab quantities, and unimplemented-state guards covered by addon tests.
- **AC-03 company isolation and authorization:** PASS (Python 3.14.6 unsupported) — ACLs, Odoo 20 company-scoped `ir.access` domains, and cross-company checks covered by addon tests.
- **AC-04 immutable audit/evidence:** PASS (Python 3.14.6 unsupported) — audit modification restrictions covered by tests; source and adjustment evidence are append-only at ORM level.
- **AC-05 native views and menu references:** PASS (Python 3.14.6 unsupported) — Odoo view schemas and menu/action references loaded successfully; test verifies key external IDs.
- **AC-06 no unimplemented workflow claims:** PASS — no calculate, approve, close, fulfill, or settle actions/services are exposed; claim lifecycle and metadata writes are server-blocked.

## Security limitations and deferred work

- Odoo superuser mode intentionally bypasses ACLs and record rules. Future privileged services need their own explicit authorization and invariant checks.
- Full multi-company access combinations, import/RPC vectors, and concurrent attempts still require targeted runtime tests. Tests used the discovered unsupported Python 3.14.6 runtime. A broad Odoo core test run also hit an unrelated core attachment memory assertion, so the successful run was filtered to this addon.
- Purchase calculation, refund linkage, UoM conversion, period closing, claim generation, immutable document snapshot capture, stale evidence detection, manager approval, zero-priced sales orders, delivery reconciliation, and late-return exceptions are deferred to P02–P08 as specified in `README.md`.
- This P01 module is an install foundation, not a functional settlement workflow and not ready to publish.
