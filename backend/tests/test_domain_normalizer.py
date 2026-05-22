"""Tests for DomainNormalizer."""

import pytest

from parsli.gmail.domain_normalizer import DomainNormalizer

n = DomainNormalizer()


def test_lowercase():
    assert n.normalize("PayPal.Com") == "paypal.com"


def test_strips_at_prefix():
    assert n.normalize("@example.com") == "example.com"


def test_strips_https_url():
    assert n.normalize("https://www.example.com/path?q=1") == "www.example.com"


def test_strips_http_url():
    assert n.normalize("http://shop.co.il/orders") == "shop.co.il"


def test_strips_port():
    assert n.normalize("example.com:443") == "example.com"


def test_strips_whitespace():
    assert n.normalize("  paypal.com  ") == "paypal.com"


def test_subdomain_preserved():
    assert n.normalize("mail.hfd.co.il") == "mail.hfd.co.il"


def test_invalid_no_dot_raises():
    with pytest.raises(ValueError):
        n.normalize("nodotdomain")


def test_invalid_empty_raises():
    with pytest.raises(ValueError):
        n.normalize("   ")


def test_invalid_url_no_host_raises():
    with pytest.raises(ValueError):
        n.normalize("https://")
