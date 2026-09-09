"""familydash smoke: renders at every declared size with no network call."""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient


@pytest.mark.parametrize("size", ["xs", "sm", "md", "lg"])
def test_familydash_renders(client: FlaskClient, size: str) -> None:
    resp = client.get(f"/_test/render?plugin=familydash&size={size}")
    assert resp.status_code == 200