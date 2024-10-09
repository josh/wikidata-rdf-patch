import logging
import time
from typing import TextIO

import click
from tqdm import tqdm

import wikidata_rdf_patch.actions_logging as actions_logging
from wikidata_rdf_patch import mediawiki_api

from .rdf_patch import fetch_page_qids, process_graph

actions_logging.setup()
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

    session: mediawiki_api.Session | None = None
    if not dry_run:
        session = mediawiki_api.login(
            username=username,
            password=password,
            user_agent=user_agent,
        )

    blocked_qids: set[str] = set()
    if blocklist_url.startswith("https://www.wikidata.org/wiki/"):
        blocked_qids = fetch_page_qids(
            title=blocklist_url.removeprefix("https://www.wikidata.org/wiki/")
        )
        logger.info("Loaded %i QIDs from blocklist", len(blocked_qids))
    elif not blocklist_url.startswith("http"):
        blocked_qids = fetch_page_qids(title=blocklist_url)
        logger.info("Loaded %i QIDs from blocklist", len(blocked_qids))

    edits = process_graph(input=input, blocked_qids=blocked_qids, user_agent=user_agent)

    last_edit: float = 0.0
    pbar = tqdm(list(edits), unit="item")

    if not session:
        return

    for item, claims, summary in pbar:
        pbar.set_description(item["id"])
        if summary:
            pbar.write(f"Edit {item['id']}: {summary}")
        else:
            pbar.write(f"Edit {item['id']}")
        for statement in claims:
            statement_id = statement["mainsnak"]["property"]
            statement_snak = statement.get("id", "(new claim)")
            pbar.write(f" ⮑ {statement_id} / {statement_snak}")

        wait_time = max(0, min_time_between_edits - (time.time() - last_edit))
        if wait_time > 0:
            pbar.write(f"Waiting for {wait_time:.1f} seconds")
            time.sleep(wait_time)

        mediawiki_api.wbeditentity(
            session=session,
            qid=item["id"],
            baserevid=item["lastrevid"],
            edit_data={"claims": claims},
            summary=summary,
        )
        last_edit = time.time()

    if session:
        mediawiki_api.logout(session)
