import sys

import pytest


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
        import pathlib    # pylint: disable=import-error
    return pathlib.Path(__file__).parents[2]
