"""`is_available()` must mean "this source can return clips".

Three adapters hardcoded `return True` while their endpoints could never
serve a result:

- coverr  — api.coverr.co answers 401 Unauthorized with no key, so the
            advertised keyless "free tier" does not exist
- nara    — catalog.archives.gov/api/v2/search answers 200 with
            content-type text/html (the SPA shell), so `.json()` always
            raises JSONDecodeError
- pond5_pd — pond5.com answers 403 behind a JavaScript bot challenge on
            both the API and the /free web fallback

Because `available_sources()` drives preflight and the corpus fan-out,
each one inflated the reported capability envelope and then contributed
zero clips. That is the silent-availability failure AGENT_GUIDE.md warns
about: the agent plans around sources that cannot deliver.

These tests are hermetic — they assert the availability contract, not the
remote endpoints.
"""

import pytest

from tools.video import stock_sources as ss


@pytest.mark.parametrize("name", ["nara", "pond5_pd"])
def test_known_broken_sources_report_unavailable(name):
    """A source whose endpoint cannot serve JSON must not claim availability."""
    source = ss.get_source(name)
    assert source.is_available() is False, (
        f"{name} reports available but its endpoint cannot return a clip"
    )


@pytest.mark.parametrize("name", ["nara", "pond5_pd"])
def test_known_broken_sources_explain_why(name):
    """Preflight shows install_instructions, so they must state the real reason."""
    text = ss.get_source(name).install_instructions.lower()
    assert "unavailable" in text, f"{name} does not say it is unavailable"


@pytest.mark.parametrize("name", ["nara", "pond5_pd"])
def test_known_broken_sources_excluded_from_available(name):
    """available_sources() feeds the corpus fan-out and preflight counts."""
    assert name not in {s.name for s in ss.available_sources()}


def test_coverr_requires_its_api_key(monkeypatch):
    """Coverr has no anonymous tier: 401 without an Authorization header."""
    monkeypatch.delenv("COVERR_API_KEY", raising=False)
    assert ss.get_source("coverr").is_available() is False


def test_coverr_available_once_key_is_set(monkeypatch):
    monkeypatch.setenv("COVERR_API_KEY", "test-key")
    assert ss.get_source("coverr").is_available() is True


def test_coverr_install_instructions_name_the_key(monkeypatch):
    text = ss.get_source("coverr").install_instructions
    assert "COVERR_API_KEY" in text
    assert "401" in text, "should say why the keyless path fails"


def test_keyed_sources_still_gate_on_their_key(monkeypatch):
    """Guard the honest adapters against regressing to hardcoded True."""
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert ss.get_source("pexels").is_available() is False
    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    assert ss.get_source("pexels").is_available() is True


def test_every_source_reports_a_boolean():
    """The protocol requires a real bool, not a truthy object."""
    for source in ss.all_sources():
        assert isinstance(source.is_available(), bool), (
            f"{source.name}.is_available() returned a non-bool"
        )
