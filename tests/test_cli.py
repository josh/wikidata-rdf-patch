import click
import pytest
from click.testing import CliRunner

from wikidata_rdf_patch.cli import _blocklist_title, main


@pytest.mark.parametrize(
    ("value", "title"),
    [
        ("", ""),
        ("Wikidata:Sandbox", "Wikidata:Sandbox"),
        ("https status blocklist", "https status blocklist"),
        (
            "https://www.wikidata.org/wiki/Wikidata:Database_reports/Complex_constraint_violations",
            "Wikidata:Database_reports/Complex_constraint_violations",
        ),
        (
            "https://www.wikidata.org/wiki/Wikidata:Sandbox%20archive",
            "Wikidata:Sandbox archive",
        ),
    ],
)
def test_blocklist_title_accepts_supported_values(value: str, title: str) -> None:
    assert _blocklist_title(value) == title


@pytest.mark.parametrize(
    "value",
    [
        "https://www.wikidata.org/wiki/",
        "https://www.wikidata.org/wiki/Wikidata:Sandbox?oldid=1",
        "https://www.wikidata.org/wiki/Wikidata:Sandbox#section",
        "https://www.wikidata.org/w/index.php?title=Wikidata:Sandbox",
        "https://wikidata.org/wiki/Wikidata:Sandbox",
        "https://www.wikidata.org.example/wiki/Wikidata:Sandbox",
        "http://www.wikidata.org/wiki/Wikidata:Sandbox",
        "https:/www.wikidata.org/wiki/Wikidata:Sandbox",
        "https://[/wiki/X",
        "https://www.wikidata.org：443/wiki/X",
        "https://www.wikidata.org/wiki/Wikidata:Sandbox%ZZ",
        "https://www.wikidata.org/wiki/Wikidata:Sandbox%C3",
    ],
)
def test_blocklist_title_rejects_unsupported_urls(value: str) -> None:
    with pytest.raises(click.BadParameter):
        _blocklist_title(value)


def test_invalid_blocklist_url_fails_before_login() -> None:
    result = CliRunner().invoke(
        main,
        ["--blocklist-url", "http://www.wikidata.org/wiki/Wikidata:Sandbox"],
    )

    assert result.exit_code == 2
    assert "Invalid value for --blocklist-url" in result.output
