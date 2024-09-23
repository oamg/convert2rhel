# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
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
import shutil

import pytest

from six.moves import mock

from convert2rhel import exceptions, unit_tests, utils
from convert2rhel.backup import certs
from convert2rhel.backup.certs import RestorablePEMCert, RestorableRpmKey
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.utils import files


# Directory with all the tool data
BASE_DATA_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "../../data/"))


@pytest.fixture
def run_subprocess_with_empty_rpmdb(monkeypatch, tmpdir):
    """When we use rpm, inject our fake rpmdb instead of the system one."""
    rpmdb = os.path.join(str(tmpdir), "rpmdb")
    os.mkdir(rpmdb)

    class RunSubprocessWithEmptyRpmdb(RunSubprocessMocked):
        def __call__(self, *args, **kwargs):
            # Call the super class for recordkeeping (update how we were
            # called)
            super(RunSubprocessWithEmptyRpmdb, self).__call__(*args, **kwargs)

            if args[0][0] == "rpm":
                args[0].extend(["--dbpath", rpmdb])

            return real_run_subprocess(*args, **kwargs)

    real_run_subprocess = utils.run_subprocess
    instrumented_run_subprocess = RunSubprocessWithEmptyRpmdb()
    monkeypatch.setattr(utils, "run_subprocess", instrumented_run_subprocess)

    return instrumented_run_subprocess


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
        files.mkdir_p(cert_dir)

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
        certs._get_cert(cert_dir)
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "CRITICAL"
    assert caplog.records[0].message == message % {"cert_dir": cert_dir}


