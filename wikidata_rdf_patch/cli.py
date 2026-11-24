import io
import json
import logging
import re
import time
import urllib.parse
from typing import Any, TextIO

import click
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from wikidata_rdf_patch import actions_logging, mediawiki_api, wikidata_typing

from .rdf_patch import PropertyDatatypes, process_graph

actions_logging.setup()
logger = logging.getLogger("wikidata-rdf-patch")


def _blocklist_title(value: str) -> str:
    if not value:
        return ""

    looks_like_url = (
        "://" in value
        or value.startswith("//")
        or value.lower().startswith(("http:", "https:"))
    )
    if not looks_like_url:
        return value

    error_message = (
        "must be a page title or a canonical "
        "https://www.wikidata.org/wiki/<title> URL without a query or fragment"
    )
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as error:
        raise click.BadParameter(
            error_message,
            param_hint="--blocklist-url",
        ) from error
    prefix = "/wiki/"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.wikidata.org"
        or not parsed.path.startswith(prefix)
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
    ):
        raise click.BadParameter(
            error_message,
            param_hint="--blocklist-url",
        )

    raw_title = parsed.path.removeprefix(prefix)
    if re.search(r"%(?![0-9A-Fa-f]{2})", raw_title):
        raise click.BadParameter(
            error_message,
            param_hint="--blocklist-url",
        )
    try:
        title = urllib.parse.unquote_to_bytes(raw_title).decode("utf-8")
    except UnicodeDecodeError as error:
        raise click.BadParameter(
            error_message,
            param_hint="--blocklist-url",
        ) from error
    if not title:
        raise click.BadParameter(
            "Wikidata blocklist URL must include a page title",
            param_hint="--blocklist-url",
        )
    return title


def _log_edit(
    qid: str, summary: str | None, claims: list[wikidata_typing.Statement]
) -> None:
    if summary:
        logger.info(f"Edit {qid}: {summary}")
    else:
        logger.info(f"Edit {qid}")
    for statement in claims:
        statement_id = statement["mainsnak"]["property"]
        statement_snak = statement.get("id", "(new claim)")
        logger.info(f" ⮑ {statement_id} / {statement_snak}")


def _edit_record(
    qid: str,
    summary: str | None,
    claims: list[wikidata_typing.Statement],
    status: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"type": "edit"}
    if request_id is not None:
        record["id"] = request_id
    record["qid"] = qid
    record["summary"] = summary
    record["status"] = status
    record["statements"] = [
        {"property": statement["mainsnak"]["property"], "guid": statement.get("id")}
        for statement in claims
    ]
    return record


def _result_record(
    status: str,
    published: int = 0,
    errored: int = 0,
    skipped: int = 0,
    reason: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"type": "result"}
    if request_id is not None:
        record["id"] = request_id
    record["status"] = status
    record["published"] = published
    record["errored"] = errored
    record["skipped"] = skipped
    if reason is not None:
        record["reason"] = reason
    return record


def _write(record: dict[str, Any]) -> None:
    click.echo(json.dumps(record))


def _stream_request(line: str, number: int) -> tuple[str, str]:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as error:
        raise click.ClickException(f"line {number}: invalid JSON") from error
    if (
        not isinstance(request, dict)
        or not isinstance(request.get("id"), str)
        or not isinstance(request.get("turtle"), str)
    ):
        raise click.ClickException(
            f"line {number}: expected an object with string id and turtle"
        )
    return request["id"], request["turtle"]


