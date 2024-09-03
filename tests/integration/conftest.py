import configparser
import dataclasses
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import warnings

from collections import namedtuple
from contextlib import contextmanager
from typing import ContextManager

import click
import pexpect
import pytest

from _pytest.warning_types import PytestUnknownMarkWarning
from dotenv import dotenv_values


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path


logging.basicConfig(level=os.environ.get("DEBUG", "INFO"), stream=sys.stderr)
logger = logging.getLogger(__name__)


def pytest_collection_modifyitems(items):
    # This will filter out warning for unregistered markers
    # e.g. "PytestUnknownMarkWarning: Unknown pytest.mark.test_this_interface - is this a typo?"
    warnings.filterwarnings("ignore", category=PytestUnknownMarkWarning, message=r"Unknown pytest\.mark\.test_[^ ]+ -")
    for item in items:
        marker_name = item.nodeid.split("::")[-1]  # Derive marker from the nodeid test_file.py::test_this_interface
        # If the test is parametrized, we need to exclude the parameter values, the decorator looks like this
        # MarkDecorator(mark=Mark(name='test_this_interface[0.01.0]', args=(), kwargs={}))
        marker_name = marker_name.split("[")[0] if "[" in marker_name else marker_name
        try:
            marker = getattr(pytest.mark, marker_name)
        except AttributeError:
            marker = pytest.mark.custom_marker(marker_name)  # Use a custom marker if the attribute doesn't exist
        item.add_marker(marker)


TEST_VARS = dotenv_values("/var/tmp/.env")
SAT_REG_FILE = dotenv_values("/var/tmp/.env_sat_reg")


SYSTEM_RELEASE_ENV = os.environ["SYSTEM_RELEASE_ENV"]


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


@pytest.fixture(name="shell")
def shell_fixture(tmp_path):
    """
    Live shell fixture.
    """
    return live_shell()


class SubscriptionManager:
    def __init__(self):
        self.shell = live_shell()

    def add_keys_and_certificates(self):
        """
        Add the SSL certificate for accessing the CDN and the redhat RPM GPG key.
        """
        self.shell(
            "curl --create-dirs -ko /etc/rhsm/ca/redhat-uep.pem https://cdn-public.redhat.com/content/public/repofiles/redhat-uep.pem"
        )
        self.shell(
            "curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://security.access.redhat.com/data/fd431d51.txt"
        )

    def add_client_tools_repo(self):
        """
        Add the client tools repository to install subscription manager from.
        """
        version = "7-server" if SystemInformationRelease.version.major == 7 else SystemInformationRelease.version.major
        repo_url = f"https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-{version}.repo"

        self.shell(f"yum-config-manager --add-repo {repo_url}")

        # On CentOS 8.5 we need to replace the $releasever in the url to 8.5,
        # otherwise the dnf will complain with dependency issues.
        if "centos-8" in SYSTEM_RELEASE_ENV:
            self.shell(r"sed -i 's#\$releasever#8.5#' /etc/yum.repos.d/client-tools-for-rhel-8.repo")

    def install_package(self, package_name="subscription-manager"):
        """
        Install a package.
        :param package_name: The package to be installed. Default is subscription-manager.
        :type package_name: str
        """
        command = f"yum install -y {package_name}"
        # rhn-client-tools package obsoletes subscription-manager on Oracle Linux
        # set the obsoletes option to 0 to be able to install the package
        if SystemInformationRelease.distribution == "oracle":
            command += " --setopt=obsoletes=0"

        return self.shell(command)

    def remove_package(self, package_name="subscription-manager*"):
        """
        Removes a package.
        :param package_name: The package to be installed. Default is subscription-manager*.
        :type package_name: str
        """
        command = f"yum remove -y {package_name}"
        return self.shell(command)

    def remove_client_tools_repo(self):
        """
        Remove the client tools repository file.
        """
        command = "rm -f /etc/yum.repos.d/client-tools-for-rhel*.repo"

        return self.shell(command)

    def remove_keys_and_certificates(self):
        """
        Remove the SSL certificate for accessing the CDN and the redhat RPM GPG key.
        """
        self.shell("rm -f /etc/rhsm/ca/redhat-uep.pem")
        self.shell("rm -f /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release")

    def unregister(self):
        """
        Remove potential leftover subscription, unregister the system.
        """
        # Remove potential leftover subscription
        self.shell("subscription-manager remove --all")
        # Remove potential leftover registration
        command = "subscription-manager unregister"

        return self.shell(command)

    def set_up_requirements(self, use_staging_cdn=False):
        """
        Usual full preparation workflow.
        Calls, where applicable:
            self.remove_package(package_name="rhn-client-tools") # only on Oracle Linux
            self.add_keys_and_certificates()
            self.add_client_tools_repo()
            self.install_package()
            self.set_up_to_stagecdn() # only when use_staging_cdn is True
        """
        if SystemInformationRelease.distribution == "oracle":
            self.remove_package(package_name="rhn-client-tools")
        self.add_keys_and_certificates()
        self.add_client_tools_repo()
        self.install_package()
        if use_staging_cdn:
            self.set_up_to_stagecdn()

    def set_up_to_stagecdn(self):
        # Point the server hostname to the staging environment,
        # so we don't need to pass it to convert2rhel explicitly
        # RHSM baseurl gets pointed to a stage cdn
        self.shell(
            "subscription-manager config --rhsm.baseurl=https://{0} --server.hostname={1}".format(
                TEST_VARS["RHSM_STAGECDN"], TEST_VARS["RHSM_SERVER_URL"]
            ),
            silent=True,
        )

    def clean_up(self):
        """
        Usual full teardown workflow.
        Calls where applicable:
            self.unregister()
            self.remove_package()
            self.remove_client_tools_repo()
            self.remove_keys_and_certificates()
        """
        self.unregister()
        self.remove_package()
        self.remove_client_tools_repo()
        self.remove_keys_and_certificates()


