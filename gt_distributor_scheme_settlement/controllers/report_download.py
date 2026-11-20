from odoo import http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class DistributorSchemeReportDownload(http.Controller):
    @http.route(
        "/gt_scheme_settlement/report/<int:wizard_id>/<string:file_type>",
        type="http", auth="user", methods=["GET"], readonly=True,
    )
    def download(self, wizard_id, file_type, **_kwargs):
        if file_type not in ("csv", "xlsx"):
            raise UserError(_("Unsupported report format."))
        wizard = request.env["gt.distributor.scheme.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            raise AccessError(_("The requested report is unavailable."))
        wizard.check_access("read")
        if not wizard.generated_at:
            raise UserError(_("Generate the report before exporting it."))
        data = wizard._render_csv() if file_type == "csv" else wizard._render_xlsx()
        if len(data) > 25 * 1024 * 1024:
            raise UserError(_("The report exceeds the 25 MB download limit. Narrow the filters and retry."))
        filename = f"distributor-scheme-{wizard.report_type}-{wizard.id}.{file_type}"
        mimetype = "text/csv; charset=utf-8" if file_type == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return request.make_response(data, headers=[
            ("Content-Type", mimetype),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "private, no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])
