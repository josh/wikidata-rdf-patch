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


def test_wbgetentities_property() -> None:
    entities = mediawiki_api.wbgetentities(
        ids=["P31"],
        user_agent=mediawiki_api.DEFAULT_USER_AGENT,
    )
    assert "P31" in entities
    assert entities["P31"]["type"] == "property"
    assert entities["P31"]["title"] == "Property:P31"
    assert entities["P31"]["datatype"] == "wikibase-item"


def test_wbgetentities_item() -> None:
    entities = mediawiki_api.wbgetentities(
        ids=["Q42"],
        user_agent=mediawiki_api.DEFAULT_USER_AGENT,
    )
    assert "Q42" in entities
    assert entities["Q42"]["type"] == "item"
    assert entities["Q42"]["title"] == "Q42"
    assert entities["Q42"]["claims"]["P31"][0]["mainsnak"]["snaktype"] == "value"
    assert (
        entities["Q42"]["claims"]["P31"][0]["mainsnak"]["datatype"] == "wikibase-item"
    )
    assert (
        entities["Q42"]["claims"]["P31"][0]["mainsnak"]["datavalue"]["type"]
        == "wikibase-entityid"
    )
    assert (
        entities["Q42"]["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"]["id"]
        == "Q5"
    )
