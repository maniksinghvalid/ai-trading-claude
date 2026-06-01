"""POST /list — list IDs by prefix. Prefix is REQUIRED (lexical-scope
guard against full-namespace enumeration). Limit capped at 1000.
"""

from _lib import pinecone_client, validate


def list_op(body: dict) -> dict:
    req = validate.ListRequest(**body)
    validate.check_namespace(req.namespace)

    idx = pinecone_client.get_index()

    kwargs = {
        "namespace": req.namespace,
        "prefix": req.prefix,
        "limit": req.limit,
    }
    if req.pagination_token:
        kwargs["pagination_token"] = req.pagination_token

    resp = idx.list_paginated(**kwargs)

    ids = []
    vectors = getattr(resp, "vectors", None) or []
    for v in vectors:
        vid = v.get("id") if hasattr(v, "get") else getattr(v, "id", None)
        if vid:
            ids.append(vid)

    pagination = getattr(resp, "pagination", None)
    next_token = None
    if pagination:
        if hasattr(pagination, "get"):
            next_token = pagination.get("next")
        else:
            next_token = getattr(pagination, "next", None)

    return {"ids": ids, "next_pagination_token": next_token}


