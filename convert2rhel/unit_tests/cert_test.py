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
            "Error: System certificate (.pem) not found in %(cert_dir)s.",
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
        cert.SystemCert._get_cert()
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "CRITICAL"
    assert caplog.records[0].message == message % {"cert_dir": cert_dir}


@pytest.mark.parametrize(
    ("arch", "rhel_version", "pem"),
    (
        ("x86_64", "6", "69.pem"),
        ("x86_64", "7", "69.pem"),
        ("x86_64", "8", "479.pem"),
        ("ppc64", "7", "74.pem"),
    ),
)
def test_get_cert_path(arch, rhel_version, pem, monkeypatch):
    monkeypatch.setattr(utils, "DATA_DIR", os.path.join(BASE_DATA_DIR, rhel_version, arch))
    # Check there are certificates for all the supported RHEL variants
    system_cert = cert.SystemCert()

    cert_path = system_cert._source_cert_path
    assert cert_path == "{0}/rhel-certs/{1}".format(utils.DATA_DIR, pem)


def test_install_cert(monkeypatch, tmpdir):
    monkeypatch.setattr(tool_opts, "arch", "x86_64")
    monkeypatch.setattr(utils, "DATA_DIR", os.path.join(BASE_DATA_DIR, "6", "x86_64"))

    # By initializing the cert object we get a path to an existing
    # certificate based on the mocked parameters above
    system_cert = cert.SystemCert()
    system_cert._target_cert_dir = str(tmpdir)

    system_cert.install()

    installed_cert_path = os.path.join(system_cert._target_cert_dir, system_cert._cert_filename)
    assert os.path.exists(installed_cert_path)


@pytest.mark.cert_filename("filename")
def test_remove_cert(caplog, system_cert_with_target_path):
    cert_file_path = system_cert_with_target_path._target_cert_path
    with open(cert_file_path, "wb") as cert_file:
        cert_file.write(b"some content")

    system_cert_with_target_path.remove()

    assert "Certificate %s removed" % cert_file_path in caplog.messages[-1]


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
def test_remove_cert_error_conditions(
    error_condition, text_not_expected_in_logs, caplog, monkeypatch, system_cert_with_target_path
):
    def fake_os_remove(path):
        raise error_condition

    monkeypatch.setattr(os, "remove", fake_os_remove)

    system_cert_with_target_path.remove()

    for message in caplog.messages:
        assert text_not_expected_in_logs not in message
