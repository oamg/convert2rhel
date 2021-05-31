import subprocess
import sys

from collections import namedtuple
from contextlib import contextmanager
from typing import ContextManager

import click
import pexpect
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
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = ""
        for line in iter(process.stdout.readline, b""):
            output += line.decode()
            click.echo(line.decode().rstrip("\n"))
        returncode = process.wait()
        return namedtuple("Result", ["returncode", "output"])(returncode, output)

    return factory


@pytest.fixture()
def convert2rhel(shell):
    """Context manager to run convert2rhel utility.

    This fixture runs the convert2rhel with the specified options and
    do automatic teardown for you. It yields pexpext.spawn object.

    You can assert that some text is in stdout, by using:
    c2r.expect("Sometext here") (see bellow example)

    Or check the utility exit code:
    assert c2r.exitcode == 0 (see bellow example)

    Example:
    >>> def test_good_conversion(convert2rhel):
    >>> with convert2rhel(
    >>>     (
    >>>         "-y "
    >>>         "--no-rpm-va "
    >>>         "--serverurl {} --username {} "
    >>>         "--password {} --pool {} "
    >>>         "--debug"
    >>>     ).format(
    >>>         env.str("RHSM_SERVER_URL"),
    >>>         env.str("RHSM_USERNAME"),
    >>>         env.str("RHSM_PASSWORD"),
    >>>         env.str("RHSM_POOL"),
    >>>     )
    >>> ) as c2r:
    >>>     c2r.expect("Kernel is compatible with RHEL")
    >>> assert c2r.exitstatus == 0

    """

    @contextmanager
    def factory(
        options: str,
        timeout: int = 30 * 60,
    ) -> ContextManager[pexpect.spawn]:
        c2r_runtime = pexpect.spawn(
            f"convert2rhel {options}",
            encoding="utf-8",
            timeout=timeout,
        )
        c2r_runtime.logfile_read = sys.stdout
        try:
            yield c2r_runtime
        except Exception:
            c2r_runtime.close()
            raise
        else:
            c2r_runtime.expect(pexpect.EOF)
            c2r_runtime.close()
        finally:
            if shell("rpm -q subscription-manager").returncode == 0:
                shell("subscription-manager unregister")

    return factory
