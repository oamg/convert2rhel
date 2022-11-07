import dataclasses
import logging
import os
import re
import subprocess
import sys

from collections import namedtuple
from contextlib import contextmanager
from fileinput import FileInput
from typing import ContextManager, Optional

import click
import pexpect
import pytest

from envparse import env


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

env.read_envfile(str(Path(__file__).parents[2] / ".env"))

logging.basicConfig(level="DEBUG" if env.str("DEBUG") else "INFO", stream=sys.stderr)
logger = logging.getLogger(__name__)

SATELLITE_URL = "satellite.sat.engineering.redhat.com"
SATELLITE_PKG_URL = "https://satellite.sat.engineering.redhat.com/pub/katello-ca-consumer-latest.noarch.rpm"
SATELLITE_PKG_DST = "/usr/share/convert2rhel/subscription-manager/katello-ca-consumer-latest.noarch.rpm"

SYSTEM_RELEASE = os.environ["SYSTEM_RELEASE"]


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

    You can verify that some text is in stdout, by using:
    c2r.expect("Sometext here") (see bellow example)
    You can also assert that some text is being reported by c2r by using:
    assert c2r.expect("some text here") == 0 (see bellow example)
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
    >>>     assert c2r.expect("Continuing the conversion") == 0
    >>> assert c2r.exitstatus == 0

    Use of custom timeout option for assertion of pexpect.expect() is recommended for some cases described below.
    Because of the default option for pexpect.expect() timeout being -1
    the timeout might take an hour at best (defined in spawned convert2rhel() instance),
    in case the expected string is not matched and/or EOF exception is not raised.

    The usage of timeout is recommended for cases where the script might get stuck
    at an interactive user prompt, when there is an expected string (not getting outputted)
    followed by expected prompt.
    Recommended option is timeout=300
    Example:
    >>> ...{output omitted}...
    >>> as c2r:
    >>>     assert c2r.expect("Checking for kernel compatibility", timeout=300) == 0
    >>>     c2r.expect("Continue with the system conversion?")
    >>>     c2r.sendline("n")
    >>> ...{output omitted}...

    Unregister means that system wouldn't be unregistered
    from subscription-manager after conversion.
    """

    @contextmanager
    def factory(
        options: str,
        timeout: int = 60 * 60,
        unregister: bool = False,
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
            if unregister:
                shell("subscription-manager unregister")

    return factory


@dataclasses.dataclass
class OsRelease:
    """Dataclass representing the content of /etc/os-release."""

    name: str
    version: str
    id: str
    id_like: str
    version_id: str
    pretty_name: str
    home_url: str
    bug_report_url: str
    ansi_color: Optional[str] = None
    cpe_name: Optional[str] = None
    platform_id: Optional[str] = None

    @classmethod
    def create_from_file(cls, file: Path):
        assert file.exists(), f"File doesn't exist: {str(file)}"
        res = {}
        with open(file) as os_release_f:
            for line in os_release_f:
                try:
                    param, value = line.strip().split("=")
                except ValueError:
                    # we're skipping lines which can't be splitted based on =
                    pass
                else:
                    if param.lower() in cls.__annotations__:
                        res[param.lower()] = value.strip('"')
        return cls(**res)


@pytest.fixture()
def os_release():
    return OsRelease.create_from_file(Path("/etc/os-release"))


class ConfigUtils:
    """Convenient features to work with configs (or any other text files).

    Created specifically to simplify writing integration tests, which requires
    adusting some configs.
    """

    def __init__(self, config_path: Path):
        self.config_path = config_path

    @contextmanager
    def replace_line(self, pattern: str, repl: str):
        """Iterates over config file lines and do re.sub for each line.

        Parameters are the same as in re.sub
        (https://docs.python.org/3/library/re.html#re.sub)

        Example:
        >>> with c2r_config.replace_line(pattern="releasever=.*", repl=f"releasever=9"):
        >>>     # do something here (the config is changed)
        >>>     pass
        >>> # config is restored at this point
        """
        logger.info(f"Scanning {str(self.config_path)} for {repr(pattern)} and replace with {repr(repl)}")
        search = re.compile(pattern)
        backup_suffix = ".bak"
        try:
            with FileInput(files=[str(self.config_path)], inplace=True, backup=backup_suffix) as f:
                for line in f:
                    new_line = search.sub(repl, line)
                    if line != new_line:
                        logger.debug(f"{repr(line.strip())} replaced with\n{repr(new_line.strip())}")
                    # need to write to stdout to write the line to the file
                    print(new_line, end="")
            yield
        finally:
            backup_config = self.config_path.with_suffix(self.config_path.suffix + backup_suffix)
            backup_config.replace(self.config_path)
            logger.debug("ConfigUtils file was restored to the origin state")


@pytest.fixture()
def c2r_config(os_release):
    """ConfigUtils object with already loaded convert2rhel config."""
    release_id2conf = {"centos": "centos", "ol": "oracle"}
    config_path = (
        Path("/usr/share/convert2rhel/configs/")
        / f"{release_id2conf[os_release.id]}-{os_release.version[0]}-x86_64.cfg"
    )
    assert config_path.exists(), f"Can't find Convert2RHEL config file.\n{str(config_path)} - does not exist."
    return ConfigUtils(config_path)


@pytest.fixture
def get_system_release(shell):
    """
    This fixture returns a string of ID and VERSION_ID from /etc/os-release.
    If /etc/os-release is not available, /etc/system-release is read instead.
    These could be in generally used for OS specific conditioning.
    Mapping of OS to ID:
        {
            "Centos Linux": "centos",\n
            "Oracle Linux": "oracle",\n
            "Alma Linux": "almalinux",\n
            "Rocky Linux": "rocky"
        }
    Examples:
        Centos Linux 7.9 => centos-7.9\n
        Oracle Linux 8.6 => oracle-8.6\n
        Alma Linux 8.4 => almalinux-8.4\n
        Rocky Linux 8.5 => rocky-8.5
    """
    path = Path("/etc/system-release")

    if not path.exists():
        path = Path("/etc/os-release")
        with open(path) as osrelease:
            os_release = {}
            for line in osrelease:
                if not re.match(line, "\n"):
                    key, value = line.rstrip().split("=")
                    os_release[key] = value
            system_name = os_release.get("ID").strip('"')
            system_version = os_release.get("VERSION_ID").strip('"')

    else:
        with open(path) as sysrelease:
            sysrelease_as_list = sysrelease.readline().rstrip().split(" ")
            system_name = sysrelease_as_list[0].lower()
            for i in sysrelease_as_list:
                if re.match(r"\d", i):
                    system_version = i

    if system_name == "ol":
        system_name = "oracle"
    system_release = f"{system_name}-{system_version}"

    return system_release


@pytest.fixture()
def config_at():
    """Factory of the ConfigUtils object.

    Created for simplicity injecting it into your testing unit (no need to import).

    Example:
    >>> with config_at(Path("/etc/system-release")).replace_line(
    >>>     "release .+",
    >>>     f"release {os_release.version[0]}.1.1111",
    >>> ):
    """

    def factory(path: Path) -> ConfigUtils:
        return ConfigUtils(path)

    return factory
