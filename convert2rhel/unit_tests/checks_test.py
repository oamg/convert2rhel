import subprocess
import sys

import pytest

from convert2rhel import checks
from convert2rhel.checks import (
    ensure_compatibility_of_kmods,
    get_host_kmods,
    get_rhel_supported_kmods,
    pre_ponr,
)
from convert2rhel.utils import run_subprocess


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


HOST_MODULES_STUB_GOOD = (
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
)
HOST_MODULES_STUB_BAD = (
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/e.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko.xz\n"
)
REPOQUERY_F_STUB = (
    b"kernel-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    b"kernel-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
    b"kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    b"kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
)
REPOQUERY_L_STUB_GOOD = (
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko\n"
)
REPOQUERY_L_STUB_BAD = (
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/e.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko.xz\n"
    b"/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko\n"
)


def test_pre_ponr(monkeypatch):
    ensure_compatibility_of_kmods_mock = mock.Mock()
    monkeypatch.setattr(
        checks,
        "ensure_compatibility_of_kmods",
        value=ensure_compatibility_of_kmods_mock,
    )
    pre_ponr()
    ensure_compatibility_of_kmods_mock.assert_called_once()


@pytest.mark.parametrize(
    ("host_kmods",),
    (
        (HOST_MODULES_STUB_GOOD,),
        (HOST_MODULES_STUB_BAD,),
    ),
)
def test_ensure_compatibility_of_kmods(
    monkeypatch, pretend_centos8, caplog, host_kmods
):
    check_output_mock = mock.Mock(return_value=host_kmods)
    run_subprocess_mock = mock.Mock(side_effect=_run_subprocess_side_effect)
    monkeypatch.setattr(checks, "check_output", value=check_output_mock)
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if host_kmods == HOST_MODULES_STUB_BAD:
        with pytest.raises(SystemExit):
            ensure_compatibility_of_kmods()
    else:
        ensure_compatibility_of_kmods()
    if host_kmods == HOST_MODULES_STUB_GOOD:
        assert "Kernel modules are compatible" in caplog.records[-1].message
    else:
        assert (
            "Kernel modules are compatible" not in caplog.records[-1].message
        )


@pytest.mark.parametrize(
    ("check_output_mock", "exp_res"),
    (
        (
            mock.Mock(return_value=HOST_MODULES_STUB_GOOD),
            set(("a.ko.xz", "b.ko.xz", "c.ko.xz")),
        ),
        (
            mock.Mock(side_effect=AssertionError()),
            None,
        ),
        (
            mock.Mock(
                side_effect=subprocess.CalledProcessError(returncode=1, cmd="")
            ),
            None,
        ),
    ),
)
def test_get_host_kmods(
    tmpdir, monkeypatch, caplog, check_output_mock, exp_res
):
    monkeypatch.setattr(
        checks,
        "check_output",
        value=check_output_mock,
    )
    if exp_res:
        assert get_host_kmods() == exp_res
    else:
        with pytest.raises(SystemExit):
            get_host_kmods()
        assert (
            "Can't get list of kernel modules." in caplog.records[-1].message
        )


def _run_subprocess_side_effect(*args, **kwargs):
    if "repoquery" in args[0] and " -f " in args[0]:
        return REPOQUERY_F_STUB
    if "repoquery" in args[0] and " -l " in args[0]:
        return REPOQUERY_L_STUB_GOOD
    else:
        return run_subprocess(*args, **kwargs)


def test_get_rhel_supported_kmods(monkeypatch, pretend_centos8):
    run_subprocess_mock = mock.Mock(side_effect=_run_subprocess_side_effect)
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    assert get_rhel_supported_kmods() == set(("a.ko.xz", "b.ko.xz", "c.ko.xz"))
