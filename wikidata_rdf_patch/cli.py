import logging
import os
from typing import TextIO

import click
import pywikibot  # type: ignore
import pywikibot.config  # type: ignore

from .rdf_patch import SITE, fetch_page_qids, process_graph


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
@click.option("--verbose", "-v", is_flag=True)
@click.version_option()
def main(
    input: TextIO,
    username: str,
    password: str,
    dry_run: bool,
    blocklist_url: str,
    verbose: bool,
) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level)

    if dry_run is False:
        pywikibot.config.password_file = "user-password.py"
        with open(pywikibot.config.password_file, "w") as file:
            file.write(f'("{username}", "{password}")')
        os.chmod(pywikibot.config.password_file, 0o600)

        pywikibot.config.usernames["wikidata"]["wikidata"] = username

        SITE.login()

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
    for item, claims, summary in edits:
        if dry_run:
            continue
        item.editEntity({"claims": claims}, summary=summary)
