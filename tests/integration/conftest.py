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

from dotenv import dotenv_values


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path


logging.basicConfig(level=os.environ.get("DEBUG", "INFO"), stream=sys.stderr)
logger = logging.getLogger(__name__)

TEST_VARS = dotenv_values("/var/tmp/.env")

SATELLITE_URL = "satellite.sat.engineering.redhat.com"
SATELLITE_PKG_URL = "https://satellite.sat.engineering.redhat.com/pub/katello-ca-consumer-latest.noarch.rpm"
SATELLITE_PKG_DST = "/usr/share/convert2rhel/subscription-manager/katello-ca-consumer-latest.noarch.rpm"

SYSTEM_RELEASE_ENV = os.environ["SYSTEM_RELEASE_ENV"]


@pytest.fixture()
def shell(tmp_path):
    """Live shell."""

    def factory(command, silent=False):
        if not silent:
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
    >>>         TEST_VARS["RHSM_SERVER_URL"],
    >>>         TEST_VARS["RHSM_USERNAME"],
    >>>         TEST_VARS["RHSM_PASSWORD"],
    >>>         TEST_VARS["RHSM_POOL"],
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
def remove_repositories(shell):
    """
    Fixture.
    Move all repositories to another location.
    """
    backup_dir = "/tmp/test-backup-release_backup"

    # Move all repos to other location, so it is not being used
    shell(f"mkdir {backup_dir}")
    assert shell(f"mv /etc/yum.repos.d/* {backup_dir}").returncode == 0

    yield

    # Return repositories to their original location
    assert shell(f"mv {backup_dir}/* /etc/yum.repos.d/").returncode == 0
    assert shell(f"rm -rf {backup_dir}")


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
def pre_registered(shell, request):
    """
    A fixture to install subscription manager and pre-register the system prior to the convert2rhel run.
    """
    username = TEST_VARS["RHSM_USERNAME"]
    password = TEST_VARS["RHSM_PASSWORD"]
    # Use custom parameters when the fixture is parametrized
    if hasattr(request, "param"):
        username, password = request.param

    assert shell("yum install -y subscription-manager").returncode == 0
    # Download the SSL certificate
    shell("curl --create-dirs -o /etc/rhsm/ca/redhat-uep.pem https://ftp.redhat.com/redhat/convert2rhel/redhat-uep.pem")
    # Register the system
    assert (
        shell(
            "subscription-manager register --serverurl {} --username {} --password {}".format(
                TEST_VARS["RHSM_SERVER_URL"], username, password
            ),
            silent=True,
        ).returncode
        == 0
    )

    if "C2R_TESTS_NOSUB" not in os.environ:
        assert shell("subscription-manager attach --pool {}".format(TEST_VARS["RHSM_POOL"])).returncode == 0

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

    assert shell("subscription-manager remove --all").returncode == 0
    shell("subscription-manager unregister")

    # We do not need to spend time on performing the cleanup for some test cases (destructive)
    if "C2R_TESTS_SUBMAN_CLEANUP" in os.environ:
        assert shell("yum remove -y subscription-manager").returncode == 0
        # Remove the redhat-uep.pem certificate, as it won't get removed with the sub-man package on CentOS 7
        if "centos-7" in SYSTEM_RELEASE_ENV:
            shell("rm -f /etc/rhsm/ca/redhat-uep.pem")


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


@pytest.fixture()
def environment_variables(request):
    """
    Fixture.
    Sets and unsets required environment variables.
    Environment variable(s) needs to be passed as a list(s) to pytest parametrize.
    Usage:
    @pytest.mark.parametrize("envars", [["LIST", "OF"], ["ENVIRONMENT", "VARIABLES"]])
    """

    def _set_env_var(envars):
        for envar in envars:
            os.environ[envar] = "1"

    yield _set_env_var

    def _unset_env_var(envars):
        for envar in envars:
            if envar in os.environ:
                del os.environ[envar]
            assert envar not in os.environ

    return _unset_env_var


# TODO remove when https://issues.redhat.com/browse/RHELC-1389 resolved
@pytest.fixture(autouse=True, scope="function")
def remediation_out_of_date_packages(shell):
    """
    Remediation fixture.
    There is an open issue https://issues.redhat.com/browse/RHELC-1389
    The python3-syspurpose package is left outdated on the system in some cases,
    causing subsequent tests to fail.
    Update the package at the end of each test function if needed.
    """
    problematic_packages = ["python3-syspurpose"]

    yield

    for package in problematic_packages:
        shell(f"yum update -y {package}")


