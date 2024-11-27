import json
import os
import re

from collections import namedtuple

import pytest

from test_helpers.vars import SYSTEM_RELEASE_ENV


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

        # Check if the release is a EUS candidate
        is_eus = False
        if (
            version.major in (8, 9)
            and version.minor in (2, 4, 6, 8)
            and distribution != "oracle"
            and "latest" not in SYSTEM_RELEASE_ENV
        ):
            is_eus = True


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


def get_custom_repos_names():
    """
    Helper function.
    Returns a list of correct repo names used on RHEL respecting major/eus system version.
    """
    system_version = SystemInformationRelease.version

    # Default RHEL-7 repositories
    repos = ["rhel-7-server-rpms", "rhel-7-server-optional-rpms", "rhel-7-server-extras-rpms"]

    if system_version.major >= 8:
        if SystemInformationRelease.is_eus:
            repos = [
                f"rhel-{system_version.major}-for-x86_64-baseos-eus-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-eus-rpms",
            ]
        else:
            repos = [
                f"rhel-{system_version.major}-for-x86_64-baseos-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-rpms",
            ]
    return repos


def get_log_file_data():
    """
    Helper fixture.
    Reads and returns data from the convert2rhel.log file.
    Mainly used for after conversion checks, where we match required strings to the log output.
    """
    convert2rhel_log_file = "/var/log/convert2rhel/convert2rhel.log"

    assert os.path.exists(convert2rhel_log_file), "The c2r log file does not exits."

    with open(convert2rhel_log_file, "r") as logfile:
        log_data = logfile.read()

        return log_data
