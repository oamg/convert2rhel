__metaclass__ = type

import os
import sys

import pytest
import six

from convert2rhel import backup, pkgmanager, redhatrelease, systeminfo, toolopts, utils
from convert2rhel.backup.certs import RestorablePEMCert
from convert2rhel.logger import add_file_handler, setup_logger_handler
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import MinimalRestorable


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


# We are injecting a instance of `mock.Mock()` for `Depsolve` class and
# `callback` module, as when we run the tests under CentOS 7, it fails by saying
# that `pkgmanager.callback.Depsolve` can't be imported as it is an import from
# DNF, not YUM.
# This implies in us mocking those targets on Python 2.7, as DNF is only
# available on Python 3+.
# Not a perfect solution, but a needed one since we are inheriting this
# class/module in the dnf handler module.
if sys.version_info[:2] <= (2, 7):
    pkgmanager.Depsolve = mock.Mock()
    pkgmanager.callback = mock.Mock()


@pytest.fixture(scope="session")
def is_py2():
    return sys.version_info[:2] <= (2, 7)


@pytest.fixture()
def read_std(capsys, is_py2):
    """Multipython compatible, modified version of capsys.

    Example:
    >>> def test_example(read_std):
    >>>     import sys
    >>>     sys.stdout.write("stdout")
    >>>     sys.stderr.write("stderr")
    >>>     std_out, std_err = read_std()
    >>>     assert "stdout" in std_out
    >>>     assert "stderr" in std_err

    :returns: Callable[Tuple[str, str]] Factory that reads the stdouterr and
        returns captured stdout and stderr strings
    """

    def factory():
        stdouterr = capsys.readouterr()
        if is_py2:
            return stdouterr
        else:
            return stdouterr.out, stdouterr.err

    return factory


@pytest.fixture()
def pkg_root():
    """Return the pathlib.Path of the convert2rhel package root."""
    six.add_move(six.MovedModule("pathlib", "pathlib2", "pathlib"))
    from six.moves import pathlib

    return pathlib.Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def setup_logger(tmpdir, request):
    # This makes it so we can skip this using @pytest.mark.noautofixtures
    if "noautofixtures" in request.keywords:
        return
    setup_logger_handler()
    add_file_handler(log_name="convert2rhel", log_dir=str(tmpdir))


@pytest.fixture
def system_cert_with_target_path(monkeypatch, tmpdir, request):
    """
    Create a single RestorablePEMCert backed by a temp file.

    Use it in unit tests when you need a RestorablePEMCert that has a real file backing it.

    The cert to be copied is the RHEL8 cert, 479.pem.
    """
    pem_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "../data/8/x86_64/rhel-certs"))

    sys_cert = RestorablePEMCert(pem_dir, str(tmpdir))
    return sys_cert


@pytest.fixture
def sys_path():
    real_sys_path = sys.path
    sys.path = sys.path[:]
    yield sys.path
    sys.path = real_sys_path


@pytest.fixture
def global_tool_opts(monkeypatch):
    local_tool_opts = toolopts.ToolOpts()
    monkeypatch.setattr(toolopts, "tool_opts", local_tool_opts)
    return local_tool_opts


@pytest.fixture
def global_system_info(monkeypatch):
    local_system_info = systeminfo.SystemInfo()
    monkeypatch.setattr(systeminfo, "system_info", system_info)
    return local_system_info


@pytest.fixture
def global_backup_control(monkeypatch):
    local_backup_control = backup.BackupController()
    monkeypatch.setattr(backup, "backup_control", local_backup_control)
    return local_backup_control


@pytest.fixture()
def pretend_os(request, pkg_root, monkeypatch):
    """Parametric fixture to pretend to be one of the available OSes for conversion.

    See https://docs.pytest.org/en/6.2.x/example/parametrize.html#indirect-parametrization
    for more information.

    Fixture parameters are:
        system_version - i.e. "7.9.9"
        system_name - i.e. "CentOS Linux"

    Examples:

    >>> # low level mode
    >>> @pytest.mark.parametrize(
    >>>     "pretend_os",
    >>>     (
    >>>         ("7.9.1111", "CentOS Linux"),
    >>>         ("7.9.1111", "Oracle Linux Server"),
    >>>         ("8.4.1111", "CentOS Linux"),
    >>>         ("8.4.1111", "Oracle Linux Server"),
    >>>     ),
    >>>     indirect=True,
    >>> )
    >>> def example_test(pretend_os):
    >>>     # Will run 4 tests for each of specified systems.
    >>>     pass


    >>> # using the shortcut
    >>> @all_systems
    >>> def example_test(pretend_os):
    >>>     # Will do the same.
    >>>     pass


    >>> @centos8
    >>> def example_test(pretend_os):
    >>>     # Will pretend CentOS 8.
    >>>     pass


    >>> @pytest.mark.parametrize(
    >>>     "param",
    >>>     (
    >>>         ("param_value1",),
    >>>         ("param_value2",),
    >>>     ),
    >>> )
    >>> @all_systems
    >>> def example_test(pretend_os):
    >>>     # Will run 8 tests.

    >>>     # for each of 4 systems it will run the test with each param value.
    >>>     pass

    """
    system_version, system_name = request.param
    system_version_major, system_version_minor, _ = system_version.split(".")

    monkeypatch.setattr(
        utils,
        "DATA_DIR",
        value=str(pkg_root / ("convert2rhel/data/%s/x86_64/" % system_version_major)),
    )
    monkeypatch.setattr(
        redhatrelease,
        "get_system_release_filepath",
        value=lambda: "/etc/system-release",
    )
    monkeypatch.setattr(
        utils,
        "get_file_content",
        value=lambda _: "%s release %s" % (system_name, system_version),
    )
    monkeypatch.setattr(
        system_info,
        "_get_architecture",
        value=lambda: "x86_64",
    )
    monkeypatch.setattr(
        system_info,
        "_check_internet_access",
        value=lambda: True,
    )
    tool_opts.no_rpm_va = True

    # We can't depend on a test environment (containers) having an init system so we have to
    # disable probing for the right value by hardcoding an anwer
    monkeypatch.setattr(
        system_info,
        "_is_dbus_running",
        value=lambda: True,
    )

    # We won't depend on a test environment having an internet connection, so we
    # need to mock _check_internet_access() for all tests
    monkeypatch.setattr(
        system_info,
        "_check_internet_access",
        value=lambda: True,
    )

    system_info.resolve_system_info()


all_systems = pytest.mark.parametrize(
    "pretend_os",
    (
        ("7.9.1111", "CentOS Linux"),
        ("7.9.1111", "Oracle Linux Server"),
        ("8.5.1111", "CentOS Linux"),
        ("8.6.1111", "Oracle Linux Server"),
    ),
    indirect=True,
)
centos7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "CentOS Linux"),),
    indirect=True,
)
centos8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.5.1111", "CentOS Linux"),),
    indirect=True,
)
oracle7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "Oracle Linux Server"),),
    indirect=True,
)
oracle8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.6.1111", "Oracle Linux Server"),),
    indirect=True,
)


@pytest.fixture
def restorable():
    return MinimalRestorable()
