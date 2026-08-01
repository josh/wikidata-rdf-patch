import logging
import re
import time
import urllib.parse
from typing import TextIO

import click
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from wikidata_rdf_patch import actions_logging, mediawiki_api

from .rdf_patch import process_graph

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
    verbose: bool,
) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level)
    logging.getLogger().setLevel(log_level)

    blocklist_title = _blocklist_title(blocklist_url)

    session: mediawiki_api.Session | None = None
    if not dry_run:
        session = mediawiki_api.login(
            username=username,
            password=password,
            user_agent=user_agent,
        )

    blocked_qids: set[str] = set()
    if blocklist_title:
        blocked_qids = mediawiki_api.fetch_page_qids(
            title=blocklist_title,
            user_agent=user_agent,
        )
        logger.info("Loaded %i QIDs from blocklist", len(blocked_qids))

    edits = process_graph(input=input, blocked_qids=blocked_qids, user_agent=user_agent)

    last_edit: float = 0.0
    pbar = tqdm(list(edits), unit="item")

    with logging_redirect_tqdm():
        for qid, lastrevid, claims, summary in pbar:
            if summary:
                logger.info(f"Edit {qid}: {summary}")
            else:
                logger.info(f"Edit {qid}")
            for statement in claims:
                statement_id = statement["mainsnak"]["property"]
                statement_snak = statement.get("id", "(new claim)")
                logger.info(f" ⮑ {statement_id} / {statement_snak}")

            if dry_run:
                continue

            assert session is not None
            wait_time = max(0, min_time_between_edits - (time.time() - last_edit))
            if wait_time > 0:
                logger.debug("Waiting for %.1f seconds", wait_time)
                time.sleep(wait_time)

            mediawiki_api.wbeditentity(
                session=session,
                qid=qid,
                baserevid=lastrevid,
                edit_data={"claims": claims},
                summary=summary,
            )
            last_edit = time.time()

        if session is not None:
            mediawiki_api.logout(session)
