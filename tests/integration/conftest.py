import dataclasses
import json
import logging
import os
import re
import shutil
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

logging.basicConfig(level="DEBUG" if env.str("DEBUG") else "INFO", stream=sys.stderr)
logger = logging.getLogger(__name__)

SATELLITE_URL = "satellite.sat.engineering.redhat.com"
SATELLITE_PKG_URL = "https://satellite.sat.engineering.redhat.com/pub/katello-ca-consumer-latest.noarch.rpm"
SATELLITE_PKG_DST = "/usr/share/convert2rhel/subscription-manager/katello-ca-consumer-latest.noarch.rpm"

SYSTEM_RELEASE_ENV = os.environ["SYSTEM_RELEASE_ENV"]


@pytest.fixture()
def shell(tmp_path):
    """Live shell."""

    def factory(command):
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
            c2r_runtime.expect(pexpect.EOF)
            c2r_runtime.close()
        finally:
            # Check if child is still alive, if so, send SIGINT
            # this handles the TIMEOUT exception - if the process is still alive,
            # the EOF is not raised, the process gets terminated.
            # If pexpect.EOF exception is not raised (timeouts after 15 minutes)
            # force terminate the process.
            if c2r_runtime.isalive():
                c2r_runtime.sendcontrol("c")
                try:
                    c2r_runtime.expect(pexpect.EOF, timeout=900)
                except pexpect.TIMEOUT:
                    c2r_runtime.terminate(force=True)
            if unregister:
                shell("subscription-manager unregister")

            # Scan for unknown errors in the pre-conversion assessment.
            try:
                with open("JSON") as f:
                    assessment = json.read(f)
            except Exception:
                # We only check for unknown errors when the run created the
                # json formatted assessment.
                pass
            else:
                message = []
                for action in assessment:
                    if action["result"].id == "UNKNOWN_ERROR":
                        message.extend(
                            (
                                "== Action caught SystemExit and returned an UNKNOWN_ERROR:",
                                "%s: %s" % (action.id, action["result"]),
                            )
                        )

                    elif action["result"].id == "UNEXPECTED_ERROR":
                        message.extend(
                            (
                                "== Action Framework caught an unhandled exception from an Action and returned an UNEXPECTED_ERROR:",
                                "%s: %s" % (action.id, action["result"]),
                            )
                        )

                    # The next two are specific to two Actions. We can remove these from this
                    # function once they are ported in convert2rhel.
                    elif (
                        action.id == "REMOVE_EXCLUDED_PACKAGES"
                        and action["result"].id == "EXCLUDED_PACKAGE_REMOVAL_FAILED"
                        and "unknown" in action["result"].description
                    ):
                        message.extend(
                            (
                                "== Action caught SystemExit while removing packages:",
                                "%s: %s" % (action.id, action["result"]),
                            )
                        )

                    elif (
                        action.id == "REMOVE_EXCLUDED_PACKAGES"
                        and action["result"].id == "REPOSITORY_FILE_PACKAGE_REMOVAL_FAILED"
                        and "unknown" in action["result"].description
                    ):
                        message.extend(
                            (
                                "== Action caught SystemExit while removing packages:",
                                "%s: %s" % (action.id, action["result"]),
                            )
                        )

                if message:
                    raise RuntimeError("\n".join(message))

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
                    # we're skipping lines which can't be split based on =
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
    adjusting some configs.
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
    release_id2conf = {"centos": "centos", "ol": "oracle", "almalinux": "almalinux", "rocky": "rocky"}
    config_path = (
        Path("/usr/share/convert2rhel/configs/")
        / f"{release_id2conf[os_release.id]}-{os_release.version[0]}-x86_64.cfg"
    )
    assert config_path.exists(), f"Can't find Convert2RHEL config file.\n{str(config_path)} - does not exist."
    return ConfigUtils(config_path)


