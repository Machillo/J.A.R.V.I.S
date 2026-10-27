"""The backend accepts exactly the appearance options the apps can render.

`jarvis-personal/native/design-tokens/appearance.json` is the one catalog: the generator turns it
into the Swift and Kotlin catalogs and tokens, and this test holds the backend's closed values and
defaults to it, so a value the apps cannot draw is never stored and none the apps offer is refused.
"""
import json
import typing
from pathlib import Path

from backend.user_product import appearance

CATALOG = json.loads((Path(__file__).resolve().parents[2] / "native" / "design-tokens" / "appearance.json").read_text(encoding="utf-8"))


def test_every_field_accepts_exactly_the_catalog_values():
    fields = appearance.AppearancePreferences.model_fields
    assert set(fields) == set(CATALOG["options"]), "same option keys"
    for key, option in CATALOG["options"].items():
        assert set(typing.get_args(fields[key].annotation)) == set(option["values"]), key


def test_the_backend_defaults_are_the_catalog_defaults():
    assert appearance.DEFAULTS.model_dump() == {key: option["default"] for key, option in CATALOG["options"].items()}
