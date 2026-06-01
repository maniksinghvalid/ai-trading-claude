"""POST /delete — delete records by IDs or filter. ``confirm: "yes"``
REQUIRED (no accidental bulk wipes).
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from _lib import handler, pinecone_client, validate


def delete_op(body: dict) -> dict:
    req = validate.DeleteRequest(**body)
    validate.check_namespace(req.namespace)

    if not req.ids and not req.filter:
        raise validate.ValidationError(
            "delete requires either `ids` or `filter` (with confirm)"
        )

    idx = pinecone_client.get_index()

    if req.ids:
        idx.delete(ids=req.ids, namespace=req.namespace)
        return {"deleted_count": len(req.ids), "by": "ids"}

    # Filter-based delete. Pinecone's Python SDK accepts a filter dict.
    idx.delete(filter=req.filter, namespace=req.namespace)
    return {"deleted_count": None, "by": "filter"}


handler = handler.make_handler(delete_op, endpoint="delete")