def _create_old_repo(distro: str, repo_name: str):
    """
    Create a repo on system with content that is older then the latest released version.
    The intended use is for Rocky-8 and Alma-8.
    """
    baseurl = None
    if distro == "alma":
        baseurl = "https://repo.almalinux.org/vault/8.6/BaseOS/$basearch/os/"
    elif distro == "rocky":
        baseurl = "https://download.rockylinux.org/vault/rocky/8.6/BaseOS/$basearch/os/"
    else:
        pytest.fail(f"Unsupported distro ({distro}) provided.")
    with open(f"/etc/yum.repos.d/{repo_name}.repo", "w") as f:
        f.write(f"[{repo_name}]\n")
        f.write(f"name={repo_name}\n")
        f.write(f"baseurl={baseurl}\n")
        f.write("enabled=0\n")
        f.write("gpgcheck=0\n")


@pytest.fixture(scope="function")
def kernel(shell):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """

    # If the fixture gets executed after second `tmt-reboot` (after cleanup of a test) then
    # do not trigger test again by yielding.
    # Note that we cannot just run `return` command as this fixture require to have
    # `yield` call in every situation. That's why calling `pytest.skip`.
    if int(os.environ["TMT_REBOOT_COUNT"]) > 1:
        pytest.skip("The `kernel` fixture has already run.")

    if os.environ["TMT_REBOOT_COUNT"] == "0":
        # Set default kernel
        if "centos-7" in SYSTEM_RELEASE_ENV:
            assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
            shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'")
        elif "oracle-7" in SYSTEM_RELEASE_ENV:
            assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
            shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'")
        elif "centos-8" in SYSTEM_RELEASE_ENV:
            assert shell("yum install kernel-4.18.0-348.el8 -y").returncode == 0
            shell("grub2-set-default 'CentOS Stream (4.18.0-348.el8.x86_64) 8'")
        # Test is being run only for the latest released oracle-linux
        elif "oracle-8" in SYSTEM_RELEASE_ENV:
            assert shell("yum install kernel-4.18.0-80.el8.x86_64 -y").returncode == 0
            shell("grub2-set-default 'Oracle Linux Server (4.18.0-80.el8.x86_64) 8.0'")
        elif "alma-8" in SYSTEM_RELEASE_ENV:
            repo_name = "alma_old"
            _create_old_repo(distro="alma", repo_name=repo_name)
            assert shell(f"yum install kernel-4.18.0-372.13.1.el8_6.x86_64 -y --enablerepo {repo_name}")
            shell("grub2-set-default 'AlmaLinux (4.18.0-372.13.1.el8_6.x86_64) 8.6 (Sky Tiger)'")
        elif "rocky-8" in SYSTEM_RELEASE_ENV:
            repo_name = "rocky_old"
            _create_old_repo(distro="rocky", repo_name=repo_name)
            assert shell(f"yum install kernel-4.18.0-372.13.1.el8_6.x86_64 -y --enablerepo {repo_name}")
            shell("grub2-set-default 'Rocky Linux (4.18.0-372.13.1.el8_6.x86_64) 8.6 (Green Obsidian)'")

        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # We need to get the name of the latest kernel
        # present in the repositories

        # Install 'yum-utils' required by the repoquery command
        shell("yum install yum-utils -y")

        # Get the name of the latest kernel
        latest_kernel = shell(
            "repoquery --quiet --qf '%{BUILDTIME}\t%{VERSION}-%{RELEASE}' kernel 2>/dev/null | tail -n 1 | awk '{printf $NF}'"
        ).output

        # Get the full name of the kernel (ignore rescue kernels)
        full_name = shell(
            'grubby --info ALL | grep "title=.*{}" | grep -vi "rescue" | tr -d \'"\' | sed \'s/title=//\''.format(
                latest_kernel
            )
        ).output

        # Set the latest kernel as the one we want to reboot to
        shell("grub2-set-default '{}'".format(full_name.strip()))

        # Remove the mocked repofile
        if "alma-8" in SYSTEM_RELEASE_ENV:
            shell(f"rm -f /etc/yum.repos.d/alma_old.repo")
        elif "rocky-8" in SYSTEM_RELEASE_ENV:
            shell(f"rm -f /etc/yum.repos.d/rocky_old.repo")

        # Reboot after clean-up
        shell("tmt-reboot -t 600")
