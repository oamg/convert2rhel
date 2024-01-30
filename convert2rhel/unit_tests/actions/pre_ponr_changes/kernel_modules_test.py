# Copyright(C) 2023 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__metaclass__ = type

import os
import re

import pytest
import six

from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.pre_ponr_changes import kernel_modules
from convert2rhel.actions.pre_ponr_changes.kernel_modules import (
    EnsureKernelModulesCompatibility,
    RHELKernelModuleNotFound,
)
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import assert_actions_result, run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos7, centos8
from convert2rhel.utils import run_subprocess


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


MODINFO_STUB = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
)

HOST_MODULES_STUB_GOOD = frozenset(
    (
        "kernel/lib/a.ko.xz",
        "kernel/lib/b.ko.xz",
        "kernel/lib/c.ko.xz",
    )
)
HOST_MODULES_STUB_BAD = frozenset(
    (
        "kernel/lib/d.ko.xz",
        "kernel/lib/e.ko.xz",
        "kernel/lib/f.ko.xz",
    )
)

REPOQUERY_F_STUB_GOOD = (
    "kernel-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
)
REPOQUERY_F_STUB_BAD = (
    "kernel-idontexpectyou-core-sdsdsd.ell8_3.x86_64\n"
    "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
)
REPOQUERY_L_STUB_GOOD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko\n"
)
REPOQUERY_L_STUB_BAD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/e.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko\n"
)


@pytest.fixture
def ensure_kernel_modules_compatibility_instance():
    return kernel_modules.EnsureKernelModulesCompatibility()