class TestPEMCert:
    @pytest.mark.parametrize(
        ("arch", "rhel_version", "pem"),
        (
            ("x86_64", "7", "69.pem"),
            ("x86_64", "8", "479.pem"),
        ),
    )
    def test_init_cert_paths(self, arch, rhel_version, pem):
        source_cert_dir = os.path.join(BASE_DATA_DIR, rhel_version, arch, "rhel-certs")
        fake_target_dir = "/another/directory"
        # Check there are certificates for all the supported RHEL variants
        system_cert = RestorablePEMCert(source_cert_dir, fake_target_dir)

        # Check that the certificate paths were set properly
        assert system_cert._cert_filename == pem
        assert system_cert._source_cert_path == os.path.join(source_cert_dir, pem)
        assert system_cert._target_cert_path == os.path.join(fake_target_dir, pem)
        assert not system_cert.previously_installed

    def test_enable_cert(self, system_cert_with_target_path):
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
            "Certificate already present at {}. Skipping copy.".format(system_cert_with_target_path._target_cert_path)
            == caplog.messages[-1]
        )

    def test_enable_certificate_error(self, caplog, monkeypatch, system_cert_with_target_path):
        fake_mkdir_p = mock.Mock(side_effect=OSError(13, "Permission denied"))
        monkeypatch.setattr(files, "mkdir_p", fake_mkdir_p)

        with pytest.raises(exceptions.CriticalError):
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

        assert "Certificate {} removed".format(system_cert_with_target_path._target_cert_path) in caplog.messages[-1]

    def test_restore_cert_previously_installed(self, caplog, monkeypatch, system_cert_with_target_path):
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        system_cert_with_target_path.enable()

        system_cert_with_target_path.restore()

        assert (
            "Certificate {} was present before conversion. Skipping removal.".format(
                system_cert_with_target_path._cert_filename
            )
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

    def test_restore_cert_error_raised(self, system_cert_with_target_path, monkeypatch, caplog):
        monkeypatch.setattr(os, "remove", mock.Mock(side_effect=OSError(1, "Operation not permitted")))

        system_cert_with_target_path.enable()

        with pytest.raises(OSError):
            system_cert_with_target_path.restore()

        assert "No certificates found to be removed." not in caplog.text

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


class TestRestorableRpmKey:
    gpg_key = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "../../data/version-independent/gpg-keys/RPM-GPG-KEY-redhat-release")
    )

    @pytest.fixture
    def rpm_key(self):
        return RestorableRpmKey(self.gpg_key)

    def test_init(self):
        rpm_key = RestorableRpmKey(self.gpg_key)

        assert rpm_key.previously_installed is None
        assert rpm_key.enabled is False
        assert rpm_key.keyid == "fd431d51"
        assert rpm_key.keyfile.endswith("/data/version-independent/gpg-keys/RPM-GPG-KEY-redhat-release")

    def test_installed_yes(self, run_subprocess_with_empty_rpmdb, rpm_key):
        utils.run_subprocess(["rpm", "--import", self.gpg_key], print_output=False)

        assert rpm_key.installed is True

    def test_installed_not_yet(self, run_subprocess_with_empty_rpmdb, rpm_key):
        assert rpm_key.installed is False

    def test_installed_generic_failure(self, monkeypatch, rpm_key):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=("Unknown error", 1)))

        with pytest.raises(
            utils.ImportGPGKeyError, match="Searching the rpmdb for the gpg key fd431d51 failed: Code 1: Unknown error"
        ):
            rpm_key.installed

    def test_enable(self, run_subprocess_with_empty_rpmdb, rpm_key):
        rpm_key.enable()

        assert rpm_key.enabled is True
        assert rpm_key.installed is True
        assert rpm_key.previously_installed is False

    def test_enable_already_enabled(self, run_subprocess_with_empty_rpmdb, rpm_key):
        rpm_key.enable()
        previous_number_of_calls = run_subprocess_with_empty_rpmdb.call_count
        rpm_key.enable()

        # Check that we do not double enable
        assert run_subprocess_with_empty_rpmdb.call_count == previous_number_of_calls

        # Check that nothing has changed
        assert rpm_key.enabled is True
        assert rpm_key.installed is True
        assert rpm_key.previously_installed is False

    def test_enable_already_installed(self, run_subprocess_with_empty_rpmdb, rpm_key):
        utils.run_subprocess(["rpm", "--import", self.gpg_key], print_output=False)
        rpm_key.enable()

        # Check that we did not call rpm to import the key
        # Omit the first call because that is the call we performed to setup the test.
        for call in run_subprocess_with_empty_rpmdb.call_args_list[1:]:
            assert not (call[0][0] == "rpm" and "--import" in call[0])

        # Check that the key is installed and we show that it was previously installed
        assert rpm_key.enabled is True
        assert rpm_key.installed is True
        assert rpm_key.previously_installed is True

    def test_enable_failure_to_import(self, monkeypatch, run_subprocess_with_empty_rpmdb, rpm_key):
        # Raise an error when we try to rpm --import
        def run_subprocess_error(*args, **kwargs):
            if args[0][0] == "rpm" and "--import" in args[0]:
                return "Error importing", 1
            return run_subprocess_with_empty_rpmdb(*args, **kwargs)

        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_error)

        with pytest.raises(utils.ImportGPGKeyError, match="Failed to import the GPG key [^ ]+: Error importing"):
            rpm_key.enable()

    def test_restore_uninstall(self, run_subprocess_with_empty_rpmdb, rpm_key):
        rpm_key.enable()

        rpm_key.restore()

        # Check that the beginning of the run_subprocess call starts with the command to remove
        # the key (The arguments our fixture has added to use the empty rpmdb come after that)
        assert run_subprocess_with_empty_rpmdb.call_args_list[-1][0][0][0:3] == ["rpm", "-e", "gpg-pubkey-fd431d51"]

        # Check that we actually removed the key from the rpmdb
        output, status = run_subprocess_with_empty_rpmdb(["rpm", "-qa", "gpg-pubkey"])
        assert output == ""

    def test_restore_not_enabled(self, run_subprocess_with_empty_rpmdb, rpm_key):
        called_previously = run_subprocess_with_empty_rpmdb.call_count
        rpm_key.restore()

        assert run_subprocess_with_empty_rpmdb.call_count == called_previously
        assert rpm_key.enabled is False

    def test_restore_previously_installed(self, run_subprocess_with_empty_rpmdb, rpm_key):
        utils.run_subprocess(["rpm", "--import", self.gpg_key], print_output=False)
        rpm_key.enable()
        called_previously = run_subprocess_with_empty_rpmdb.call_count

        rpm_key.restore()

        # run_subprocess has not been called again
        assert run_subprocess_with_empty_rpmdb.call_count == called_previously

        # Check that the key is still in the rpmdb
        output, status = run_subprocess_with_empty_rpmdb(["rpm", "-q", "gpg-pubkey-fd431d51"])
        assert status == 0
        assert output.startswith("gpg-pubkey-fd431d51")
        assert rpm_key.enabled is False
