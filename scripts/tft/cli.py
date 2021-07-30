import asyncio
import sys

from functools import wraps
from typing import List, Tuple

import click

from envparse import env
from loguru import logger

from scripts.tft.app import tft_runner


def coro(f):
    """Simple hack for enabling coroutines as a click commands.

    More info:
        https://github.com/pallets/click/issues/85#issuecomment-503464628
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.command()
@click.option(
    "-p",
    "--plans",
    default=["/plans/"],
    multiple=True,
    show_default=True,
    help="Plan names. i.e. -p /plan/name. Could be multiple",
)
@click.option(
    "-r",
    "--remote-name",
    default="origin",
    show_default=True,
    help=(
        "Git remote name from which the content of the repo will be cloned at "
        "current commit. Warning: changes should be pushed to the remote "
        "before running this script."
    ),
)
@click.option(
    "-b",
    "--copr-build-id",
    default=[],
    multiple=True,
    help="Use specified builds ids instead of creating a new copr builds.",
)
@click.option("-v", "--verbose", count=True)
@coro
async def cli(
    plans: List[str],
    remote_name: str,
    copr_build_id: Tuple[str],
    verbose: int,
) -> None:
    """Script to interact with testing farm service.

    Ensure the content of .env.

    Example commands:

    -------------------

    # Submit only given plan to tft and use existing copr rpm builds

        python scripts/tft -v -p /plans/integration/inhibit-if-kmods-is-not-supported/centos8 --copr-build-id 2353320 --copr-build-id 2353321

    # Run all plans for some-atypical-remote-name git remote with debug mode (-v)

        python scripts/tft -v -r some-atypical-remote-name
    """
    # some housekeeping
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if env.bool("DEBUG") or verbose > 0 else "INFO")

    # submit tmt plans for execution on tft
    async with tft_runner(
        plans=[plan.strip() for plan in plans],
        remote=remote_name.strip(),
        copr_build_ids=copr_build_id,
    ):
        pass
    click.echo("Job finished. Exiting...")
