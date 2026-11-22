"""Cross-version TOML parsing compatibility helper (Python 3.10+).

Prefers standard library `tomllib` (Python 3.11+).
Falls back to `tomli` (PEP 680 reference implementation backport) on Python < 3.11.
"""
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        raise ImportError(
            "TOML parsing requires 'tomllib' (Python 3.11+) or 'tomli' (Python < 3.11). "
            "Install with: pip install tomli"
        )
