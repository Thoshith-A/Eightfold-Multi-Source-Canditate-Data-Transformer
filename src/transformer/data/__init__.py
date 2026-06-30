"""Checked-in data assets shipped inside the package.

Currently just ``skills_taxonomy.json`` (the alias -> canonical skill map).
Kept inside the package so it resolves via ``importlib.resources`` after a real
``pip install``, independent of the current working directory.
"""
