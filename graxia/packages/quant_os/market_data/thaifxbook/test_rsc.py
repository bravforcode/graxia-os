"""RSC flight-payload decoding tests."""

from __future__ import annotations

import pytest

from market_data.thaifxbook.rsc import decode_flight_payload


def test_decode_returns_concatenated_text():
    html = (
        '<script>self.__next_f.push([1,"hello\\u0020world"])</script><script>self.__next_f.push([2,"second"])</script>'
    )
    out = decode_flight_payload(html)
    assert "hello world" in out
    assert "second" in out


def test_decode_handles_escaped_quotes():
    html = '<script>self.__next_f.push([1,"a\\"b\\"c"])</script>'
    assert decode_flight_payload(html) == 'a"b"c'


def test_decode_rejects_non_rsc_page():
    with pytest.raises(ValueError):
        decode_flight_payload("<html><body>plain</body></html>")


def test_decode_real_fixture():
    from pathlib import Path

    html = (Path(__file__).parent / "fixtures" / "outlook_20260806.html").read_text(encoding="utf-8")
    out = decode_flight_payload(html)
    assert "XAU/USD" in out
