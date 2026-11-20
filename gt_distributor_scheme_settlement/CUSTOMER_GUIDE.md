# Distributor Scheme Settlement — Customer Guide

Publisher: **Golok Technology**  
Support: [patelyash.gokul@gmail.com](mailto:patelyash.gokul@gmail.com)

## Requirements and access

Use Odoo 20 Community with the `sale_stock`, `account`, and `mail` Community modules installed. Assign Distributor Scheme Operator, Scheme Manager, or Scheme Auditor in addition to the standard Accounting and Inventory permissions needed for the employee's work. A manager also receives Odoo's Sales User role so the standard free-goods sales order can be created and confirmed. Keep warehouse validation permissions limited to the people who work with stock.

All scheme records, claims, accounting evidence, fulfillment orders, stock movements, and reports are scoped by company. Select the correct company in the Odoo company switcher before working. A report cannot read companies outside the user's allowed company list.

## Supported workflow

1. In **Distributor Schemes → Schemes**, create a scheme, select the qualifying product, reward product, qualifying unit, eligible distributor companies, and validity dates.
2. Add non-overlapping purchase slabs under **Configuration → Purchase Slabs**. Activate the scheme after checking its products, dates, distributors, units, and slab boundaries.
3. Use **Preview Purchase Eligibility** for a non-binding calculation. The purchase source is posted brand-side customer invoices and reliably linked posted customer credit notes. Quotations, vendor bills, deliveries without invoices, and unposted accounting documents do not qualify.
4. Create and open scheme periods. Close an ended period after reviewing the calculation exceptions. Closing creates draft claims with saved calculation and source evidence.
5. An operator submits a claim. A different authorized manager starts review, revalidates sources, and approves or rejects it. The submitter or revision preparer cannot approve their own request.
6. A manager initiates free-goods fulfillment from an approved claim and explicitly selects a warehouse when needed. The module creates one zero-priced sales order using the frozen approved product, unit, and quantity.
7. Warehouse staff perform normal Odoo reservation, picking, delivery, and backorder operations. Only completed customer-facing stock moves count as delivered; internal transfers and reservations do not. Linked completed returns reduce net fulfillment.
8. Reconcile and finalize settlement only when actual net delivery equals the approved quantity and no material source or adjustment hold remains.
9. Use **Distributor Schemes → Dashboard** for operational counts. **Reporting → Settlement Reports** provides scheme performance, distributor settlement, outstanding free goods, and adjustment exception reports. Filter dates mean **claim creation dates**. The active-scheme KPI is based on current scheme status and is not restricted by claim creation dates.

## Exceptions and limits

Late qualifying purchase refunds and relevant accounting changes are recorded as adjustment exceptions. Original approval and settlement evidence remains visible. The module does not automatically recover goods or money, post accounting entries, create invoices or credit notes, or issue additional entitlement. Review an exception and follow your organization's documented finance and warehouse process.

A zero selling price does not determine the tax or statutory treatment in every jurisdiction. Unsupported non-zero payable tax totals block fulfillment for review. Standard Odoo stock valuation may still apply according to product and accounting configuration.

Exports include at most 5,000 report rows and 25 MB per download. CSV text that could be interpreted as a spreadsheet formula is prefixed with an apostrophe. XLSX exports write business text as literal string cells. Export filters and permissions match the report wizard; changing a filter clears generated rows until the report is run again.

## Common messages

- **Source changed / stale:** review the claim's invoice and credit-note evidence, then use the controlled revision or adjustment workflow.
- **Fulfillment on hold:** inspect open adjustment exceptions and source validation before attempting another delivery.
- **Outstanding quantity:** the claim is not settled until validated customer delivery movements, less linked returns, equal the frozen approved entitlement.
- **Report too large:** narrow the company, scheme, distributor, or claim-creation date filters and generate the report again.
- **Company not allowed:** select an authorized company or ask an administrator to review the user's allowed-company and group assignments.

## Support

For installation and workflow questions, contact Golok Technology at [patelyash.gokul@gmail.com](mailto:patelyash.gokul@gmail.com). Include the Odoo version, addon version, company context, and affected claim reference. Do not send passwords, database dumps, or unrelated customer financial records.
