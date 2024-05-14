import configparser
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
SAT_REG_FILE = dotenv_values("/var/tmp/.env_sat_reg")


SAT_REG_COMMAND = {
    "alma-8-latest": SAT_REG_FILE["ALMA8_SAT_REG"],
    "alma-8.8": SAT_REG_FILE["ALMA88_SAT_REG"],
    "rocky-8-latest": SAT_REG_FILE["ROCKY8_SAT_REG"],
    "rocky-8.8": SAT_REG_FILE["ROCKY88_SAT_REG"],
    "oracle-8-latest": SAT_REG_FILE["ORACLE8_SAT_REG"],
    "centos-8-latest": SAT_REG_FILE["CENTOS8_SAT_REG"],
    "oracle-7": SAT_REG_FILE["ORACLE7_SAT_REG"],
    "centos-7": SAT_REG_FILE["CENTOS7_SAT_REG"],
}


def satellite_curl_command():
    """
    Get the Satellite registration command for the respective system.
    """
    sat_curl_command = None
    try:
        sat_curl_command = SAT_REG_COMMAND[SYSTEM_RELEASE_ENV]
    except KeyError:
        print(f"Key not found in satellite registration command dictionary: {SYSTEM_RELEASE_ENV}")

    return sat_curl_command


SYSTEM_RELEASE_ENV = os.environ["SYSTEM_RELEASE_ENV"]


@pytest.fixture()
def shell(tmp_path):
    """Live shell."""

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


class SystemInformationRelease:
    """
    Helper class.
    Assign a namedtuple with major and minor elements, both of an int type
    Assign a distribution (e.g. centos, oracle, rocky, alma)
    Assign a system release (e.g. redhat-8.8)

    Examples:
    Oracle Linux Server release 7.8
    CentOS Linux release 7.6.1810 (Core)
    CentOS Linux release 8.1.1911 (Core)
    """

    with open("/etc/system-release", "r") as file:
        system_release_content = file.read()
        match_version = re.search(r".+?(\d+)\.(\d+)\D?", system_release_content)
        if not match_version:
            print("not match")
        version = namedtuple("Version", ["major", "minor"])(int(match_version.group(1)), int(match_version.group(2)))
        distribution = system_release_content.split()[0].lower()
        if distribution == "ol":
            distribution = "oracle"
        elif distribution == "red":
            distribution = "redhat"
        system_release = "{}-{}.{}".format(distribution, version.major, version.minor)


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
def remove_repositories(shell, backup_directory):
    """
    Fixture.
    Move all repositories to another location.
    """
    backup_dir = os.path.join(backup_directory, "repos")
    shell(f"mkdir {backup_dir}")
    # Move all repos to other location, so it is not being used
    assert shell(f"mv /etc/yum.repos.d/* {backup_dir}").returncode == 0
    assert len(os.listdir("/etc/yum.repos.d/")) == 0

    yield

    # Return repositories to their original location
    assert shell(f"mv {backup_dir}/* /etc/yum.repos.d/").returncode == 0


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
        "oracle-7": ["oraclelinux-release-el7", "oraclelinux-release"],
        "oracle-8": ["oraclelinux-release-el8", "oraclelinux-release"],
        "centos-7": ["centos-release"],
        "centos-8": ["centos-linux-release"],
        "alma-8": ["almalinux-release"],
        "rocky-8": ["rocky-release"],
    }

    # Run only for non-destructive tests.
    # The envar is added by tmt and is defined in main.fmf for non-destructive tests.
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        os_name = SYSTEM_RELEASE_ENV.split("-")[0]
        os_ver = SYSTEM_RELEASE_ENV.split("-")[1]
        os_key = f"{os_name}-{os_ver[0]}"

        system_release_pkgs = os_to_pkg_mapping.get(os_key)

        for pkg in system_release_pkgs:
            installed = shell(f"rpm -q {pkg}").returncode
            if installed == 1:
                shell(f"yum install -y --releasever={os_ver} {pkg}")

        # Since we try to mitigate any damage caused by the incomplete rollback
        # try to update the system, in case anything got downgraded
        shell("yum update -y", silent=True)


def _load_json_schema(path):
    """Load the JSON schema from the system."""
    assert os.path.exists(path)

    with open(path, mode="r") as handler:
        return json.load(handler)