@pytest.mark.parametrize(
    (
        "host_kmods",
        "should_be_in_logs",
    ),
    (
        (
            HOST_MODULES_STUB_GOOD,
            "loaded kernel modules are available in RHEL",
        ),
    ),
)
@centos8
def test_ensure_compatibility_of_kmods(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    caplog,
    host_kmods,
    should_be_in_logs,
):
    monkeypatch.setattr(
        ensure_kernel_modules_compatibility_instance, "_get_loaded_kmods", mock.Mock(return_value=host_kmods)
    )
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("yum", "makecache"), ("", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    ensure_kernel_modules_compatibility_instance.run()
    assert_actions_result(ensure_kernel_modules_compatibility_instance, level="SUCCESS")

    assert should_be_in_logs in caplog.records[-1].message


@pytest.mark.parametrize(
    (
        "host_kmods",
        "repo_kmod_pkgs",
        "makecache_output",
        "error_id",
        "level",
    ),
    (
        (
            HOST_MODULES_STUB_BAD,
            REPOQUERY_F_STUB_GOOD,
            ("", 0),
            "UNSUPPORTED_KERNEL_MODULES",
            "OVERRIDABLE",
        ),
        (
            HOST_MODULES_STUB_BAD,
            REPOQUERY_F_STUB_GOOD,
            ("Insufficient space to run makecache", 1),
            "PROBLEM_WITH_PACKAGE_REPO",
            "ERROR",
        ),
        (
            HOST_MODULES_STUB_BAD,
            "",
            ("", 0),
            "NO_RHEL_KERNEL_MODULES_FOUND",
            "ERROR",
        ),
        (
            HOST_MODULES_STUB_BAD,
            "kernel-core-0:4.18.0-240.10.1.el8_3.x86_64\n" "kernel-core-0:4.19.0-240.10.1.el8_3.i486\n",
            ("", 0),
            "CANNOT_COMPARE_PACKAGE_VERSIONS",
            "ERROR",
        ),
    ),
)
@centos8
def test_ensure_compatibility_of_kmods_failure(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    caplog,
    host_kmods,
    repo_kmod_pkgs,
    makecache_output,
    error_id,
    level,
):
    monkeypatch.setattr(
        ensure_kernel_modules_compatibility_instance, "_get_loaded_kmods", mock.Mock(return_value=host_kmods)
    )
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("yum", "makecache"), makecache_output),
            (("repoquery", "-f"), (repo_kmod_pkgs, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    ensure_kernel_modules_compatibility_instance.run()
    assert_actions_result(ensure_kernel_modules_compatibility_instance, level=level, id=error_id)


@centos8
def test_ensure_compatibility_of_kmods_check_env_and_message(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    caplog,
):

    monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS": "1"})
    monkeypatch.setattr(
        ensure_kernel_modules_compatibility_instance, "_get_loaded_kmods", mock.Mock(return_value=HOST_MODULES_STUB_BAD)
    )
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("yum", "makecache"), ("", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    ensure_kernel_modules_compatibility_instance.run()
    should_be_in_logs = (
        ".*Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable."
        " We will continue the conversion with the following kernel modules unavailable in RHEL:.*"
    )
    assert re.match(pattern=should_be_in_logs, string=caplog.records[-1].message, flags=re.MULTILINE | re.DOTALL)
    # cannot assert exact action message contents as the kmods arrangement in the message is not static
    message = ensure_kernel_modules_compatibility_instance.messages[0]
    assert STATUS_CODE["WARNING"] == message.level
    assert "ALLOW_UNAVAILABLE_KERNEL_MODULES" == message.id
    assert "Did not perform the ensure kernel modules compatibility check" == message.title
    assert "Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable." in message.description
    assert "We will continue the conversion with the following kernel modules unavailable in RHEL:" in message.diagnosis


@pytest.mark.parametrize(
    (
        "unsupported_pkg",
        "msg_in_logs",
        "msg_not_in_logs",
        "exception",
    ),
    (
        # ff-memless specified to be ignored in the config, so no exception raised
        (
            "kernel/drivers/input/ff-memless.ko.xz",
            "loaded kernel modules are available in RHEL",
            "The following loaded kernel modules are not available in RHEL",
            False,
        ),
        (
            "kernel/drivers/input/other.ko.xz",
            "The following loaded kernel modules are not available in RHEL",
            None,
            True,
        ),
    ),
)
@centos7
def test_ensure_compatibility_of_kmods_excluded(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    caplog,
    unsupported_pkg,
    msg_in_logs,
    msg_not_in_logs,
    exception,
):
    monkeypatch.setattr(
        ensure_kernel_modules_compatibility_instance,
        "_get_loaded_kmods",
        mock.Mock(
            return_value=HOST_MODULES_STUB_GOOD | frozenset((unsupported_pkg,)),
        ),
    )
    get_unsupported_kmods_mocked = mock.Mock(wraps=ensure_kernel_modules_compatibility_instance._get_unsupported_kmods)
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("yum", "makecache"), ("", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(
        ensure_kernel_modules_compatibility_instance,
        "_get_unsupported_kmods",
        value=get_unsupported_kmods_mocked,
    )

    if exception:
        ensure_kernel_modules_compatibility_instance.run()
        assert_actions_result(
            ensure_kernel_modules_compatibility_instance,
            level="OVERRIDABLE",
            id="UNSUPPORTED_KERNEL_MODULES",
            title="Unsupported kernel modules",
            description="Unsupported kernel modules were found",
            diagnosis="The following loaded kernel modules are not available in RHEL:",
            remediations="Ensure you have updated the kernel to the latest available version and rebooted the system.",
        )
    else:
        ensure_kernel_modules_compatibility_instance.run()
        assert_actions_result(ensure_kernel_modules_compatibility_instance, level="SUCCESS")

    get_unsupported_kmods_mocked.assert_called_with(
        # host kmods
        set(
            (
                unsupported_pkg,
                "kernel/lib/c.ko.xz",
                "kernel/lib/a.ko.xz",
                "kernel/lib/b.ko.xz",
            )
        ),
        # rhel supported kmods
        set(
            (
                "kernel/lib/c.ko",
                "kernel/lib/b.ko.xz",
                "kernel/lib/c.ko.xz",
                "kernel/lib/a.ko.xz",
                "kernel/lib/a.ko",
            )
        ),
    )
    if msg_in_logs and not exception:
        assert any(msg_in_logs in record.message for record in caplog.records)
    if msg_not_in_logs and not exception:
        assert all(msg_not_in_logs not in record.message for record in caplog.records)


def test_get_loaded_kmods(ensure_kernel_modules_compatibility_instance, monkeypatch):
    run_subprocess_mocked = mock.Mock(
        spec=run_subprocess,
        side_effect=run_subprocess_side_effect(
            (
                ("/usr/sbin/lsmod",),
                (
                    "Module                  Size  Used by\n"
                    "a                 81920  4\n"
                    "b    49152  0\n"
                    "c              40960  1\n",
                    0,
                ),
            ),
            (
                ("/usr/sbin/modinfo", "-F", "filename", "a"),
                (MODINFO_STUB.split()[0] + "\n", 0),
            ),
            (
                ("/usr/sbin/modinfo", "-F", "filename", "b"),
                (MODINFO_STUB.split()[1] + "\n", 0),
            ),
            (
                ("/usr/sbin/modinfo", "-F", "filename", "c"),
                (MODINFO_STUB.split()[2] + "\n", 0),
            ),
        ),
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mocked,
    )
    assert ensure_kernel_modules_compatibility_instance._get_loaded_kmods() == frozenset(
        ("kernel/lib/c.ko.xz", "kernel/lib/a.ko.xz", "kernel/lib/b.ko.xz")
    )


@pytest.mark.parametrize(
    ("repoquery_f_stub", "repoquery_l_stub"),
    (
        (REPOQUERY_F_STUB_GOOD, REPOQUERY_L_STUB_GOOD),
        (REPOQUERY_F_STUB_BAD, REPOQUERY_L_STUB_GOOD),
    ),
)
@centos8
def test_get_rhel_supported_kmods(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    repoquery_f_stub,
    repoquery_l_stub,
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (
                ("repoquery", "-f"),
                (repoquery_f_stub, 0),
            ),
            (
                ("repoquery", "-l"),
                (repoquery_l_stub, 0),
            ),
            (
                ("yum", "makecache"),
                ("", 0),
            ),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    res = ensure_kernel_modules_compatibility_instance._get_rhel_supported_kmods()
    assert res == set(
        (
            "kernel/lib/a.ko",
            "kernel/lib/a.ko.xz",
            "kernel/lib/b.ko.xz",
            "kernel/lib/c.ko.xz",
            "kernel/lib/c.ko",
        )
    )


@pytest.mark.parametrize(
    (
        "repoquery_f_return",
        "repoquery_l_return",
        "makecache_return",
        "exception",
        "exception_msg",
    ),
    (
        (
            (REPOQUERY_F_STUB_GOOD, 0),
            (REPOQUERY_L_STUB_GOOD, 0),
            ("", 1),
            kernel_modules.PackageRepositoryError,
            "We were unable to download the repository metadata for (.*) to determine packages containing kernel modules.  Can be caused by not enough disk space in /var/cache or too little memory.  The yum output below may have a clue for what went wrong in this case:\n\n.*",
        ),
        (
            (REPOQUERY_F_STUB_BAD, 1),
            (REPOQUERY_L_STUB_GOOD, 0),
            ("", 0),
            kernel_modules.PackageRepositoryError,
            "We were unable to query the repositories (.*) to determine packages containing kernel modules. Output from the failed repoquery command:\n\n.*",
        ),
        (
            ("", 0),
            (REPOQUERY_L_STUB_GOOD, 0),
            ("", 0),
            kernel_modules.RHELKernelModuleNotFound,
            "No packages containing kernel modules available in the enabled repositories (.*).",
        ),
    ),
)
@centos8
def test_get_rhel_supported_kmods_repoquery_fails(
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
    pretend_os,
    repoquery_f_return,
    repoquery_l_return,
    makecache_return,
    exception,
    exception_msg,
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (
                ("repoquery", "-f"),
                repoquery_f_return,
            ),
            (
                ("repoquery", "-l"),
                repoquery_l_return,
            ),
            (
                ("yum", "makecache"),
                makecache_return,
            ),
        )
    )
    monkeypatch.setattr(
        kernel_modules,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    with pytest.raises(exception, match=exception_msg):
        ensure_kernel_modules_compatibility_instance._get_rhel_supported_kmods()


@pytest.mark.parametrize(
    ("pkgs", "exp_res"),
    (
        (
            (
                "kernel-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
        ),
        (
            (
                "kmod-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kmod-core-0:10.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:9.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:10.18.0-240.10.1.el8_3.x86_64",),
        ),
        (
            (
                "not-expected-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.15.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",),
        ),
        (("kernel_bad_package:111111",), ("kernel_bad_package:111111",)),
        (
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel_bad_package:111111",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel_bad_package:111111",
            ),
        ),
    ),
)
def test_get_most_recent_unique_kernel_pkgs(pkgs, exp_res, ensure_kernel_modules_compatibility_instance):
    assert tuple(ensure_kernel_modules_compatibility_instance._get_most_recent_unique_kernel_pkgs(pkgs)) == exp_res


@pytest.mark.parametrize(
    ("rhel_kmods_str", "expected"),
    (
        (
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n",
            {"kernel/lib/a.ko.xz"},
        ),
        (
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/6.1.18-200.fc37.x86_64/kernel/lib/lru_cache.ko.xz\n"
            "/lib/modules/6.1.18-200.fc37.x86_64/kernel/lib/crc8.ko\n"
            "/lib/modules/6.1.18-200.fc37.x86_64/kernel/lib/ts_bm.ko\n",
            {"kernel/lib/a.ko.xz", "kernel/lib/lru_cache.ko.xz", "kernel/lib/crc8.ko", "kernel/lib/ts_bm.ko"},
        ),
        (
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
            "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n",
            {"kernel/lib/a.ko.xz"},
        ),
    ),
)
def test_get_rhel_kmods_keys(ensure_kernel_modules_compatibility_instance, rhel_kmods_str, expected):
    result = ensure_kernel_modules_compatibility_instance._get_rhel_kmods_keys(rhel_kmods_str)
    assert result == expected


@pytest.mark.parametrize(
    ("host_kmods", "rhel_supported_kmods", "kmods_to_ignore", "expected"),
    (
        (
            {"kernel/lib/a.ko.xz"},
            {"kernel/lib/a.ko.xz"},
            [],
            [],
        ),
        (
            {"kernel/lib/c.ko.xz"},
            {"kernel/lib/a.ko.xz"},
            [],
            ["/lib/modules/6.1.14-200.fc37.x86_64/kernel/lib/c.ko.xz"],
        ),
        (
            {"kernel/lib/c.ko.xz", "kernel/lib/d.ko.xz"},
            {"kernel/lib/a.ko.xz"},
            [],
            [
                "/lib/modules/6.1.14-200.fc37.x86_64/kernel/lib/c.ko.xz",
                "/lib/modules/6.1.14-200.fc37.x86_64/kernel/lib/d.ko.xz",
            ],
        ),
        (
            {"kernel/lib/c.ko.xz", "kernel/lib/d.ko.xz"},
            {"kernel/lib/c.ko.xz"},
            [],
            [
                "/lib/modules/6.1.14-200.fc37.x86_64/kernel/lib/d.ko.xz",
            ],
        ),
        (
            {"kernel/lib/c.ko.xz", "kernel/lib/d.ko.xz"},
            {"kernel/lib/c.ko.xz"},
            ["kernel/lib/d.ko.xz"],
            [],
        ),
        (
            {"kernel/lib/c.ko.xz", "kernel/lib/d.ko.xz"},
            {"kernel/lib/a.ko.xz"},
            ["kernel/lib/c.ko.xz"],
            [
                "/lib/modules/6.1.14-200.fc37.x86_64/kernel/lib/d.ko.xz",
            ],
        ),
    ),
)
def test_get_unsupported_kmods(
    host_kmods,
    rhel_supported_kmods,
    kmods_to_ignore,
    expected,
    ensure_kernel_modules_compatibility_instance,
    monkeypatch,
):
    monkeypatch.setattr(system_info, "kmods_to_ignore", kmods_to_ignore)
    monkeypatch.setattr(system_info, "booted_kernel", "6.1.14-200.fc37.x86_64")
    result = ensure_kernel_modules_compatibility_instance._get_unsupported_kmods(host_kmods, rhel_supported_kmods)
    for mod in expected:
        assert mod in result


def test_kernel_modules_rhel_kernel_module_not_found_error(ensure_kernel_modules_compatibility_instance, monkeypatch):
    # need to trigger the raise event
    monkeypatch.setattr(EnsureKernelModulesCompatibility, "_get_loaded_kmods", mock.Mock(return_value=None))
    monkeypatch.setattr(
        EnsureKernelModulesCompatibility,
        "_get_rhel_supported_kmods",
        mock.Mock(
            side_effect=RHELKernelModuleNotFound(
                "No packages containing kernel modules available in the enabled repositories"
            )
        ),
    )
    monkeypatch.setattr(EnsureKernelModulesCompatibility, "_get_loaded_kmods", mock.Mock(return_value="loaded_kmods"))
    ensure_kernel_modules_compatibility_instance.run()
    assert_actions_result(
        ensure_kernel_modules_compatibility_instance,
        level="ERROR",
        id="NO_RHEL_KERNEL_MODULES_FOUND",
        title="No RHEL kernel modules were found",
        description="This check was unable to find any kernel modules in the packages in the enabled yum repositories.",
        diagnosis="No packages containing kernel modules available in the enabled repositories",
        remediations="Adding additional repositories to those mentioned in the diagnosis may solve this issue.",
    )


def test_kernel_modules_value_error(ensure_kernel_modules_compatibility_instance, monkeypatch):
    # need to trigger the raise event
    monkeypatch.setattr(
        EnsureKernelModulesCompatibility, "_get_loaded_kmods", mock.Mock(side_effect=ValueError("Value error"))
    )
    ensure_kernel_modules_compatibility_instance.run()
    print(ensure_kernel_modules_compatibility_instance.result)
    assert_actions_result(
        ensure_kernel_modules_compatibility_instance,
        level="ERROR",
        id="CANNOT_COMPARE_PACKAGE_VERSIONS",
        title="Error while comparing packages",
        description="There was an error while detecting the kernel package which corresponds to the kernel modules present on the system.",
        diagnosis="Package comparison failed: Value error",
    )
