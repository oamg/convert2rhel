import logging
import sys

import pytest
import six

from convert2rhel import backup, cert, redhatrelease, systeminfo, toolopts, utils
from convert2rhel.logger import setup_logger_handler
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import get_pytest_marker


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module

try:
    from pytest_catchlog import CompatLogCaptureFixture

    class SubCompatLogCaptureFixture(CompatLogCaptureFixture):
        @property
        def messages(self):
            return [r.getMessage() for r in self.records]

    @pytest.fixture
    def caplog(request):
        """Access and control log capturing.
        Captured logs are available through the following properties/methods::
        * caplog.messages        -> list of format-interpolated log messages
        * caplog.text            -> string containing formatted log output
        * caplog.records         -> list of logging.LogRecord instances
        * caplog.record_tuples   -> list of (logger_name, level, message) tuples
        * caplog.clear()         -> clear captured records and formatted log output string
        """
        return SubCompatLogCaptureFixture(request.node)

except ImportError:
    pass


@pytest.fixture(scope="session")
def is_py26():
    return sys.version_info[:2] == (2, 6)


@pytest.fixture(scope="session")
def is_py2():
    return sys.version_info[:2] <= (2, 7)


@pytest.fixture
def clear_loggers():
    """
    Remove handlers from the loggers.

    If logger handlers are created while we are using capsys or capfd, then
    the logger handlers get created with pytest's capture.  If pytest's
    capture feature is disabled later, the logger handlers will get errors
    trying to write to a closed file.  This is this issue:

        https://github.com/pytest-dev/pytest/issues/5502

    In our unittests, there are some tests that use pexpect that have to
    disable pytest's capture otherwise pexpect-2.3 will malfunction.  The
    combination of these two things causes logging calls during the utils
    tests to complain that they are trying to log to a closed file handle.

    Adding this fixture to any unit test which both uses capsys/capfd and
    creates the logger handlers (by calling
    `convert2rhel.logger.setup_logger_handler()`) fixes the issue.  The
    fixture works by removing the handlers that `setup_logger_handler()`
    (actually, all of the handlers) created when the test completes.
    """
    # Nothing to do in setup
    yield
    # In teardown, we clear all the logger handlers.
    loggers = logging.Logger.manager.loggerDict.values()
    for logger in loggers:
        if not hasattr(logger, "handlers"):
            continue
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)


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
def setup_logger(tmpdir):
    setup_logger_handler(log_name="convert2rhel", log_dir=str(tmpdir))


@pytest.fixture
def system_cert_with_target_path(monkeypatch, tmpdir, request):
    """
    Create a single SystemCert backed by a temp file.

    Use it in unit tests when you need a SystemCert that has a real file backing it.

    You may use a custom pytest.mark named cert_filename to use a specific file name in the temp directory.
    If you don't the file name will be arbitrary.

    We use this mark instead of using parametrize because parametrize is mainly used to run a test multiple times
    with diffrent data. For constant data, pytest recommends the use of custom markers.

    .. seealso::
        https://docs.pytest.org/en/7.1.x/how-to/fixtures.html#using-markers-to-pass-data-to-fixtures
    """
    cert_file_returns = get_pytest_marker(request, "cert_filename")

    if not cert_file_returns:
        temporary_filename = "filename"
    else:
        temporary_filename = cert_file_returns.args[0]

    tmp_file = tmpdir / temporary_filename

    monkeypatch.setattr(cert.SystemCert, "_get_cert", value=mock.Mock(return_value=("anything", "anything")))
    monkeypatch.setattr(cert.SystemCert, "_get_target_cert_path", value=mock.Mock(return_value=str(tmp_file)))

    sys_cert = cert.SystemCert()

    return sys_cert


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
        ("6.10.1111", "CentOS Linux"),
        ("6.10.1111", "Oracle Linux Server"),
        ("7.9.1111", "CentOS Linux"),
        ("7.9.1111", "Oracle Linux Server"),
        ("8.4.1111", "CentOS Linux"),
        ("8.4.1111", "Oracle Linux Server"),
    ),
    indirect=True,
)
centos6 = pytest.mark.parametrize(
    "pretend_os",
    (("6.10.1111", "CentOS Linux"),),
    indirect=True,
)
centos7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "CentOS Linux"),),
    indirect=True,
)
centos8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.4.1111", "CentOS Linux"),),
    indirect=True,
)
oracle6 = pytest.mark.parametrize(
    "pretend_os",
    (("6.10.1111", "Oracle Linux Server"),),
    indirect=True,
)
oracle7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "Oracle Linux Server"),),
    indirect=True,
)
oracle8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.4.1111", "Oracle Linux Server"),),
    indirect=True,
)


class TestPkgObj(object):
    class PkgObjHdr(object):
        def sprintf(self, *args, **kwargs):
            return "RSA/SHA256, Sun Feb  7 18:35:40 2016, Key ID 73bde98381b46521"

    hdr = PkgObjHdr()


def create_pkg_obj(
    name,
    epoch=0,
    version="",
    release="",
    arch="",
    packager=None,
    from_repo="",
    manager="yum",
    vendor=None,
):
    class DumbObj(object):
        pass

    obj = TestPkgObj()
    obj.yumdb_info = DumbObj()
    obj.name = name
    obj.epoch = obj.e = epoch
    obj.version = obj.v = version
    obj.release = obj.r = release
    obj.evr = version + "-" + release
    obj.arch = arch
    obj.packager = packager
    if vendor:
        obj.vendor = vendor
    if manager == "yum":
        if from_repo:
            obj.yumdb_info.from_repo = from_repo
    elif manager == "dnf":
        if from_repo:
            obj._from_repo = from_repo
        else:
            obj._from_repo = "@@System"
    return obj