def _stream(
    input: TextIO,
    session: mediawiki_api.Session | None,
    json_output: bool,
    blocked_qids: set[str],
    user_agent: str,
    min_time_between_edits: int,
    seconds: float,
) -> None:
    property_datatypes: PropertyDatatypes = {}
    published = 0
    errored = 0
    skipped = 0
    last_edit: float = 0.0

    try:
        for number, line in enumerate(input, start=1):
            if not line.strip():
                continue
            request_id, turtle = _stream_request(line, number)
            result = _result_record("done", request_id=request_id)
            deadline = time.monotonic() + seconds
            current: tuple[str, str | None, list[wikidata_typing.Statement]] | None
            current = None

            try:
                edits = process_graph(
                    input=io.StringIO(turtle),
                    blocked_qids=blocked_qids,
                    user_agent=user_agent,
                    deadline=deadline,
                    property_datatypes=property_datatypes,
                )
                for qid, lastrevid, claims, summary in edits:
                    current = (qid, summary, claims)
                    if not json_output:
                        _log_edit(qid, summary, claims)

                    if session is None:
                        result["skipped"] += len(claims)
                        status = "skipped"
                    else:
                        wait_time = max(
                            0, min_time_between_edits - (time.time() - last_edit)
                        )
                        if wait_time > 0:
                            logger.debug("Waiting for %.1f seconds", wait_time)
                            time.sleep(wait_time)
                        mediawiki_api.wbeditentity(
                            session=session,
                            qid=qid,
                            baserevid=lastrevid,
                            edit_data={"claims": claims},
                            summary=summary,
                            deadline=deadline,
                        )
                        last_edit = time.time()
                        result["published"] += len(claims)
                        status = "published"

                    if json_output:
                        _write(_edit_record(qid, summary, claims, status, request_id))
                    current = None
            except mediawiki_api.RetriesExhaustedError as e:
                logger.warning("Stopping at %s: %s", request_id, e)
                result["status"] = "stopped"
                result["reason"] = str(e)
            except Exception as e:
                logger.exception("%s failed", request_id)
                result["status"] = "error"
                result["reason"] = str(e)
                if current is not None:
                    result["errored"] = len(current[2])
                    if json_output:
                        _write(_edit_record(*current, "errored", request_id))

            published += result["published"]
            errored += result["errored"]
            skipped += result["skipped"]
            if json_output:
                _write(result)
            if result["status"] == "stopped":
                break
    finally:
        if session is not None:
            mediawiki_api.logout(session)
        if not json_output:
            logger.info(
                "Finished with %i statements published, %i errored, %i skipped",
                published,
                errored,
                skipped,
            )