@pytest.fixture
def system_release(shell):
    """
    This fixture returns a string of ID and VERSION_ID from /etc/os-release.
    If /etc/os-release is not available, /etc/system-release is read instead.
    These could be in generally used for OS specific conditioning.
    To be used whenever we need live information about system release.
    E.g. after conversion system release check.
    Otherwise, use hardcoded SYSTEM_RELEASE_ENV envar from /plans/main.fmf
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
        Alma Linux 8.7 => almalinux-8.7\n
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


@pytest.fixture()
def log_file_data():
    """
    This fixture reads and returns data from the convert2rhel.log file.
    Mainly used for after conversion checks, where we match required strings to the log output.
    """
    convert2rhel_log_file = "/var/log/convert2rhel/convert2rhel.log"

    with open(convert2rhel_log_file, "r") as logfile:
        log_data = logfile.read()

        return log_data


@pytest.fixture(scope="function")
def required_packages(shell):
    """
    Installs packages based on values under TEST_REQUIRES envar in tmt metadata, when called.
    """
    try:
        required_packages = os.environ.get("TEST_REQUIRES").split(" ")
        for package in required_packages:
            print(f"\nPREPARE: Installing required {package}")
            assert shell(f"yum install -y {package}")

        yield

        for package in required_packages:
            print(f"\nCLEANUP: Removing previously installed required {package}")
            assert shell(f"yum remove -y *{package}*")

    except KeyError:
        raise


@pytest.fixture(scope="function")
def repositories(shell):
    """
    Fixture.
    Move all repositories to another location, do the same for EUS if applicable.
    """
    backup_dir = "/tmp/test-backup-release_backup"
    backup_dir_eus = "%s_eus" % backup_dir

    # Move all repos to other location, so it is not being used
    shell(f"mkdir {backup_dir}")
    assert shell(f"mv /etc/yum.repos.d/* {backup_dir}").returncode == 0

    # EUS version use hardcoded repos from c2r as well
    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell(f"mkdir {backup_dir_eus}")
        assert shell(f"mv /usr/share/convert2rhel/repos/* {backup_dir_eus}").returncode == 0

    yield

    # Return repositories to their original location
    assert shell(f"mv {backup_dir}/* /etc/yum.repos.d/").returncode == 0
    assert shell(f"rm -rf {backup_dir}")
    # Return EUS repositories to their original location
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell(f"mv {backup_dir_eus}/* /usr/share/convert2rhel/repos/").returncode == 0
        assert shell(f"rm -rf {backup_dir_eus}")


@pytest.fixture(autouse=True)
def missing_os_release_package_workaround(shell):
    # TODO(danmyway) remove when/if the issue gets fixed
    """
    Fixture to workaround issues with missing `*-linux-release`
    package, after incomplete rollback.
    """
    # run only after the test finishes
    yield

    os_to_pkg_mapping = {
        "oracle-7": "oracle*-release-el7",
        "oracle-8": "oraclelinux-release-el8",
        "centos-7": "centos-release",
        "centos-8": "centos-linux-release",
        "alma-8": "almalinux-release",
        "rocky-8": "rocky-release",
    }

    # Run only for non-destructive tests.
    # The envar is added by tmt and is defined in main.fmf for non-destructive tests.
    if "INT_TESTS_NONDESTRUCTIVE" in os.environ:
        os_name = SYSTEM_RELEASE_ENV.split("-")[0]
        os_ver = SYSTEM_RELEASE_ENV.split("-")[1]
        os_key = f"{os_name}-{os_ver[0]}"

        system_release_pkg = os_to_pkg_mapping.get(os_key)

        rpm_output = shell(f"rpm -qa {system_release_pkg}").output
        if "not installed" in rpm_output:
            shell(f"yum install -y --releasever={os_ver} {system_release_pkg}")


def _load_json_schema(path):
    """Load the JSON schema from the system."""
    assert os.path.exists(path)

    with open(path, mode="r") as handler:
        return json.load(handler)


@pytest.fixture
def pre_registered(shell):
    """
    A fixture to install subscription manager and pre-register the system prior to the convert2rhel run.
    """
    assert shell("yum install -y subscription-manager").returncode == 0
    # Download the SSL certificate
    shell("curl --create-dirs -o /etc/rhsm/ca/redhat-uep.pem https://ftp.redhat.com/redhat/convert2rhel/redhat-uep.pem")
    # Register the system
    assert (
        shell(
            "subscription-manager register --serverurl {} --username {} --password {}".format(
                env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD")
            )
        ).returncode
        == 0
    )

    assert shell("subscription-manager attach --pool {}".format(env.str("RHSM_POOL"))).returncode == 0

    rhsm_uuid_command = "subscription-manager identity | grep identity"

    uuid_raw_output = shell(rhsm_uuid_command).output

    # The `subscription-manager identity | grep identity` command returns
    # system identity: <UUID>, we need to store just the system UUID
    original_registration_uuid = uuid_raw_output.split(":")[1].strip()

    yield

    # For some scenarios we do not pre-register the system, therefore we do not have the original UUID
    # and do not need to verify it stays the same
    if "C2R_TESTS_CHECK_RHSM_UUID_MATCH" in os.environ:
        # Get the registered system UUID
        uuid_raw_output = shell(rhsm_uuid_command).output
        post_c2r_registration_uuid = uuid_raw_output.split(":")[1].strip()

        # Validate it matches with UUID prior to the conversion
        assert original_registration_uuid == post_c2r_registration_uuid
        del os.environ["C2R_TESTS_CHECK_RHSM_UUID_MATCH"]

        assert shell("subscription-manager remove --pool {}".format(env.str("RHSM_POOL"))).returncode == 0
        assert shell("subscription-manager unregister").returncode == 0

    # We do not need to spend time on performing the cleanup for some test cases (destructive)
    if "C2R_TESTS_SUBMAN_CLEANUP" in os.environ:
        assert shell("yum remove -y subscription-manager").returncode == 0
        # Remove the redhat-uep.pem certificate, as it won't get removed with the sub-man package on CentOS 7
        if "centos-7" in SYSTEM_RELEASE_ENV:
            shell("rm -f /etc/rhsm/ca/redhat-uep.pem")

        del os.environ["C2R_TESTS_SUBMAN_CLEANUP"]


@pytest.fixture
def disabled_telemetry(shell):
    """
    Fixture exporting CONVERT2RHEL_DISABLE_TELEMETRY envar to disable data collection.
    Removes after the test.
    Used in scenarios where we do not care about the data collection and want to bypass
    the data collection acknowledgement prompt.
    """
    os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"] = "1"

    yield

    if os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"]:
        del os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"]


@pytest.fixture()
def hybrid_rocky_image(shell, system_release):
    """
    Fixture to detect a hybrid Rocky Linux cloud image.
    Removes symlink from /boot/grub2/grubenv -> ../efi/EFI/rocky/grubenv
    The symlink prevents grub to read the grubenv and boot to a different
    kernel than the last selected.
    """
    grubenv_file = "/boot/grub2/grubenv"
    if "rocky" in system_release:
        if os.path.islink(grubenv_file):
            target_grubenv_file = os.path.realpath(grubenv_file)

            os.remove(grubenv_file)
            shutil.copy2(target_grubenv_file, grubenv_file)


@pytest.fixture(autouse=True, scope="function")
def tmt_reboot_count_reset(shell):
    """
    Fixture to reset reboot counters.
    We need this to be able to perform reboot using the tmt-reboot.
    After each reboot the TMT_REBOOT_COUNT += 1, meaning we would need to
    reflect the test order to be able to perform the reboot.
    The fixture will reset the counter for each function, so we always start with "0".
    """
    shell("export TMT_REBOOT_COUNT=0 && export REBOOTCOUNT=0 && export RSTRNT_REBOOTCOUNT=0")


@pytest.fixture(scope="session", autouse=True)
def rcmtools_cleanup():
    """
    Fixture to clean up rcmtools packages and repository from the host.
    These are an artifact of Testing Farm installation, which have no usage for our testing
    and can negatively impact the test results in some scenarios.
    """
    reponame = "rcmtools"

    conflicting_pkgs = ["libcomps"]

    # Get list of packages installed from the rcmtools repository
    yum_command = f"yum list installed --disablerepo=* --enablerepo={reponame} | awk '$3==\"@{reponame}\" {{print $1}}'"

    installed_packages = subprocess.run(
        f"{yum_command} | wc -l",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        check=True,
        universal_newlines=True,
    )

    result = subprocess.run(yum_command, stdout=subprocess.PIPE, shell=True, check=True, universal_newlines=True)

    # Remove the packages installed from the rcmtools repo
    if "oracle-7" in SYSTEM_RELEASE_ENV and installed_packages.stdout.splitlines()[-1].strip() != "0":
        for pkg in conflicting_pkgs:
            if pkg in result.stdout:
                subprocess.run(f"yum remove -y {pkg}", check=True, shell=True)

    yield
