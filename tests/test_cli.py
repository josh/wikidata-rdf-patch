import json
import logging

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


def test_dry_run_previews_every_item_and_claim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    triples = """
        wd:Q42 wdt:P370 "Dry run preview for Q42".
        wd:Q115569934 wdt:P370 "Dry run preview for sandbox";
            wdt:P2536 "dry-run-preview".
    """

    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        root_logger.setLevel(logging.WARNING)
        result = CliRunner().invoke(
            main, ["--dry-run"], input=triples, catch_exceptions=False
        )
    finally:
        root_logger.setLevel(original_level)

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    messages = [record.getMessage() for record in caplog.records]
    assert "Edit Q42" in messages
    assert "Edit Q115569934" in messages
    assert sum(message.startswith(" ⮑ P370 / ") for message in messages) == 2
    assert sum(message.startswith(" ⮑ P2536 / ") for message in messages) == 1
    assert "Finished with 0 statements published, 0 errored, 3 skipped" in messages


def test_json_dry_run_writes_edit_and_result_records(
    caplog: pytest.LogCaptureFixture,
) -> None:
    triples = """
        wd:Q42 wdt:P370 "Dry run preview for Q42".
        wd:Q115569934 wdt:P370 "Dry run preview for sandbox";
            wdt:P2536 "dry-run-preview".
    """

    result = CliRunner().invoke(
        main,
        ["--dry-run", "--output-format", "json"],
        input=triples,
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    records = [json.loads(line) for line in result.stdout.splitlines()]
    edits = {record["qid"]: record for record in records[:-1]}
    assert edits.keys() == {"Q42", "Q115569934"}
    assert all(record["type"] == "edit" for record in edits.values())
    assert all(record["status"] == "skipped" for record in edits.values())
    assert [s["property"] for s in edits["Q42"]["statements"]] == ["P370"]
    assert edits["Q42"]["statements"][0]["guid"].startswith("Q42$")
    assert sorted(s["property"] for s in edits["Q115569934"]["statements"]) == [
        "P2536",
        "P370",
    ]
    assert records[-1] == {
        "type": "result",
        "status": "done",
        "published": 0,
        "errored": 0,
        "skipped": 3,
    }
    messages = [record.getMessage() for record in caplog.records]
    assert not any(message.startswith("Edit ") for message in messages)
    assert not any(message.startswith("Finished with ") for message in messages)


def test_json_reports_error_result_and_fails() -> None:
    result = CliRunner().invoke(
        main,
        ["--dry-run", "--output-format", "json"],
        input="wd:Q42 wdt:P370 .",
    )

    assert result.exit_code != 0
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 1
    assert records[0]["type"] == "result"
    assert records[0]["status"] == "error"
    assert records[0]["reason"]


def _requests(*requests: tuple[str, str]) -> str:
    return "".join(
        json.dumps({"id": request_id, "turtle": turtle}) + "\n"
        for request_id, turtle in requests
    )


def test_stream_json_dry_run_answers_each_request_in_order() -> None:
    result = CliRunner().invoke(
        main,
        ["--stream", "--dry-run", "--output-format", "json"],
        input=_requests(
            ("first", 'wd:Q42 wdt:P370 "Stream preview for Q42".'),
            (
                "second",
                'wd:Q115569934 wdt:P370 "Stream preview"; wdt:P2536 "stream".',
            ),
        ),
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(record["type"], record["id"]) for record in records] == [
        ("edit", "first"),
        ("result", "first"),
        ("edit", "second"),
        ("result", "second"),
    ]
    assert records[0]["qid"] == "Q42"
    assert records[0]["status"] == "skipped"
    assert records[1] == {
        "type": "result",
        "id": "first",
        "status": "done",
        "published": 0,
        "errored": 0,
        "skipped": 1,
    }
    assert records[2]["qid"] == "Q115569934"
    assert records[3]["status"] == "done"
    assert records[3]["skipped"] == 2


def test_stream_reports_a_failed_request_and_continues() -> None:
    missing = """
        wds:Q42-00000000-0000-0000-0000-000000000000
            wikibase:rank wikibase:DeprecatedRank.
    """
    result = CliRunner().invoke(
        main,
        ["--stream", "--dry-run", "--output-format", "json"],
        input=_requests(
            ("missing", missing),
            ("valid", 'wd:Q42 wdt:P370 "Stream preview for Q42".'),
        ),
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    results = [
        record
        for record in map(json.loads, result.stdout.splitlines())
        if record["type"] == "result"
    ]
    assert [(record["id"], record["status"]) for record in results] == [
        ("missing", "error"),
        ("valid", "done"),
    ]
    assert results[0]["reason"]
    assert results[1]["skipped"] == 1


def test_stream_rejects_a_malformed_request() -> None:
    result = CliRunner().invoke(
        main,
        ["--stream", "--dry-run", "--output-format", "json"],
        input="wd:Q42 wdt:P31 wd:Q5.\n",
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "line 1: invalid JSON" in result.stderr


def test_stream_text_dry_run_logs_edits_and_writes_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        root_logger.setLevel(logging.WARNING)
        result = CliRunner().invoke(
            main,
            ["--stream", "--dry-run"],
            input=_requests(("first", 'wd:Q42 wdt:P370 "Stream preview for Q42".')),
            catch_exceptions=False,
        )
    finally:
        root_logger.setLevel(original_level)

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    messages = [record.getMessage() for record in caplog.records]
    assert "Edit Q42" in messages
    assert "Finished with 0 statements published, 0 errored, 1 skipped" in messages
