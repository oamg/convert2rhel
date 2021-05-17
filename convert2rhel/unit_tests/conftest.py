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


def _replace_data_dir_base(system_version_num):
    """Factory function serves as a base to mokeypatch utils.DATA_DIR."""

    def fixture(monkeypatch, pkg_root):
        monkeypatch.setattr(
            utils,
            "DATA_DIR",
            value=str(pkg_root / ("convert2rhel/data/%s/x86_64/" % system_version_num)),
        )

    return fixture


_replace_data_dir_for_centos8 = pytest.fixture(_replace_data_dir_base("8"))
_replace_data_dir_for_centos7 = pytest.fixture(_replace_data_dir_base("7"))


def _pretend_fixture_base(monkeypatch, system_release_version):
    """Apply common logic in pretend_{os_name} fixtures."""

    monkeypatch.setattr(
        redhatrelease,
        "get_system_release_filepath",
        value=lambda: "/etc/system-release",
    )
    monkeypatch.setattr(
        utils,
        "get_file_content",
        value=lambda _: "CentOS Linux release %s" % system_release_version,
    )
    tool_opts.no_rpm_va = True
    system_info.resolve_system_info()


def _pretend_centos_base(system_release_version):
    """Factory function serves as a base to pretend_{os} fixtures."""

    def fixture_centos7(monkeypatch, _replace_data_dir_for_centos7):
        _pretend_fixture_base(monkeypatch, system_release_version)

    def fixture_centos8(monkeypatch, _replace_data_dir_for_centos8):
        _pretend_fixture_base(monkeypatch, system_release_version)

    release2data_dir_relations = {
        "8.3.2011": fixture_centos8,
        "7.9.2009": fixture_centos7,
    }

    try:
        return release2data_dir_relations[system_release_version]
    except KeyError:
        raise KeyError(
            "Unknown system release version %s.\n"
            "Available are: %s" % (system_release_version, " ".join(release2data_dir_relations)),
        )


pretend_centos8 = pytest.fixture(_pretend_centos_base("8.3.2011"))
pretend_centos7 = pytest.fixture(_pretend_centos_base("7.9.2009"))
