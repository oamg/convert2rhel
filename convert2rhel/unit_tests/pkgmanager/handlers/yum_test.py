import pytest
import six

from convert2rhel import pkgmanager, unit_tests, utils
from convert2rhel.pkgmanager.handlers.yum import YumTransactionHandler
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import centos7


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class YumResolveDepsMocked(unit_tests.MockFunction):
    def __init__(self, called=0):
        self.called = called

    def __call__(self, *args, **kwargs):
        self.called += 1
        if self.called >= 2:
            return (0, "success")
        else:
            return (1, "failed")


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
class TestYumTransactionHandler(object):
    @pytest.fixture
    def _mock_yum_api_transaction_calls(self, monkeypatch):
        """ """
        monkeypatch.setattr(pkgmanager.RepoStorage, "enableRepo", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "update", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "reinstall", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "downgrade", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "resolveDeps", value=mock.Mock(return_value=(0, "Success.")))
        monkeypatch.setattr(pkgmanager.YumBase, "processTransaction", value=mock.Mock())

    @centos7
    @pytest.mark.skipif(
        pkgmanager.TYPE != "yum",
        reason="No yum module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs", "test_transaction"),
        (
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
                False,
            ),
            (
                ["rhel-7-repo-test", "rhel-7-repo-test-2"],
                ["package-1", "package-2", "package-3"],
                True,
            ),
        ),
    )
    def test_process_yum_transaction(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        test_transaction,
        _mock_yum_api_transaction_calls,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.yum,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", value=lambda: enabled_repos)
        instance = YumTransactionHandler()
        instance.process_transaction(test_transaction)

        assert pkgmanager.RepoStorage.enableRepo.call_count == len(enabled_repos)
        assert pkgmanager.YumBase.update.call_count == len(original_os_pkgs)
        assert pkgmanager.YumBase.reinstall.call_count == len(original_os_pkgs)
        assert not pkgmanager.YumBase.downgrade.called
        assert pkgmanager.YumBase.resolveDeps.call_count == 1
        assert pkgmanager.YumBase.processTransaction.call_count == 1

    @centos7
    @pytest.mark.skipif(
        pkgmanager.TYPE != "yum",
        reason="No yum module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
            (
                ["rhel-7-repo-test", "rhel-7-repo-test-2"],
                ["package-1", "package-2", "package-3"],
            ),
        ),
    )
    def test_process_yum_transaction_downgrade_pkgs(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_yum_api_transaction_calls,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.yum,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", value=lambda: enabled_repos)
        # Re-patch the reinstall function to use a side_effect
        pkgmanager.YumBase.reinstall = mock.Mock(
            side_effect=pkgmanager.Errors.ReinstallInstallError,
        )

        instance = YumTransactionHandler()
        instance.process_transaction()

        assert pkgmanager.RepoStorage.enableRepo.call_count == len(enabled_repos)
        assert pkgmanager.YumBase.update.call_count == len(original_os_pkgs)
        assert pkgmanager.YumBase.reinstall.call_count == len(original_os_pkgs)
        assert pkgmanager.YumBase.downgrade.call_count == len(original_os_pkgs)
        assert pkgmanager.YumBase.resolveDeps.call_count == 1
        assert pkgmanager.YumBase.processTransaction.call_count == 1

    @centos7
    @pytest.mark.skipif(
        pkgmanager.TYPE != "yum",
        reason="No yum module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
        ),
    )
    def test_process_yum_transaction_resolve_deps_exception(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_yum_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.yum,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", value=lambda: enabled_repos)
        pkgmanager.YumBase.resolveDeps = YumResolveDepsMocked()
        instance = YumTransactionHandler()
        instance.process_transaction()

    @centos7
    @pytest.mark.skipif(
        pkgmanager.TYPE != "yum",
        reason="No yum module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
        ),
    )
    def test_process_yum_transaction_resolve_deps_not_finished(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_yum_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.yum,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", value=lambda: enabled_repos)
        # Initialize this with a negative number so we don't bump into the
        # limit, this way we test the while limit.
        pkgmanager.YumBase.resolveDeps = YumResolveDepsMocked(-5)
        instance = YumTransactionHandler()
        with pytest.raises(SystemExit):
            instance.process_transaction()

        assert "Couldn't resolve yum dependencies" in caplog.records[-1].message

    @centos7
    @pytest.mark.skipif(
        pkgmanager.TYPE != "yum",
        reason="No yum module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
            (
                ["rhel-7-repo-test"],
                ["package-1", "package-2", "package-3"],
            ),
        ),
    )
    def test_process_yum_transaction_process_transaction_exception(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_yum_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.yum,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", value=lambda: enabled_repos)

        pkgmanager.YumBase.processTransaction = mock.Mock(
            side_effect=[
                pkgmanager.Errors.YumRPMCheckError,
                pkgmanager.Errors.YumTestTransactionError,
                pkgmanager.Errors.YumRPMTransError,
            ]
        )

        instance = YumTransactionHandler()
        with pytest.raises(SystemExit):
            instance.process_transaction()

        assert "Failed to process yum transactions." in caplog.records[-1].message


@centos7
@pytest.mark.parametrize(
    ("output", "expected_remove_pkgs"),
    (
        # A real case
        (
            [
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-submod-security(x86-64) = 4.1-27.el7.centos.1",
                "ldb-tools-1.5.4-2.el7.x86_64 requires libldb(x86-64) = 1.5.4-2.el7",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-submod-multimedia(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-4.0.9.2-2.el7_9.noarch requires python2-hawkey >= 0.22.5",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64 requires abrt = 2.1.11-60.el7.centos",
            ],
            {
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                "ldb-tools-1.5.4-2.el7.x86_64",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                "python2-dnf-4.0.9.2-2.el7_9.noarch",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64",
            },
        ),
        # Prevent duplicate entries
        (
            [
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64 requires abrt = 2.1.11-60.el7.centos",
            ],
            {
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64",
            },
        ),
        # Random string - This might not happen that frequently.
        (
            ["testing the test random string"],
            {},
        ),
    ),
)
def test__resolve_yum_problematic_dependencies(
    pretend_os,
    output,
    expected_remove_pkgs,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(pkgmanager.handlers.yum, "remove_pkgs", mock.Mock())
    pkgmanager.handlers.yum._resolve_yum_problematic_dependencies(output)

    if expected_remove_pkgs:
        assert pkgmanager.handlers.yum.remove_pkgs.called
        pkgmanager.handlers.yum.remove_pkgs.assert_called_with(
            pkgs_to_remove=expected_remove_pkgs,
            backup=True,
            critical=False,
            reposdir=utils.BACKUP_DIR,
            set_releasever=False,
            manual_releasever=7,
        )
    else:
        assert "No packages to remove." in caplog.records[-1].message
