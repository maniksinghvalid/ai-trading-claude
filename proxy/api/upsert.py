"""POST /upsert — write records into Pinecone with integrated-inference
(default) or caller-supplied vectors (fallback).

The producer plan's record schema uses ``text`` only; ``values`` is
omitted. So the default path is ``Index.upsert_records()`` (server-side
embedding by ``llama-text-embed-v2``). The ``values?`` accept-shape keeps
the proxy useful for future callers that pre-embed.
"""

from _lib import pinecone_client, validate


def upsert_op(body: dict) -> dict:
    req = validate.UpsertRequest(**body)
    validate.check_namespace(req.namespace)

    # Partition records by whether they have caller-supplied vectors
    integrated = []
    pre_embedded = []
    for rec in req.records:
        # Normalize id field name (accept either)
        record = dict(rec)
        if "_id" in record and "id" not in record:
            record["id"] = record.pop("_id")
        if record.get("values"):
            pre_embedded.append(record)
        else:
            integrated.append(record)

    idx = pinecone_client.get_index()
    results = {"upserted_integrated": 0, "upserted_pre_embedded": 0}

    if integrated:
        # Build on-wire Pinecone payload via RecordMetadata.to_pinecone_record()
        # so the proxy uses the same lift/serialize path as the local writer
        # (lifts id→_id, comma-joins catalysts). Single source of truth lives
        # in scripts/trade_schemas.py.
        payload = []
        for rec in integrated:
            # Already validated by UpsertRequest above; round-trip through
            # the model to apply to_pinecone_record() semantics.
            model = validate.RecordMetadata(**rec)
            payload.append(model.to_pinecone_record())
        idx.upsert_records(req.namespace, payload)
        results["upserted_integrated"] = len(integrated)

    if pre_embedded:
        # Index.upsert expects [{"id": ..., "values": [...], "metadata": {...}}]
        # Strip the `text` field if present (Pinecone reserves no special
        # handling for it on the upsert path; it'd just go into metadata).
        payload = []
        for rec in pre_embedded:
            metadata = {
                k: v for k, v in rec.items()
                if k not in ("id", "values", "_id")
            }
            payload.append({
                "id": rec.get("id") or rec.get("_id"),
                "values": rec["values"],
                "metadata": metadata,
            })
        idx.upsert(vectors=payload, namespace=req.namespace)
        results["upserted_pre_embedded"] = len(pre_embedded)

    return results


