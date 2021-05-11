import click
import subprocess

import pytest

from collections import namedtuple
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
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = ''
        for line in iter(process.stdout.readline, b''):
            output += line.decode()
            click.echo(line.decode().rstrip('\n'))
        returncode = process.wait()
        return namedtuple('Result', ['returncode', 'output'])(returncode, output)


    return factory
