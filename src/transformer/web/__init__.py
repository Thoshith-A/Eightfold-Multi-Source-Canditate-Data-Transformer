"""Optional thin HTTP layer (Stage 9).

A FastAPI app that wraps the SAME :mod:`transformer.pipeline` — it holds **no
transform logic of its own**: it writes uploads to a temp dir, calls
``pipeline.run`` (with the same optional enricher seam), and returns the result.
Requires the ``[web]`` extra (``pip install -e ".[web]"``); the core never
imports this package.
"""
