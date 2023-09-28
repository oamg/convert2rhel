# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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
import os
import shutil

import pytest

from six.moves import mock

from convert2rhel import cert, unit_tests, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


# Directory with all the tool data
BASE_DATA_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "../data/"))


@pytest.fixture
def cert_dir(monkeypatch, request):
    if request.param["data_dir"] is None:
        data_dir = unit_tests.NONEXISTING_DIR
        rhel_cert_dir = os.path.join(data_dir, "rhel-certs")
    else:
        data_dir = request.param["data_dir"]
        rhel_cert_dir = os.path.join(data_dir, "rhel-certs")

        # Create temporary directory that has no certificate
        cert_dir = os.path.join(rhel_cert_dir, request.param["arch"])
        utils.mkdir_p(cert_dir)

    monkeypatch.setattr(utils, "DATA_DIR", data_dir)
    monkeypatch.setattr(system_info, "arch", request.param["arch"])

    yield rhel_cert_dir

    # Remove the temporary directory tree if we created it earlier
    if request.param["data_dir"] is not None:
        shutil.rmtree(data_dir)


@pytest.mark.parametrize(
    (
        "message",
        "cert_dir",
    ),
    (
        pytest.param(
            "Error: No certificate (.pem) found in %(cert_dir)s.",
            {
                "data_dir": unit_tests.TMP_DIR,
                "arch": "arch",
            },
            id="missing-certificate",
        ),
        pytest.param(
            "Error: Could not access %(cert_dir)s.",
            {
                "data_dir": None,
                "arch": "nonexisting_arch",
            },
            id="missing-cert-dir",
        ),
    ),
    indirect=("cert_dir",),
)
def test_get_cert_path_missing_cert(message, caplog, cert_dir):
    # Check response for the non-existing certificate in the temporary dir
    with pytest.raises(SystemExit):
        cert._get_cert(cert_dir)
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "CRITICAL"
    assert caplog.records[0].message == message % {"cert_dir": cert_dir}


