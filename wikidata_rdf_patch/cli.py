import os
from typing import TextIO

import click
import pywikibot  # type: ignore
import pywikibot.config  # type: ignore

from .rdf_patch import SITE, blocklist, process_graph


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
@click.version_option()
def main(input: TextIO, username: str, password: str, dry_run: bool) -> None:
    if dry_run is False:
        pywikibot.config.password_file = "user-password.py"
        with open(pywikibot.config.password_file, "w") as file:
            file.write(f'("{username}", "{password}")')
        os.chmod(pywikibot.config.password_file, 0o600)

        pywikibot.config.usernames["wikidata"]["wikidata"] = username

        SITE.login()

    blocked_qids = blocklist()

    edits = process_graph(username=username, input=input, blocked_qids=blocked_qids)
    for item, claims, summary in edits:
        if dry_run:
            continue
        item.editEntity({"claims": claims}, summary=summary)
