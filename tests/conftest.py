from collections.abc import Generator

import pytest

from wikidata_rdf_patch import mediawiki_api


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, None, None]:
    try:
        yield
    except mediawiki_api.Error as error:
        if error.code != "maxlag":
            raise
        pytest.skip(f"Wikidata replication lag: {error.info}")
