"""POST /query — semantic search. Integrated-inference (text) or pre-embedded
(vector). ``top_k`` capped at 50; ``filter`` keys must be schema fields.
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from _lib import handler, pinecone_client, validate


def _serialize_hits(response) -> list:
    """Convert Pinecone's response object into a JSON-safe list. Handles
    both the integrated-inference SearchRecordsResponse shape (hits at
    response.result.hits) and the vector-query QueryResponse shape (matches
    at response.matches).
    """
    out = []
    # Integrated-inference shape
    hits = None
    try:
        hits = response.result.hits
    except AttributeError:
        pass
    if hits is not None:
        for hit in hits:
            score = getattr(hit, "_score", None)
            fields = getattr(hit, "fields", None) or {}
            if hasattr(fields, "to_dict"):
                fields = fields.to_dict()
            out.append({
                "_id": getattr(hit, "_id", None),
                "_score": score,
                "fields": dict(fields) if not isinstance(fields, dict) else fields,
            })
        return out

    # Vector-query shape
    matches = getattr(response, "matches", None) or []
    for m in matches:
        out.append({
            "_id": getattr(m, "id", None),
            "_score": getattr(m, "score", None),
            "fields": dict(getattr(m, "metadata", {}) or {}),
        })
    return out


def query_op(body: dict) -> dict:
    req = validate.QueryRequest(**body)
    validate.check_namespace(req.namespace)

    if not req.text and not req.vector:
        raise validate.ValidationError(
            "query requires either `text` or `vector`"
        )
    if req.text and req.vector:
        raise validate.ValidationError(
            "query takes one of `text` or `vector`, not both"
        )

    idx = pinecone_client.get_index()

    if req.text:
        # Integrated-inference path
        q = {"inputs": {"text": req.text}, "top_k": req.top_k}
        if req.filter:
            q["filter"] = req.filter
        response = idx.search(namespace=req.namespace, query=q)
    else:
        # Pre-embedded path (consumers doing their own embeddings)
        response = idx.query(
            namespace=req.namespace,
            vector=req.vector,
            top_k=req.top_k,
            filter=req.filter,
            include_metadata=True,
        )

    return {"hits": _serialize_hits(response)}


handler = handler.make_handler(query_op, endpoint="query")
