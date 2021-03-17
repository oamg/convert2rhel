import logging
import os
import re
import subprocess


try:
    from subprocess import check_output  # pylint: disable=no-name-in-module
except ImportError:
    # python2.6 doesn't have this
    def check_output(command):
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
        ).communicate()[0]


from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)

_KEY_KERNEL_CORE = "kernel-core"
_KEY_KERNEL_DEBUG_CORE = "kernel-debug-core"

KERNEL_REPO_RE = re.compile(
    "kernel-(?:debug-)?core-0:(?P<version>(\d+\.)*(\d+)-(\d+\.)*(\d+)).el.+"
)
KERNEL_REPO_VER_SPLIT_RE = re.compile("\D+")


def get_host_kmods():
    try:
        # TODO make it work with utils.run_subprocess (now fails)
        kmod_str = check_output(
            'find /lib/modules/"$(uname -r)" -name "*.ko.xz"',
            shell=True,
        ).decode()
        assert kmod_str
    except (subprocess.CalledProcessError, AssertionError):
        logger.critical("Can't get list of kernel modules.")
    else:
        return set(
            os.path.split(path)[-1] for path in kmod_str.rstrip("\n").split()
        )


def _repos_version_key(pkg_name):
    try:
        rpm_version = KERNEL_REPO_RE.search(pkg_name).group("version")
    except AttributeError:
        raise NotImplementedError(
            "Unexpected package:\n%s\n is a source of kernel modules."
            % pkg_name
        )
    else:
        return tuple(map(int, KERNEL_REPO_VER_SPLIT_RE.split(rpm_version)))


def get_most_recent_unique_kernel_pkgs(pkgs):
    """Return the most recent versions of kernel packages.

    When we do scanning of kernel modules provided by kernel packages,
    it is expensive to check each kernel pkg. Considering the fact,
    that each new kernel pkg do not deprecate kernel modules we select only
    the most recent ones.

    :type pkgs: Iterable[str]
    """
    kernel_core_pkgs = filter(
        lambda pkg_name: pkg_name.startswith(_KEY_KERNEL_CORE), pkgs
    )
    kernel_debug_core_pkgs = filter(
        lambda pkg_name: pkg_name.startswith(_KEY_KERNEL_DEBUG_CORE), pkgs
    )

    return (
        max(kernel_core_pkgs, key=_repos_version_key),
        max(kernel_debug_core_pkgs, key=_repos_version_key),
    )


def get_rhel_supported_kmods():
    """Return set of target RHEL supported kernel modules."""
    system_info.resolve_system_info()
    baseos_repoid, appstream_repoid = system_info.default_rhsm_repoids
    kmod_repos_str = run_subprocess(
        (
            "repoquery "
            "--repoid={baseos_repoid} "
            "--repoid={appstream_repoid} "
            "-f /lib/modules"
        ).format(
            baseos_repoid=baseos_repoid, appstream_repoid=appstream_repoid
        )
    ).decode()  # type: str
    kmod_pkgs = get_most_recent_unique_kernel_pkgs(
        kmod_repos_str.rstrip("\n").split()
    )
    rhel_kmods = set()
    for kmod_pkg in kmod_pkgs:
        rhel_kmods_str = run_subprocess(
            (
                "repoquery "
                "--repoid={baseos_repoid} "
                "--repoid={appstream_repoid} "
                "-l {pkg}"
            ).format(
                baseos_repoid=baseos_repoid,
                appstream_repoid=appstream_repoid,
                pkg=kmod_pkg,
            )
        ).decode()  # type: str
        rhel_kmods.update(
            set(
                os.path.split(kmod_path)[-1]
                for kmod_path in filter(
                    lambda path: path.endswith("ko.xz"),
                    rhel_kmods_str.rstrip("\n").split(),
                )
            )
        )
    return rhel_kmods


def ensure_compatibility_of_kmods():
    """Ensure if the host kernel modules are compatible with RHEL."""
    host_kmods = get_host_kmods()
    rhel_supported_kmods = get_rhel_supported_kmods()
    if not host_kmods.issubset(rhel_supported_kmods):
        logger.critical(
            "The following kernel modules are not supported"
            "on RHEL:\n %s" % "\n".join(host_kmods - rhel_supported_kmods)
        )
    else:
        logger.debug("Kernel modules are compatible.")


def pre_ponr():
    ensure_compatibility_of_kmods()
