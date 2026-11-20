"""In-process capabilities used only by trusted addon services.

These object identities cannot be supplied through JSON RPC or CSV imports.
They are not cryptographic secrets and do not protect against trusted Python
code or a database administrator.
"""

PERIOD_SERVICE_TOKEN = object()
CLAIM_CREATE_TOKEN = object()
CLAIM_WRITE_TOKEN = object()
CLAIM_SOURCE_TOKEN = object()
AUDIT_CREATE_TOKEN = object()
REVISION_CREATE_TOKEN = object()
REVISION_WRITE_TOKEN = object()
SOURCE_GUARD_TOKEN = object()
