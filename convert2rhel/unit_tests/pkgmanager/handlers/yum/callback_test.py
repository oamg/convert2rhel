__metaclass__ = type

import pytest

from convert2rhel import pkgmanager
from convert2rhel.pkgmanager.handlers.yum.callback import PackageDownloadCallback, TransactionDisplayCallback


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
class TestPackageDownloadCallback:
    @pytest.mark.parametrize(
        ("name", "frac", "fread", "ftime", "expected"),
        (
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                1,
                "1250",
                "10s",
                "Downloading package: libicu-60.3-2.el8_1.x86_64.rpm",
                id="download-a-simple-package",
            ),
            pytest.param(
                "repo.xml",
                1,
                "100",
                "1s",
                "Downloading repository metadata: repo.xml",
                id="download-repository-metadata",
            ),
        ),
    )
    def test_update_progress(self, name, frac, fread, ftime, expected, caplog):
        instance = PackageDownloadCallback()
        instance.updateProgress(name=name, frac=frac, fread=fread, ftime=ftime)

        assert expected in caplog.records[-1].message

    def test_update_progress_duplicate_packages(self, caplog):
        instance = PackageDownloadCallback()
        packages = ["libicu-60.3-2.el8_1.x86_64.rpm", "libicu-60.3-2.el8_1.x86_64.rpm"]

        for package in packages:
            instance.updateProgress(name=package, frac=1, fread="1250", ftime="10s")

        assert len(caplog.records) == 1
        assert "Downloading package: libicu-60.3-2.el8_1.x86_64.rpm" in caplog.records[-1].message


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
class TestTransactionDisplayCallback:
    def test_event(self, caplog):
        instance = TransactionDisplayCallback()
        instance.event(
            package="libicu-60.3-2.el8_1.x86_64.rpm", action=20, te_current=1, te_total=1, ts_current=1, ts_total=1
        )

        assert "Installing: libicu-60.3-2.el8_1.x86_64.rpm [1/1]" in caplog.records[-1].message

    def test_event_duplicate_package(self, caplog):
        instance = TransactionDisplayCallback()
        packages = ["libicu-60.3-2.el8_1.x86_64.rpm", "libicu-60.3-2.el8_1.x86_64.rpm"]
        for package in packages:
            instance.event(package=package, action=20, te_current=1, te_total=1, ts_current=1, ts_total=1)

        assert len(caplog.records) == 1
        assert "Installing: libicu-60.3-2.el8_1.x86_64.rpm [1/1]" in caplog.records[-1].message

    def test_event_multiple_packages(self, caplog):
        instance = TransactionDisplayCallback()
        packages = ["libicu-60.3-2.el8_1.x86_64.rpm", "breeze-icon-theme-5.102.0-1.fc37.noarch"]
        for package in packages:
            instance.event(package=package, action=20, te_current=1, te_total=1, ts_current=1, ts_total=1)

            assert "Installing: %s [1/1]" % package in caplog.records[-1].message

        assert len(caplog.records) == 2

    @pytest.mark.parametrize(
        ("package", "msgs", "expected"),
        (
            ("package-1", "Test output scriptlet", "Scriptlet output package-1: Test output scriptlet"),
            (None, None, None),
        ),
    )
    def test_scriptout(self, package, msgs, expected, caplog):
        TransactionDisplayCallback().scriptout(package, msgs)

        if expected:
            assert expected in caplog.records[-1].message

    def test_errorlog(self, caplog):
        TransactionDisplayCallback().errorlog("Something went wrong with the transaction.")

        assert "Transaction error: Something went wrong with the transaction." in caplog.records[-1].message