@pytest.fixture()
def fixture_subman():
    """
    Fixture.
    Set up the subscription manager on the system. Wrapper around SubscriptionManager class and its methods.
    By default sets the subscription manager to the stagecdn (needed for SCA Enabled accounts). If you want
    to disable it, please edit this fixture to utilize parametrization.
    """
    subman = SubscriptionManager()

    subman.set_up_requirements(use_staging_cdn=True)

    yield

    # The "pre_registered system" test requires to remain registered even after the conversion is completed,
    # so the check "enabled repositories" after the conversion can be executed.
    if "C2R_TESTS_SUBMAN_REMAIN_REGISTERED" not in os.environ:
        subman.unregister()

    # We do not need to spend time on performing the cleanup for some test cases (destructive)
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        subman.clean_up()


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
    >>>         "--password {} "
    >>>         "--debug"
    >>>     ).format(
    >>>         TEST_VARS["RHSM_SERVER_URL"],
    >>>         TEST_VARS["RHSM_SCA_USERNAME"],
    >>>         TEST_VARS["RHSM_SCA_PASSWORD"],
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
        # Evaluate if we're looking at CentOS Stream
        is_stream = re.match("stream", system_release_content.split()[1].lower())
        distribution = system_release_content.split()[0].lower()
        if distribution == "ol":
            distribution = "oracle"
        elif distribution == "red":
            distribution = "redhat"
        match_version = re.search(r".+?(\d+)\.?(\d+)?\D?", system_release_content)
        if not match_version:
            pytest.fail("Something is wrong with the /etc/system-release, cowardly refusing to continue.")
        if is_stream:
            distribution = "stream"
            version = namedtuple("Version", ["major", "minor"])(int(match_version.group(1)), "latest")
            system_release = "{}-{}-{}".format(distribution, version.major, version.minor)
        else:
            version = namedtuple("Version", ["major", "minor"])(
                int(match_version.group(1)), int(match_version.group(2))
            )
            system_release = "{}-{}.{}".format(distribution, version.major, version.minor)


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
def remove_repositories(shell, backup_directory):
    """
    Fixture.
    Move all repositories to another location.
    """
    backup_dir = os.path.join(backup_directory, "repos")
    shell(f"mkdir {backup_dir}")
    # Move all repos to other location, so it is not being used
    assert shell(f"mv -v /etc/yum.repos.d/* {backup_dir}").returncode == 0
    assert len(os.listdir("/etc/yum.repos.d/")) == 0

    yield

    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        # Make sure the reposdir is present
        # It gets removed with the *-release package on EL9 systems
        shell("mkdir -p /etc/yum.repos.d")
        # Return repositories to their original location
        assert shell(f"mv {backup_dir}/* /etc/yum.repos.d/").returncode == 0


@pytest.fixture
def pre_registered(shell, request, fixture_subman):
    """
    A fixture to install subscription manager and pre-register the system prior to the convert2rhel run.
    We're using the client-tools-for-rhel-<version>-rpms repository to install the subscription-manager package from.
    The rhn-client-tools package obsoletes the subscription-manager, so we remove the package on Oracle Linux.
    By default, the RHSM_SCA_USERNAME and RHSM_SCA_PASSWORD is passed to the subman registration.
    Can be parametrized by requesting a different KEY from the TEST_VARS file.
    @pytest.mark.parametrize("pre_registered", [("DIFFERENT_USERNAME", "DIFFERENT_PASSWORD")], indirect=True)
    """
    username = TEST_VARS["RHSM_SCA_USERNAME"]
    password = TEST_VARS["RHSM_SCA_PASSWORD"]
    # Use custom keys when the fixture is parametrized
    if hasattr(request, "param"):
        username_key, password_key = request.param
        username = TEST_VARS[username_key]
        password = TEST_VARS[password_key]
        print(">>> Using parametrized username and password requested in the fixture.")

    # Register the system
    assert (
        shell(
            "subscription-manager register --serverurl {0} --username {1} --password {2}".format(
                TEST_VARS["RHSM_SERVER_URL"], username, password
            ),
            hide_command=True,
        ).returncode
        == 0
    ), f"Failed to pre-register the system. The subscription manager call has failed."

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


@pytest.fixture()
def hybrid_rocky_image(shell):
    """
    Fixture to detect a hybrid Rocky Linux cloud image.
    Removes symlink from /boot/grub2/grubenv -> ../efi/EFI/rocky/grubenv
    The symlink prevents grub to read the grubenv and boot to a different
    kernel than the last selected.
    """
    grubenv_file = "/boot/grub2/grubenv"
    is_efi = shell("efibootmgr", silent=True).returncode
    if "rocky" in SystemInformationRelease.distribution and is_efi not in (None, 0):
        if os.path.islink(grubenv_file):
            target_grubenv_file = os.path.realpath(grubenv_file)

            os.remove(grubenv_file)
            shutil.copy2(target_grubenv_file, grubenv_file)


@pytest.fixture()
def environment_variables(request):
    """
    Fixture.
    Set and unset required environment variables.
    Usage:
    @pytest.mark.parametrize("environment_variables", ["CONVERT2RHEL_UNSUPPORTED"], indirect=True)
    @pytest.mark.parametrize("environment_variables", [["FIRST", "TEST", "EXECUTION"], ["SECOND", "TEST", "EXECUTION"]], indirect=True)
    """

    if hasattr(request, "param"):
        env_vars = request.param
        if not isinstance(env_vars, list):
            env_vars = [env_vars]

        for e in env_vars:
            os.environ[e] = "1"

        yield

        for e in env_vars:
            os.environ.pop(e, None)
            assert e not in os.environ, f"The removal of the environment variable - '{e}' failed"


@pytest.fixture(scope="function")
def outdated_kernel(shell, hybrid_rocky_image):
    """
    Install an older version of kernel and let the system boot to it.
    """
    # If the fixture gets executed after second `tmt-reboot` (after cleanup of a test) then
    # do not trigger test again by yielding.
    # Note that we cannot just run `return` command as this fixture require to have
    # `yield` call in every situation. That's why calling `pytest.skip`.
    if int(os.environ["TMT_REBOOT_COUNT"]) > 1:
        pytest.skip("The `kernel` fixture has already run.")

    if os.environ["TMT_REBOOT_COUNT"] == "0":
        # There won't be much changes for EL 7 packages anymore
        # We can hardcode this then
        # The release part differs a bit on CentOS and Oracle,
        # so going with wildcard asterisk to generalize
        if SystemInformationRelease.version.major == 7:
            older_kernel = "kernel-3.10.0-1160.118*"
            assert shell(f"yum install -y {older_kernel}").returncode == 0

        # Verify that there is multiple kernels installed
        if int(shell("rpm -q kernel | wc -l").output.strip()) > 1:
            # We don't need to do anything at this point
            # The whole setup needed happens after
            pass

        # Try to downgrade kernel version, if there is not multiple versions installed already.
        # If the kernel downgrade fails, assume it's not possible and try to install from
        # an older repo. This should only happen when Alma and Rocky has just landed on
        # a fresh minor version.
        elif shell("yum downgrade kernel -y").returncode == 1:
            # Assuming this can only happen with Alma and Rocky we'll try to install an older kernel
            # from a previous minor version.
            # For that we need to use the vault url and bump te current minor down one version.
            major_ver = SystemInformationRelease.version.major
            minor_ver = SystemInformationRelease.version.minor
            previous_minor_ver = minor_ver - 1
            if minor_ver <= 0:
                # In case we're on a x.0 version, there is not an older repo to work with.
                # Skip the test if so
                pytest.skip("There is no older kernel to install for this system.")
            releasever = ".".join((str(major_ver), str(previous_minor_ver)))
            old_repo = None
            if SystemInformationRelease.distribution == "alma":
                old_repo = f"https://vault.almalinux.org/{releasever}/BaseOS/x86_64/os/"
            elif SystemInformationRelease.distribution == "rocky":
                old_repo = f"https://dl.rockylinux.org/vault/rocky/{releasever}/BaseOS/x86_64/os/"
            else:
                pytest.fail("This should not happen.")
            # Install the kernel from the url
            shell(f"yum install kernel -y --repofromurl 'oldrepo,{old_repo}'")

        # Get the oldest kernel version
        oldest_kernel = shell("rpm -q kernel | rpmdev-sort | awk -F'kernel-' '{print $2}' | head -1").output.strip()
        # Get the full kernel title from grub to set later
        default_kernel_title = get_full_kernel_title(shell, kernel=oldest_kernel)
        workaround_grub_setup(shell)
        # Set the older kernel as default
        shell(f"grub2-set-default '{default_kernel_title.strip()}'")
        shell("grub2-mkconfig -o /boot/grub2/grub.cfg")

        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # We need to get the name of the latest kernel
        # present in the repositories

        # Get the name of the latest kernel
        latest_kernel = shell(
            "repoquery --quiet --qf '%{BUILDTIME}\t%{VERSION}-%{RELEASE}' kernel 2>/dev/null | tail -n 1 | awk '{printf $NF}'"
        ).output

        full_boot_kernel_title = get_full_kernel_title(shell, kernel=latest_kernel)

        # Set the latest kernel as the one we want to reboot to
        shell(f"grub2-set-default '{full_boot_kernel_title.strip()}'")
        shell("grub2-mkconfig -o /boot/grub2/grub.cfg")

        # Reboot after clean-up
        shell("tmt-reboot -t 600")


@pytest.fixture()
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
    exclude = [""]
    if hasattr(request, "param"):
        exclude = request.param
        print(">>> Using parametrized packages requested in the fixture.")
    # /etc/yum.conf is either a standalone config file for yum, on EL7 systems
    # or a symlink to the /etc/dnf/dnf.conf config file on dnf based systems
    # we want to be able to restore this state after the test finishes.
    yum_configs_all = ["/etc/yum.conf", "/etc/dnf/dnf.conf"]
    # figure out which config files are on the system
    yum_configs = [conf for conf in yum_configs_all if os.path.exists(conf)]
    backup_dir = os.path.join(backup_directory, "yumconf")
    shell(f"mkdir -v {backup_dir}")

    yum_conf = yum_configs_all[0]
    dnf_conf = yum_configs_all[1]
    yum_conf_bak = os.path.join(backup_dir, os.path.basename(yum_conf))
    dnf_conf_bak = os.path.join(backup_dir, os.path.basename(dnf_conf))
    # if there are both config files on the system, we can assume, that /etc/yum.conf
    # is just a symlink to /etc/dnf/dnf.conf, and we work with just the regular file
    if len(yum_configs) == 2:
        modified_config = dnf_conf
    else:
        modified_config = yum_conf

    assert shell(f"cp -v {modified_config} {backup_dir}").returncode == 0

    config = configparser.ConfigParser()
    config.read(modified_config)

    pkgs_to_exclude = " ".join(exclude)
    # If there is already an `exclude` section, append to the existing value
    if config.has_option("main", "exclude"):
        pre_existing_value = config.get("main", "exclude")
        config.set("main", "exclude", f"{pre_existing_value} {pkgs_to_exclude}")
    else:
        config.set("main", "exclude", pkgs_to_exclude)

    with open(modified_config, "w") as configfile:
        config.write(configfile, space_around_delimiters=False)

    assert config.has_option("main", "exclude")
    assert all(pkg in config.get("main", "exclude") for pkg in exclude)

    yield

    # Clean up only for non-destrucive tests
    # We need to keep the yum.conf in the descructive tests, since restoring the original
    # version has the discoverpkg option set to centos|oracle|alma|rocky-release trying to read
    # the system information from the then non-existent file
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        for yum_config in yum_configs:
            # Remove the files first in case we get some pollution by convert2rhel
            shell(f"rm -f {yum_config}")

        # if there are both config files on the system prior, restore /etc/dnf/dnf.conf
        # file and re-create the /etc/yum.conf symlink
        if len(yum_configs) == 2:
            assert shell(f"mv {dnf_conf_bak} {dnf_conf}").returncode == 0
            Path(yum_conf).symlink_to(dnf_conf)
        else:
            assert shell(f"mv {yum_conf_bak} {yum_conf}").returncode == 0


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

    if int(os.environ["TMT_REBOOT_COUNT"]) > 0 and os.path.exists(backup_path):
        print(f"\nBackup path {backup_path} is already created. Skipping for now.")
    else:
        assert shell(f"mkdir {backup_path}").returncode == 0

    yield backup_path

    shell(f"rm -rf {backup_path}")


class Satellite:
    def __init__(self, key=SYSTEM_RELEASE_ENV):
        self.shell = live_shell()
        # Key on which upon the command is selected
        self.key = key
        # File containing registration commands
        self._sat_reg_commands = dotenv_values("/var/tmp/.env_sat_reg")
        self._sat_script_location = "/var/tmp/register_to_satellite.sh"
        self.subman = SubscriptionManager()

    def get_satellite_curl_command(self):
        """
        Get the Satellite registration command for the respective system.
        """
        if not self._sat_reg_commands:
            pytest.fail(
                f"The {self._sat_reg_file} either not found or empty.\
                It is required for the satellite conversion to work."
            )

        return self._sat_reg_commands.get(self.key)

    def _curl_the_satellite_script(self, curl_command):
        assert (
            self.shell(f"{curl_command} -o {self._sat_script_location}", silent=True).returncode == 0
        ), "Failed to curl the satellite script to the machine."

        # [danmyway] This is just a mitigation of rhn-client-tools pkg obsoleting subscription-manager during upgrade
        # TODO remove when https://github.com/theforeman/foreman/pull/10280 gets merged and or foreman 3.12 is out
        # Should be around November 2024
        if "oracle-7.9" in SystemInformationRelease.system_release:
            self.shell(
                fr"sed -i 's/$PKG_MANAGER_UPGRADE subscription-manager/& --setopt=exclude=rhn-client-tools/' {self._sat_script_location}"
            )

    def _run_satellite_reg_script(self):
        assert (
            self.shell(f"chmod +x {self._sat_script_location} && /bin/bash {self._sat_script_location}").returncode == 0
        ), "Falied to run the satellite registration script."

    def register(self):
        curl_command = self.get_satellite_curl_command()

        # Subscription-manager is not in Oracle repositories so we have to add
        # our own client-tools-repo with subscription-manager package.
        if "oracle" in SYSTEM_RELEASE_ENV:
            self.subman.add_keys_and_certificates()
            self.subman.add_client_tools_repo()

        # Make sure it returned some value, otherwise it will fail.
        assert curl_command, "The registration command is empty."

        # Curl the Satellite registration script silently
        self._curl_the_satellite_script(curl_command)

        # Make the script executable and run the registration
        self._run_satellite_reg_script()

        ### This is a workaround which might be removed, when we enable the Satellite repositories by default
        repos_to_enable = self.shell(
            "subscription-manager repos --list | grep '^Repo ID:' | awk '{print $3}'"
        ).output.split()
        for repo in repos_to_enable:
            self.shell(f"subscription-manager repos --enable {repo}")

    def unregister(self):
        """
        Remove the subman packages installed by the registration script
        """
        self.subman.clean_up()


@pytest.fixture()
def fixture_satellite(request):
    """
    Fixture.
    Register the system to the Satellite server. Wrapper around satellite class and its methods.
    Can be parametrized with requesting a different key from the SAT_REG_FILE("/var/tmp/.env_sat_reg"):
    @pytest.mark.parametrize("fixture_satellite", ["DIFFERENT_KEY"], indirect=True)
    """
    sat_curl_command_key = SYSTEM_RELEASE_ENV
    if hasattr(request, "param"):
        sat_curl_command_key = request.param
        print(">>> Using parametrized curl command requested in the fixture.")
    satellite = Satellite(key=sat_curl_command_key)

    satellite.register()

    yield

    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        satellite.unregister()


#### Common functions ####
def load_json_schema(path):
    """Load the JSON schema from the system."""
    assert os.path.exists(path)

    with open(path, mode="r") as handler:
        return json.load(handler)


def get_full_kernel_title(shell, kernel=None):
    """
    Helper function.
    Get the full kernel boot entry title.
    :param kernel: kernel pacakge VRA (version-release.architecture)
    :type kernel: str
    :param shell: Live shell fixture

    :return: The full boot entry title for the given kernel.
    :rtype: str
    """
    if not kernel:
        raise ValueError("The kernel argument is probably empty")
    # Get the full name of the kernel (ignore rescue kernels)
    full_title = shell(
        f'grubby --info ALL | grep "title=.*{kernel}" | grep -vi "rescue" | tr -d \'"\' | sed \'s/title=//\''
    ).output.strip()

    return full_title


#### Workaround fixtures ####
@pytest.fixture(autouse=True)
def workaround_missing_os_release_package(shell):
    # TODO(danmyway) remove when/if the issue gets fixed
    """
    Fixture to workaround issues with missing `*-linux-release`
    package, after incomplete rollback.
    """
    # run only after the test finishes
    yield

    os_to_pkg_mapping = {
        "centos-7": ["centos-release"],
        "centos-8": ["centos-linux-release"],
        "almalinux": ["almalinux-release"],
        "rocky": ["rocky-release"],
        "oracle": ["oraclelinux-release"],
        "stream": ["centos-stream-release"],
    }

    # Run only for non-destructive tests.
    # The envar is added by tmt and is defined in main.fmf for non-destructive tests.
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        os_name = SystemInformationRelease.distribution
        os_ver = SystemInformationRelease.version.major
        if "centos" in os_name:
            os_key = f"{os_name}-{os_ver}"
        else:
            os_key = os_name

        system_release_pkgs = os_to_pkg_mapping.get(os_key)

        if os_key == "oracle":
            system_release_pkgs.append(f"oraclelinux-release-el{SystemInformationRelease.version.major}")

        for pkg in system_release_pkgs:
            installed = shell(f"rpm -q {pkg}").returncode
            if installed == 1:
                shell(f"yum install -y --releasever={os_ver} {pkg}")

        # Since we try to mitigate any damage caused by the incomplete rollback
        # try to update the system, in case anything got downgraded
        print("TESTS >>> Updating the system.")
        shell("yum update -y", silent=True)


@pytest.fixture(scope="session", autouse=True)
def workaround_remove_uek():
    """
    Fixture to remove the Unbreakable Enterprise Kernel package.
    The package might cause dependency issues.
    Reference issue https://issues.redhat.com/browse/RHELC-1544
    """
    if SystemInformationRelease.distribution == "oracle":
        subprocess.run(
            ["yum", "remove", "-y", "kernel-uek"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    yield


def workaround_grub_setup(shell):
    """
    Workaround.
    /usr/lib/kernel/install.d/99-grub-mkconfig.install sets DISABLE_BLS=true when the hypervisor is xen
    Due to all AWS images having xen type hypervisor, GRUB_ENABLE_BLSCFG is set to false as well
    as a consequence. We need GRUB_ENABLE_BLSCFG set to true to be able to boot into different kernel
    than the latest.
    """
    if SystemInformationRelease.version.major == 9:
        print("TESTS >>> Setting grub default to correct values.")
        shell(r"sed -i 's/^\s*GRUB_ENABLE_BLSCFG\s*=.*/GRUB_ENABLE_BLSCFG=true/g' /etc/default/grub")


@pytest.fixture(autouse=True)
def workaround_keep_centos_pointed_to_vault(shell):
    """
    Fixture.
    In some rare cases we (re)install the centos-release package.
    This overwrites the repofiles to its default state using mirrorlist instead of vault
    which won't work since the EOL.
    Make sure the repositories are pointed to the vault to keep the system usable.
    """
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ and "centos" in SystemInformationRelease.distribution:
        sed_repos_to_vault = r'sed -i -e "s|^\(mirrorlist=.*\)|#\1|" -e "s|^#baseurl=http://mirror\(.*\)|baseurl=http://vault\1|" /etc/yum.repos.d/CentOS-*'
        print("TESTS >>> Resetting the repos to vault")
        shell(sed_repos_to_vault, silent=True)
