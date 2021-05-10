import subprocess
import click

import pytest

from envparse import env


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

env.read_envfile(str(Path(__file__).parents[2] / ".env"))


@pytest.fixture()
def shell(tmp_path):
    """Live shell."""

    def factory(command):
        click.echo(
            "\nExecuting a command:\n{}\n\n".format(command),
            color="green",
        )
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        for line in process.stdout:
            click.echo(line.decode())
        process.wait()
        return process

    return factory
