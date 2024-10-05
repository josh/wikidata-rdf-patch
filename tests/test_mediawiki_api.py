import os

import pytest

import wikidata_rdf_patch.mediawiki_api as mediawiki_api

WIKIDATA_USERNAME = os.environ.get("WIKIDATA_USERNAME", "")
WIKIDATA_PASSWORD = os.environ.get("WIKIDATA_PASSWORD", "")


@pytest.mark.skipif(WIKIDATA_USERNAME == "", reason="Missing WIKIDATA_USERNAME")
@pytest.mark.skipif(WIKIDATA_PASSWORD == "", reason="Missing WIKIDATA_PASSWORD")
def test_login() -> None:
    session = mediawiki_api.login(
        username=WIKIDATA_USERNAME,
        password=WIKIDATA_PASSWORD,
        user_agent=mediawiki_api.DEFAULT_USER_AGENT,
    )
    assert session.username == WIKIDATA_USERNAME
    assert len(session.login_token) == 42
    assert len(session.csrf_token) == 42
    mediawiki_api.logout(session)
