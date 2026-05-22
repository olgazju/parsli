"""Tests for SenderTrustScorer."""

import pytest

from parsli.gmail.sender_trust import SenderTrustLevel, SenderTrustScorer

scorer = SenderTrustScorer()


def test_known_shipping_domain_is_high():
    result = scorer.score("amazon.com")
    assert result.trust_level == SenderTrustLevel.HIGH
    assert result.trust_score == 4
    assert "shipping" in result.reasons[0]


def test_known_ecommerce_domain_is_high():
    result = scorer.score("asos.com")
    assert result.trust_level == SenderTrustLevel.HIGH
    assert result.trust_score == 3


def test_ecommerce_subdomain_matches():
    # m.nextdirect.com is a subdomain of nextdirect.com (ecommerce)
    result = scorer.score("m.nextdirect.com")
    assert result.trust_level == SenderTrustLevel.HIGH
    assert result.trust_score == 3


def test_shipping_subdomain_matches():
    # mail.hfd.co.il is directly in KNOWN_SHIPPING_DOMAINS
    result = scorer.score("mail.hfd.co.il")
    assert result.trust_level == SenderTrustLevel.HIGH
    assert result.trust_score == 4


def test_free_email_provider_is_low():
    result = scorer.score("gmail.com")
    assert result.trust_level == SenderTrustLevel.LOW
    assert result.trust_score == -2
    assert "free email" in result.reasons[0]


def test_walla_is_low():
    result = scorer.score("walla.co.il")
    assert result.trust_level == SenderTrustLevel.LOW


def test_generic_corporate_is_medium():
    result = scorer.score("unknownshop.co.il")
    assert result.trust_level == SenderTrustLevel.MEDIUM
    assert result.trust_score == 1
    assert "generic" in result.reasons[0]


def test_none_domain_is_medium():
    result = scorer.score(None)
    assert result.trust_level == SenderTrustLevel.MEDIUM
    assert result.sender_domain is None


def test_user_blocklisted_is_blocked():
    custom_scorer = SenderTrustScorer(user_blocklist=frozenset({"spammer.com"}))
    result = custom_scorer.score("spammer.com")
    assert result.trust_level == SenderTrustLevel.BLOCKED
    assert result.trust_score == -10


def test_blocklist_does_not_affect_other_domains():
    custom_scorer = SenderTrustScorer(user_blocklist=frozenset({"spammer.com"}))
    result = custom_scorer.score("amazon.com")
    assert result.trust_level == SenderTrustLevel.HIGH


def test_blocklisted_subdomain_is_blocked():
    custom_scorer = SenderTrustScorer(user_blocklist=frozenset({"badshop.com"}))
    result = custom_scorer.score("mail.badshop.com")
    assert result.trust_level == SenderTrustLevel.BLOCKED


def test_domain_normalised_to_lowercase():
    result = scorer.score("Amazon.COM")
    assert result.trust_level == SenderTrustLevel.HIGH
    assert result.sender_domain == "amazon.com"


def test_reasons_always_non_empty():
    for domain in [None, "amazon.com", "gmail.com", "random.co.il"]:
        result = scorer.score(domain)
        assert len(result.reasons) >= 1
