import subprocess

from collections import namedtuple

import click


def live_shell():
    """
    Live shell.
    Callable directly.
    """

    def factory(command, silent=False, hide_command=False):
        if silent:
            click.echo("This shell call is set to silent=True, therefore no output will be printed.")
        if hide_command:
            click.echo("This shell call is set to hide_command=True, so it won't show the called command.")
        if not silent and not hide_command:
            click.echo(
                "\nExecuting a command:\n{}\n\n".format(command),
                color="green",
            )
        # pylint: disable=consider-using-with
        # Popen is a context-manager in python-3.2+
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = ""
        for line in iter(process.stdout.readline, b""):
            output += line.decode()
            if not silent:
                click.echo(line.decode().rstrip("\n"))
        returncode = process.wait()
        return namedtuple("Result", ["returncode", "output"])(returncode, output)

    return factory
