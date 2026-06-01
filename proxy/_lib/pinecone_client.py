"""Singleton Pinecone client for the proxy. Reuses one TCP connection across
warm-function invocations.

Vercel Python functions can be warm-reused; module-level state survives
between requests on the same container. Lazy initialization on first use
keeps cold-start latency on functions that never need Pinecone (none today
— all 5 endpoints do — but the pattern is portable).
"""

import os
from typing import Optional


_PC = None
_INDEX_CACHE: dict = {}


def get_client():
    """Return the singleton ``Pinecone`` client. Constructs on first call."""
    global _PC
    if _PC is None:
        from pinecone import Pinecone
        api_key = os.environ.get("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "PINECONE_API_KEY is not set in the proxy environment. "
                "Set it in the Vercel project settings."
            )
        _PC = Pinecone(api_key=api_key)
    return _PC


def get_index(name: Optional[str] = None):
    """Return an ``Index`` handle (cached per index name).

    Defaults to the ``PINECONE_INDEX`` env var (or ``trade-reports``).
    """
    if name is None:
        name = os.environ.get("PINECONE_INDEX", "trade-reports")
    if name not in _INDEX_CACHE:
        _INDEX_CACHE[name] = get_client().Index(name)
    return _INDEX_CACHE[name]
