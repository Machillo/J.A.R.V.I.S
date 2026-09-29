"""DINCR Labs: a local, synthetic, disposable experimentation environment.

Labs can never reach production: see docs/labs.md. The backend never imports
this package (guarded by labs/tests/test_isolation.py). Importing it does
nothing by itself; ``labs.runtime.activate`` (called by ``python -m labs``)
checks the environment, blocks the network and only then loads the backend.
"""
