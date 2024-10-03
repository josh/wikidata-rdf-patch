import logging
import time
from typing import TextIO

import click

from wikidata_rdf_patch import mediawiki_api

from .rdf_patch import fetch_page_qids, process_graph

logger = logging.getLogger("wikidata-rdf-patch")


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
    "--min-time-between-edits",
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
    min_time_between_edits: int,
    verbose: bool,
) -> None:
    exit_code = 0

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level)

    session: mediawiki_api.Session | None = None
    if not dry_run:
        session = mediawiki_api.login(username, password)

    blocked_qids: set[str] = set()
    if blocklist_url.startswith("https://www.wikidata.org/wiki/"):
        blocked_qids = fetch_page_qids(
            title=blocklist_url.removeprefix("https://www.wikidata.org/wiki/")
        )
        click.echo(f"Loaded {len(blocked_qids)} QIDs from blocklist", err=True)
    elif not blocklist_url.startswith("http"):
        blocked_qids = fetch_page_qids(title=blocklist_url)
        click.echo(f"Loaded {len(blocked_qids)} QIDs from blocklist", err=True)

    edits = process_graph(username=username, input=input, blocked_qids=blocked_qids)

    last_edit: float = 0.0
    for item, claims, summary in edits:
        if not session:
            continue

        wait_time = max(0, min_time_between_edits - (time.time() - last_edit))
        if wait_time > 0:
            logger.info(f"Waiting for {wait_time} seconds")
            time.sleep(wait_time)

        success = mediawiki_api.wbeditentity(
            session=session,
            qid=item.id,
            baserevid=item._revid,
            edit_data={"claims": claims},
            summary=summary,
        )
        if not success:
            logger.error(f"Failed to edit {item.id}")
            exit_code = 1
            continue
        last_edit = time.time()

    if session:
        mediawiki_api.logout(session)

    exit(exit_code)