@click.command()
@click.option("-n", "--dry-run", is_flag=True, help="Do not make any changes")
@click.option(
    "--username",
    envvar="WIKIDATA_USERNAME",
    default="",
    help="Wikidata username",
)
@click.option(
    "--password",
    envvar="WIKIDATA_PASSWORD",
    default="",
    help="Wikidata password",
)
@click.option(
    "--input",
    type=click.File("r"),
    default="-",
    help="Input RDF file",
)
@click.option(
    "--blocklist-url",
    envvar="WIKIDATA_BLOCKLIST_URL",
    default="",
    help="Wikidata blocklist page URL",
)
@click.option(
    "--user-agent",
    envvar="WIKIDATA_USER_AGENT",
    default=mediawiki_api.DEFAULT_USER_AGENT,
    help="User-Agent header",
)
@click.option(
    "--min-time-between-edits",
    envvar="WIKIDATA_MIN_TIME_BETWEEN_EDITS",
    type=int,
    default=10,
    help="Minimum time between edits in seconds",
)
@click.option(
    "--maxlag",
    envvar="WIKIDATA_MAXLAG",
    type=int,
    default=mediawiki_api.DEFAULT_MAXLAG,
    help="Wait on edits while replication lag exceeds this many seconds",
)
@click.option(
    "--deadline",
    type=float,
    default=float("inf"),
    help="Stop cleanly after this many seconds, per request with --stream",
)
@click.option(
    "--stream",
    is_flag=True,
    help="Read one JSON request per input line and apply each before the next",
)
@click.option(
    "--output-format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Log plain text to stderr, or write JSON Lines records to stdout",
)
@click.option("--verbose", "-v", is_flag=True)
@click.version_option()
def main(
    input: TextIO,
    username: str,
    password: str,
    dry_run: bool,
    blocklist_url: str,
    user_agent: str,
    min_time_between_edits: int,
    maxlag: int,
    deadline: float,
    stream: bool,
    output_format: str,
    verbose: bool,
) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logging.getLogger().setLevel(log_level)

    blocklist_title = _blocklist_title(blocklist_url)
    json_output = output_format == "json"
    seconds = deadline
    deadline += time.monotonic()

    session: mediawiki_api.Session | None = None
    if not dry_run:
        try:
            session = mediawiki_api.login(
                username=username,
                password=password,
                user_agent=user_agent,
                maxlag=maxlag,
                deadline=deadline,
            )
        except mediawiki_api.RetriesExhaustedError as e:
            logger.warning("Stopping before login: %s", e)
            if json_output:
                _write(_result_record("stopped", reason=str(e)))
            return

    try:
        blocked_qids: set[str] = set()
        if blocklist_title:
            blocked_qids = mediawiki_api.fetch_page_qids(
                title=blocklist_title,
                user_agent=user_agent,
                deadline=deadline,
            )
            logger.info("Loaded %i QIDs from blocklist", len(blocked_qids))

        edits = (
            []
            if stream
            else list(
                process_graph(
                    input=input,
                    blocked_qids=blocked_qids,
                    user_agent=user_agent,
                    deadline=deadline,
                )
            )
        )
    except mediawiki_api.RetriesExhaustedError as e:
        logger.warning("Stopping before edits: %s", e)
        if json_output:
            _write(_result_record("stopped", reason=str(e)))
        return
    except Exception as e:
        if json_output:
            _write(_result_record("error", reason=str(e)))
        raise

    if stream:
        _stream(
            input=input,
            session=session,
            json_output=json_output,
            blocked_qids=blocked_qids,
            user_agent=user_agent,
            min_time_between_edits=min_time_between_edits,
            seconds=seconds,
        )
        return

    total = sum(len(claims) for _, _, claims, _ in edits)
    published = 0
    errored = 0
    status = "done"
    reason: str | None = None
    last_edit: float = 0.0
    pbar = tqdm(edits, unit="item", disable=json_output)

    try:
        with logging_redirect_tqdm():
            for index, (qid, lastrevid, claims, summary) in enumerate(pbar):
                if not json_output:
                    _log_edit(qid, summary, claims)

                if dry_run:
                    if json_output:
                        _write(_edit_record(qid, summary, claims, "skipped"))
                    continue

                assert session is not None
                if time.monotonic() >= deadline:
                    logger.warning(
                        "Stopping at %i/%i edits: deadline reached",
                        index,
                        len(edits),
                    )
                    status, reason = "stopped", "deadline reached"
                    break
                wait_time = max(0, min_time_between_edits - (time.time() - last_edit))
                if wait_time > 0:
                    logger.debug("Waiting for %.1f seconds", wait_time)
                    time.sleep(wait_time)

                try:
                    mediawiki_api.wbeditentity(
                        session=session,
                        qid=qid,
                        baserevid=lastrevid,
                        edit_data={"claims": claims},
                        summary=summary,
                        deadline=deadline,
                    )
                except mediawiki_api.RetriesExhaustedError as e:
                    logger.warning("Stopping at %i/%i edits: %s", index, len(edits), e)
                    status, reason = "stopped", str(e)
                    break
                except Exception:
                    errored += len(claims)
                    if json_output:
                        _write(_edit_record(qid, summary, claims, "errored"))
                    raise
                published += len(claims)
                last_edit = time.time()
                if json_output:
                    _write(_edit_record(qid, summary, claims, "published"))

            if session is not None:
                mediawiki_api.logout(session)
    except Exception as e:
        status, reason = "error", str(e)
        raise
    finally:
        skipped = total - published - errored
        if json_output:
            _write(_result_record(status, published, errored, skipped, reason))
        else:
            logger.info(
                "Finished with %i statements published, %i errored, %i skipped",
                published,
                errored,
                skipped,
            )
