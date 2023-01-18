import pytest

from convert2rhel import pkgmanager
from convert2rhel.pkgmanager.handlers.dnf.callback import (
    DependencySolverProgressIndicatorCallback,
    PackageDownloadCallback,
    TransactionDisplayCallback,
)


class PackageDownloadPayload:
    def __init__(self, name="test", download_size=1000):
        self.name = name
        self._download_size = download_size

    def __str__(self):
        return self.name

    @property
    def download_size(self):
        return self._download_size


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
class TestDependencySolverProgressIndicatorCallback:
    @pytest.mark.parametrize(
        ("package", "mode", "expected"),
        (
            ("package-1", "i", "package-1 will be installed."),
            ("package-1", "u", "package-1 will be an update."),
            ("package-1", "e", "package-1 will be erased."),
            ("package-1", "r", "package-1 will be reinstalled."),
            ("package-1", "d", "package-1 will be an downgrade."),
            ("package-1", "o", "package-1 will obsolete another package."),
            ("package-1", "ud", "package-1 will be updated."),
            ("package-1", "od", "package-1 will be obsoleted."),
        ),
    )
    def test_pkg_added(self, package, mode, expected, caplog):
        instance = DependencySolverProgressIndicatorCallback()
        instance.pkg_added(pkg=package, mode=mode)

        assert expected in caplog.records[-1].message

    def test_pkg_added_no_mode(self, caplog):
        instance = DependencySolverProgressIndicatorCallback()
        instance.pkg_added(pkg="package-1", mode="x")

        assert "Unknow operation (x) for package 'package-1'." in caplog.records[-1].message

    def test_start(self, caplog):
        instance = DependencySolverProgressIndicatorCallback()
        instance.start()

        assert "Starting dependency resolution process." in caplog.records[-1].message

    def test_end(self, caplog):
        instance = DependencySolverProgressIndicatorCallback()
        instance.end()

        assert "Finished dependency resolution process." in caplog.records[-1].message


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
class TestDnfPackageDownloadCallback:
    def test_start(self):
        instance = PackageDownloadCallback()
        instance.start(total_files=100, total_size=37500, total_drpms=100)

        assert instance.total_files == 100
        assert instance.total_size == 37500
        assert instance.total_drpm == 100

    @pytest.mark.parametrize(
        ("package", "status", "err_msg", "total_files", "total_size", "total_drpms", "expected"),
        (
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                1,
                "package failed to download",
                1,
                37500,
                0,
                "FAILED",
                id="download-status-failed",
            ),
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                2,
                "package failed to download",
                1,
                37500,
                0,
                "(1/1) [SKIPPED]: libicu-60.3-2.el8_1.x86_64.rpm",
                id="download-status-already-exists",
            ),
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                3,
                "package failed to download",
                1,
                37500,
                0,
                "(0/1) [MIRROR]: libicu-60.3-2.el8_1.x86_64.rpm",
                id="download-status-mirror",
            ),
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                4,
                "package failed to download",
                1,
                37500,
                0,
                "(0/1) [DRPM]: libicu-60.3-2.el8_1.x86_64.rpm",
                id="download-status-drpm",
            ),
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                4,
                "test err_msg",
                1,
                37500,
                2,
                "(0/1) [DRPM 1/2]: libicu-60.3-2.el8_1.x86_64.rpm - test err_msg",
                id="drpm-message-with-err-msg",
            ),
            pytest.param(
                "libicu-60.3-2.el8_1.x86_64.rpm",
                None,
                "test err_msg",
                2,
                37500,
                2,
                "(1/2): libicu-60.3-2.el8_1.x86_64.rpm",
                id="no-status",
            ),
        ),
    )
    def test_end(self, package, status, err_msg, total_files, total_size, total_drpms, expected, caplog):
        payload = PackageDownloadPayload(package, 37500)
        instance = PackageDownloadCallback()
        # It's cleaner to call start here than "mock" the other properties we
        # will use.
        instance.start(total_files, total_size, total_drpms)
        instance.end(payload=payload, status=status, err_msg=err_msg)

        assert expected in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("packages", "status", "err_msg", "total_files", "total_size", "total_drpms", "expected_message"),
        (
            pytest.param(
                ["package-1.rpm", "package-2.rpm", "package-3.rpm", "package-4.rpm", "package-5.rpm"],
                None,
                None,
                5,
                5000,  # 1000 for each file
                0,
                "(%d/%d): %s",
                id="download-multiple-packages",
            ),
            pytest.param(
                ["package-1.rpm", "package-2.rpm", "package-3.rpm", "package-4.rpm", "package-5.rpm"],
                2,
                None,
                5,
                5000,  # 1000 for each file
                0,
                "(%d/%d) [SKIPPED]: %s",
                id="download-multiple-packages-skipped-status",
            ),
        ),
    )
    def test_end_multiple_packages(
        self, packages, status, err_msg, total_files, total_size, total_drpms, expected_message, caplog
    ):
        package_count = 1
        instance = PackageDownloadCallback()
        for package in packages:
            payload = PackageDownloadPayload(package, 1000)
            instance.start(total_files, total_size, total_drpms)
            instance.end(payload=payload, status=status, err_msg=err_msg)

            expected = expected_message % (package_count, total_files, package)
            assert expected in caplog.records[-1].message
            package_count += 1

    def test_end_no_status_and_not_enough_files(self, caplog):
        instance = PackageDownloadCallback()
        instance.start(0, 0, 0)
        payload = PackageDownloadPayload("", 0)
        instance.end(payload, None, None)

        assert not caplog.records


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
class TestDnfTransactionDisplayCallback:
    def test_progress(self, caplog):
        TransactionDisplayCallback().progress(
            package="libicu-60.3-2.el8_1.x86_64.rpm", action=103, ti_done=1, ti_total=1, ts_done=1, ts_total=1
        )

        assert "Running scriptlet: libicu-60.3-2.el8_1.x86_64.rpm [1/1]" in caplog.records[-1].message

    def test_duplicate_package(self, caplog):
        instance = TransactionDisplayCallback()
        packages = ["libicu-60.3-2.el8_1.x86_64.rpm", "libicu-60.3-2.el8_1.x86_64.rpm"]
        for package in packages:
            instance.progress(package=package, action=103, ti_done=1, ti_total=1, ts_done=1, ts_total=1)

        assert len(caplog.records) == 1
        assert "Running scriptlet: libicu-60.3-2.el8_1.x86_64.rpm [1/1]" in caplog.records[-1].message

    def test_no_action_and_package(self, caplog):
        TransactionDisplayCallback().progress(None, None, None, None, None, None)
        assert "No action or package was provided in the callback." in caplog.records[-1].message