@pytest.fixture
def pre_registered(shell, request, yum_conf_exclude):
    """
    A fixture to install subscription manager and pre-register the system prior to the convert2rhel run.
    For Oracle Linux we're using the _add_client_tools_repo_oracle to enable the client-tools repository
    to install the subscription-manager package from.
    We also exclude the rhn-client* packages for the same reason.
    On Oracle Linux subscription-manger is obsolete and replaced by rhn-client* packages when installing subman.
    """
    username = TEST_VARS["RHSM_USERNAME"]
    password = TEST_VARS["RHSM_PASSWORD"]
    # Use custom parameters when the fixture is parametrized
    if hasattr(request, "param"):
        username, password = request.param
        print(">>> Using parametrized username and password requested in the fixture.")

    if "oracle" in SYSTEM_RELEASE_ENV:
        # Remove the rhn-client-tools package to make way for subscription-manager installation
        # given subman is obsoleted by the rhn-client-tools on Oracle
        shell("yum remove -y rhn-client-tools")
        # Add the client-tools repository for Oracle linux to install subscription-manager from
        _add_client_tools_repo(shell)

    assert shell("yum install -y subscription-manager").returncode == 0
    # Download the certificate using insecure connection
    shell(
        "curl --create-dirs -ko /etc/rhsm/ca/redhat-uep.pem https://cdn-public.redhat.com/content/public/repofiles/redhat-uep.pem"
    )
    # Register the system
    assert (
        shell(
            "subscription-manager register --serverurl {} --username {} --password {}".format(
                TEST_VARS["RHSM_SERVER_URL"], username, password
            ),
            hide_command=True,
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

    if "oracle" in SYSTEM_RELEASE_ENV:
        _remove_client_tools_repo(shell)

    # For some scenarios we do not pre-register the system, therefore we do not have the original UUID
    # and do not need to verify it stays the same
    if "C2R_TESTS_CHECK_RHSM_UUID_MATCH" in os.environ:
        # Get the registered system UUID
        uuid_raw_output = shell(rhsm_uuid_command).output
        post_c2r_registration_uuid = uuid_raw_output.split(":")[1].strip()

        # Validate it matches with UUID prior to the conversion
        assert original_registration_uuid == post_c2r_registration_uuid

    # The "pre_registered system" test requires to remain registered even after the conversion is completed,
    # so the check "enabled repositories" after the conversion can be executed.
    if "C2R_TESTS_SUBMAN_REMAIN_REGISTERED" not in os.environ:
        assert shell("subscription-manager remove --all").returncode == 0
        shell("subscription-manager unregister")

    # We do not need to spend time on performing the cleanup for some test cases (destructive)
    if "C2R_TESTS_SUBMAN_CLEANUP" in os.environ:
        assert shell("yum remove -y subscription-manager").returncode == 0
        # Remove the redhat-uep.pem certificate, as it won't get removed with the sub-man package on CentOS 7
        if "centos-7" in SYSTEM_RELEASE_ENV:
            shell("rm -f /etc/rhsm/ca/redhat-uep.pem")


@pytest.fixture()
def hybrid_rocky_image():
    """
    Fixture to detect a hybrid Rocky Linux cloud image.
    Removes symlink from /boot/grub2/grubenv -> ../efi/EFI/rocky/grubenv
    The symlink prevents grub to read the grubenv and boot to a different
    kernel than the last selected.
    """
    grubenv_file = "/boot/grub2/grubenv"
    if "rocky" in SystemInformationRelease.distribution:
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
    Create a repo on system with content that is older than the latest released version.
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


@pytest.fixture()
@pytest.mark.yum_conf_exclude
def yum_conf_exclude(shell, backup_directory, request):
    """
    Fixture.
    Define `exclude=kernel kernel-core` in /etc/yum.conf.
    Using pytest.mark.parametrize pass the packages to exclude in a single scenario as a list.
    The fixture is called indirectly in the test function.
    Example:
        # one testcase
        @pytest.mark.parametrize("yum_conf_exclude", [["this", "that", "also_this"]])

        # more testcases
        @pytest.mark.parametrize("yum_conf_exclude", [["this", "that"], ["then_this"]])

        def test_function(yum_conf_exclude):
    """
    exclude = ["rhn-client*"]
    if hasattr(request, "param"):
        exclude = request.param
        print(">>> Using parametrized packages requested in the fixture.")
    yum_config = "/etc/yum.conf"
    backup_dir = os.path.join(backup_directory, "yumconf")
    shell(f"mkdir -v {backup_dir}")
    config_bak = os.path.join(backup_dir, os.path.basename(yum_config))
    config = configparser.ConfigParser()
    config.read(yum_config)

    assert shell(f"cp -v {yum_config} {config_bak}").returncode == 0

    pkgs_to_exclude = " ".join(exclude)
    # If there is already an `exclude` section, append to the existing value
    if config.has_option("main", "exclude"):
        pre_existing_value = config.get("main", "exclude")
        config.set("main", "exclude", f"{pre_existing_value} {pkgs_to_exclude}")
    else:
        config.set("main", "exclude", pkgs_to_exclude)

    with open(yum_config, "w") as configfile:
        config.write(configfile, space_around_delimiters=False)

    assert config.has_option("main", "exclude")
    assert all(pkg in config.get("main", "exclude") for pkg in exclude)

    yield

    # Clean up
    assert shell(f"mv {config_bak} {yum_config}").returncode == 0


def _add_client_tools_repo(shell):
    """
    Helper function.
    Runs only on Oracle Linux system
    Create an ubi repo for its respective major version to install subscription-manager from.
    """
    repo_url = "https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-8.repo"
    if SystemInformationRelease.version.major == 7:
        repo_url = "https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-7-server.repo"

    # Add the redhat-release GPG key
    assert shell(f"curl -o /etc/yum.repos.d/client-tools-for-tests.repo {repo_url}")
    shell("curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://www.redhat.com/security/data/fd431d51.txt")


def _remove_client_tools_repo(shell):
    """
    Helper function.
    Remove the client tools repositories and the redhat-release GPG key
    on the Oracle Linux systems.
    Created as a function given we need to be able to call this during
    the test execution not just the teardown phase.
    """
    # Remove the client-tools repofile
    shell("rm -f /etc/yum.repos.d/client-tools-for-tests.repo")
    # Remove the redhat-release GPG key
    shell("rm -f /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release")


@pytest.fixture
def satellite_registration(shell, yum_conf_exclude, request):
    """
    Register the system to the Satellite server
    """
    # Get the curl command for the respective system
    # from the conftest function
    sat_curl_command = satellite_curl_command()
    sat_script = "/var/tmp/register_to_satellite.sh"
    # If the fixture is parametrized, use the parameter as the registration command
    if hasattr(request, "param"):
        sat_curl_command = request.param
        print(">>> Using parametrized curl command requested in the fixture.")
    if "oracle" in SYSTEM_RELEASE_ENV:
        _add_client_tools_repo(shell)

    # Make sure it returned some value, otherwise it will fail.
    assert sat_curl_command, "The registration command is empty."

    # Curl the Satellite registration script silently
    assert shell(f"{sat_curl_command} -o {sat_script}", silent=True).returncode == 0

    # Make the script executable and run the registration
    assert shell(f"chmod +x {sat_script} && /bin/bash {sat_script}").returncode == 0

    if "oracle" in SYSTEM_RELEASE_ENV:
        _remove_client_tools_repo(shell)

    yield

    # Remove the subman packages installed by the registration script
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        # Remove potential leftover subscription
        shell("subscription-manager remove --all")
        # Remove potential leftover registration
        shell("subscription-manager unregister")
        assert shell("yum remove -y subscription-manager*")


@pytest.fixture
def backup_directory(shell, request):
    """
    Fixture.
    Creates a backup directory for needed file back up.
    Directory at /var/tmp/custom_pytest_marker
    We're using the /var/tmp instead of /tmp
    for the directory to survive a system reboot
    """
    backup_path_base = "/var/tmp"
    backup_dir_name = None
    markers = request.node.own_markers
    for marker in markers:
        if marker.name not in ("parametrize",):
            backup_dir_name = marker.name

    assert backup_dir_name, "Did not manage to parse the function's pytest marker"
    backup_path = os.path.join(backup_path_base, backup_dir_name)

    assert shell(f"mkdir {backup_path}").returncode == 0

    yield backup_path

    shell(f"rm -rf {backup_path}")
