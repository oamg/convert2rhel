import sys

import pytest

from convert2rhel import redhatrelease, utils
from convert2rhel.logger import initialize_logger
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


@pytest.fixture(scope="session")
def is_py26():
    return sys.version_info[:2] == (2, 6)


@pytest.fixture(scope="session")
def is_py2():
    return sys.version_info[:2] <= (2, 7)


@pytest.fixture()
def tmpdir(tmpdir, is_py2):
    """Make tmpdir type str for py26.

    Origin LocalPath object is not supported in python26 for os.path.isdir.
    We're using this method when do a logger setup.
    """
    if is_py2:
        return str(tmpdir)
    else:
        return tmpdir


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
def pkg_root(is_py2):
    """Return the pathlib.Path of the convert2rhel package root."""
    if is_py2:
        import pathlib2 as pathlib  # pylint: disable=import-error
    else:
        import pathlib  # pylint: disable=import-error
    return pathlib.Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def setup_logger(tmpdir):
    initialize_logger(log_name="convert2rhel", log_dir=tmpdir)


@pytest.fixture()
def pretend_os(request, pkg_root, monkeypatch):
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
    tool_opts.no_rpm_va = True
    system_info.resolve_system_info()


all_systems = pytest.mark.parametrize(
    "pretend_os",
    (
        ("7.9.1111", "CentOS Linux"),
        ("7.9.1111", "Oracle Linux Server"),
        ("8.4.1111", "CentOS Linux"),
        ("8.4.1111", "Oracle Linux Server"),
    ),
    indirect=True,
)
centos8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.4.1111", "CentOS Linux"),),
    indirect=True,
)
centos7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "CentOS Linux"),),
    indirect=True,
)
oracle8 = pytest.mark.parametrize(
    "pretend_os",
    (("8.4.1111", "Oracle Linux Server"),),
    indirect=True,
)
oracle7 = pytest.mark.parametrize(
    "pretend_os",
    (("7.9.1111", "Oracle Linux Server"),),
    indirect=True,
)