class TestPEMCert:
    @pytest.mark.parametrize(
        ("arch", "rhel_version", "pem"),
        (
            ("ppc64", "7", "74.pem"),
            ("x86_64", "7", "69.pem"),
            ("x86_64", "8", "479.pem"),
        ),
    )
    def test_init_cert_paths(self, arch, rhel_version, pem, monkeypatch, tmpdir):
        source_cert_dir = os.path.join(BASE_DATA_DIR, rhel_version, arch, "rhel-certs")
        fake_target_dir = "/another/directory"
        # Check there are certificates for all the supported RHEL variants
        system_cert = cert.PEMCert(source_cert_dir, fake_target_dir)

        # Check that the certificate paths were set properly
        assert system_cert._cert_filename == pem
        assert system_cert._source_cert_path == os.path.join(source_cert_dir, pem)
        assert system_cert._target_cert_path == os.path.join(fake_target_dir, pem)
        assert system_cert.previously_installed == False

    def test_enable_cert(self, monkeypatch, system_cert_with_target_path):
        system_cert_with_target_path.enable()

        assert system_cert_with_target_path.enabled
        assert system_cert_with_target_path.previously_installed is False
        installed_cert = os.path.join(
            system_cert_with_target_path._target_cert_dir, system_cert_with_target_path._cert_filename
        )
        assert os.path.exists(installed_cert)

        with open(os.path.join(system_cert_with_target_path._source_cert_dir, "479.pem")) as f:
            source_contents = f.read()

        with open(installed_cert) as f:
            installed_contents = f.read()

        assert installed_contents == source_contents

    def test_enable_already_enabled(self, monkeypatch, system_cert_with_target_path):
        real_copy2 = shutil.copy2

        class FakeCopy2:
            def __init__(self):
                self.call_count = 0

            def __call__(self, *args, **kwargs):
                self.call_count += 1
                return real_copy2(*args, **kwargs)

        monkeypatch.setattr(shutil, "copy2", FakeCopy2())

        system_cert_with_target_path.enable()
        previous_number_of_calls = shutil.copy2.call_count
        system_cert_with_target_path.enable()

        # Assert we did not double the actual enable
        assert shutil.copy2.call_count == previous_number_of_calls
        # Check that nothing has changed
        assert system_cert_with_target_path.enabled
        assert system_cert_with_target_path.previously_installed is False
        installed_cert = os.path.join(
            system_cert_with_target_path._target_cert_dir, system_cert_with_target_path._cert_filename
        )
        assert os.path.exists(installed_cert)

        with open(os.path.join(system_cert_with_target_path._source_cert_dir, "479.pem")) as f:
            source_contents = f.read()

        with open(installed_cert) as f:
            installed_contents = f.read()

        assert installed_contents == source_contents

    def test_enable_certificate_already_present(self, caplog, system_cert_with_target_path):
        with open(system_cert_with_target_path._target_cert_path, "w") as f:
            f.write("Content")

        system_cert_with_target_path.enable()

        assert system_cert_with_target_path.enabled
        assert system_cert_with_target_path.previously_installed
        assert (
            "Certificate already present at %s. Skipping copy." % system_cert_with_target_path._target_cert_path
            == caplog.messages[-1]
        )

    def test_enable_certificate_error(self, caplog, monkeypatch, system_cert_with_target_path):
        fake_mkdir_p = mock.Mock(side_effect=OSError(13, "Permission denied"))
        monkeypatch.setattr(utils, "mkdir_p", fake_mkdir_p)

        with pytest.raises(SystemExit):
            system_cert_with_target_path.enable()

        assert "OSError(13): Permission denied" == caplog.messages[-1]

    def test_restore_cert(self, caplog, monkeypatch, system_cert_with_target_path):
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            unit_tests.RunSubprocessMocked(return_string="479.pem is not owned by any package", return_code=1),
        )
        system_cert_with_target_path.enable()

        system_cert_with_target_path.restore()

        assert "Certificate %s removed" % system_cert_with_target_path._target_cert_path in caplog.messages[-1]

    def test_restore_cert_previously_installed(self, caplog, monkeypatch, system_cert_with_target_path):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        system_cert_with_target_path.enable()

        system_cert_with_target_path.restore()

        assert (
            "Certificate %s was present before conversion. Skipping removal."
            % system_cert_with_target_path._cert_filename
            in caplog.messages[-1]
        )

    @pytest.mark.parametrize(
        (
            "error_condition",
            "text_not_expected_in_logs",
        ),
        (
            (
                OSError(2, "No such file or directory"),
                "No such file or directory",
            ),
            (
                OSError(13, "[Errno 13] Permission denied: '/tmpdir/certfile'"),
                "OSError(13): Permission denied: '/tmpdir/certfile'",
            ),
        ),
    )
    def test_restore_cert_error_conditions(
        self, error_condition, text_not_expected_in_logs, caplog, monkeypatch, system_cert_with_target_path
    ):
        def fake_os_remove(path):
            raise error_condition

        monkeypatch.setattr(os, "remove", fake_os_remove)
        system_cert_with_target_path.enable()

        system_cert_with_target_path.restore()

        for message in caplog.messages:
            assert text_not_expected_in_logs not in message

    @pytest.mark.parametrize(
        ("rpm_exit_code", "rpm_stdout", "expected"),
        (
            (
                0,
                "subscription-manager-1.0-1.noarch",
                "A package was installed that owns the certificate %s. Skipping removal.",
            ),
            (1, "", "Unable to determine if a package owns certificate %s. Skipping removal."),
            (
                1,
                "Error printed to stdout",
                "Unable to determine if a package owns certificate %s. Skipping removal.",
            ),
            (
                1,
                "error: file /etc/pki/product-default/69.pem: No such file or directory",
                "Certificate already removed from %s",
            ),
        ),
    )
    def test_restore_rpm_package_owns(
        self, caplog, monkeypatch, system_cert_with_target_path, rpm_exit_code, rpm_stdout, expected
    ):
        monkeypatch.setattr(
            utils, "run_subprocess", unit_tests.RunSubprocessMocked(return_string=rpm_stdout, return_code=rpm_exit_code)
        )
        system_cert_with_target_path.enable()

        system_cert_with_target_path.restore()

        assert expected % system_cert_with_target_path._target_cert_path in caplog.messages[-1]
