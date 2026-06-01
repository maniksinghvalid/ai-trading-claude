"""POST /fetch — fetch records by ID. Max 100 IDs per call. IDs must
match the RECORD_ID_PATTERN contract.
"""

from _lib import pinecone_client, validate


def fetch_op(body: dict) -> dict:
    req = validate.FetchRequest(**body)
    validate.check_namespace(req.namespace)

    idx = pinecone_client.get_index()
    resp = idx.fetch(ids=req.ids, namespace=req.namespace)

    vectors = getattr(resp, "vectors", None) or {}
    out = {}
    for vid, vec in vectors.items():
        metadata = getattr(vec, "metadata", None)
        if metadata is None and hasattr(vec, "get"):
            metadata = vec.get("metadata", {})
        out[vid] = dict(metadata) if metadata else {}

    return {"records": out}


