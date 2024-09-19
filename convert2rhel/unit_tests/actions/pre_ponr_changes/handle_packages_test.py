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

import pytest
import six

from convert2rhel import actions, pkghandler, pkgmanager, repo, unit_tests, utils
from convert2rhel.actions.pre_ponr_changes import handle_packages
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import (
    FormatPkgInfoMocked,
    GetPackagesToRemoveMocked,
    GetThirdPartyPkgsMocked,
    MockFunctionObject,
    RemovePkgsMocked,
)
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class RemovePkgsUnlessFromRedhatMocked(MockFunctionObject):
    spec = handle_packages._remove_packages_unless_from_redhat


@pytest.fixture
def list_third_party_packages_instance():
    return handle_packages.ListThirdPartyPackages()


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(repo, "tool_opts", global_tool_opts)


def test_list_third_party_packages_no_packages(list_third_party_packages_instance, monkeypatch, caplog):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", GetThirdPartyPkgsMocked(pkg_selection="empty"))

    list_third_party_packages_instance.run()

    assert "No third party packages installed" in caplog.records[-1].message
    assert list_third_party_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


@centos8
def test_list_third_party_packages(pretend_os, list_third_party_packages_instance, monkeypatch):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", GetThirdPartyPkgsMocked(pkg_selection="key_ids"))
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked(return_value=["shim", "ruby", "pytest"]))
    monkeypatch.setattr(system_info, "name", "Centos7")
    monkeypatch.setattr(pkgmanager, "TYPE", "dnf")
    diagnosis = (
        "Only packages signed by Centos7 are to be"
        " replaced. Red Hat support won't be provided"
        " for the following third party packages:\npkg1-None-None.None, pkg2-None-None.None, gpg-pubkey-1.0.0-1.x86_64"
    )
    list_third_party_packages_instance.run()
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="THIRD_PARTY_PACKAGE_DETECTED",
                title="Third party packages detected",
                description="Third party packages will not be replaced during the conversion.",
                diagnosis=diagnosis,
            ),
        )
    )
    assert expected.issuperset(list_third_party_packages_instance.messages)
    assert expected.issubset(list_third_party_packages_instance.messages)
    assert len(pkghandler.format_pkg_info.call_args[0][0]) == 3


@pytest.fixture
def remove_special_packages_instance():
    return handle_packages.RemoveSpecialPackages()


def get_centos_logos_pkg_object():
    return pkghandler.PackageInformation(
        packager="CentOS BuildSystem <http://bugs.centos.org>",
        vendor="CentOS",
        nevra=pkghandler.PackageNevra(
            name="centos-logos",
            epoch="0",
            version="70.0.6",
            release="3.el7.centos",
            arch="noarch",
        ),
        key_id="24c6a8a7f4a80eb5",
        signature="RSA/SHA256, Wed Sep 30 20:10:39 2015, Key ID 24c6a8a7f4a80eb5",
    )


@pytest.fixture
def pkgs_to_remove():
    return [
        pkghandler.PackageInformation(
            packager="CentOS BuildSystem <http://bugs.centos.org>",
            vendor="CentOS",
            nevra=pkghandler.PackageNevra(
                name="centos-logos",
                epoch="0",
                version="70.0.6",
                release="3.el7.centos",
                arch="noarch",
            ),
            key_id="24c6a8a7f4a80eb5",
            signature="RSA/SHA256, Wed Sep 30 20:10:39 2015, Key ID 24c6a8a7f4a80eb5",
        ),
        pkghandler.PackageInformation(
            packager="CentOS BuildSystem <http://bugs.centos.org>",
            vendor="CentOS",
            nevra=pkghandler.PackageNevra(
                name="test1",
                epoch="0",
                version="1.0.6",
                release="3.el7.centos",
                arch="noarch",
            ),
            key_id="24c6a8a7f4a80eb5",
            signature="RSA/SHA256, Wed Sep 30 20:10:39 2015, Key ID 24c6a8a7f4a80eb5",
        ),
        pkghandler.PackageInformation(
            packager="CentOS BuildSystem <http://bugs.centos.org>",
            vendor="CentOS",
            nevra=pkghandler.PackageNevra(
                name="test2",
                epoch="0",
                version="1.2.6",
                release="3.el7.centos",
                arch="noarch",
            ),
            key_id="24c6a8a7f4a80eb5",
            signature="RSA/SHA256, Wed Sep 30 20:10:39 2015, Key ID 24c6a8a7f4a80eb5",
        ),
    ]


class TestRemoveSpecialPackages:
    def test_dependency_order(self, remove_special_packages_instance):
        expected_dependencies = (
            # We use the backed up repos in remove_pkgs_unless_from_redhat()
            "BACKUP_REPOSITORY",
            "BACKUP_PACKAGE_FILES",
            "BACKUP_REDHAT_RELEASE",
        )

        assert expected_dependencies == remove_special_packages_instance.dependencies

    def test_run_no_packages_to_remove(self, monkeypatch, remove_special_packages_instance, caplog):
        monkeypatch.setattr(pkghandler, "get_packages_to_remove", GetPackagesToRemoveMocked(return_value=[]))
        remove_special_packages_instance.run()
        assert "No packages to backup and remove." in caplog.records[-1].message

    def test_run_all_removed(self, monkeypatch, remove_special_packages_instance):
        pkgs_to_remove = [get_centos_logos_pkg_object()]
        pkgs_removed = ["centos-logos-70.0.6-3.el7.centos.noarch"]
        expected = set(
            (
                actions.ActionMessage(
                    level="INFO",
                    id="SPECIAL_PACKAGES_REMOVED",
                    title="Special packages to be removed",
                    description="We have identified installed packages that match a pre-defined list of packages that are"
                    " to be removed during the conversion",
                    diagnosis="The following packages will be removed during the conversion: centos-logos-70.0.6-3.el7.centos.noarch",
                    remediations=None,
                    variables={},
                ),
            )
        )
        monkeypatch.setattr(
            pkghandler, "get_packages_to_remove", GetPackagesToRemoveMocked(return_value=pkgs_to_remove)
        )
        monkeypatch.setattr(
            handle_packages,
            "_remove_packages_unless_from_redhat",
            RemovePkgsUnlessFromRedhatMocked(return_value=pkgs_removed),
        )

        remove_special_packages_instance.run()
        assert expected.issuperset(remove_special_packages_instance.messages)
        assert expected.issubset(remove_special_packages_instance.messages)
        assert pkghandler.get_packages_to_remove.call_count == 2
        assert handle_packages._remove_packages_unless_from_redhat.call_count == 1
        assert remove_special_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]

    @centos8
    def test_run_packages_not_removed(self, pretend_os, monkeypatch, remove_special_packages_instance):
        pkgs_removed = ["kernel-core"]
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="SPECIAL_PACKAGES_NOT_REMOVED",
                    title="Special packages not removed",
                    description="Special packages which could not be removed",
                    diagnosis="The following packages were not removed: gpg-pubkey-1.0.0-1.x86_64, pkg1-None-None.None, pkg2-None-None.None",
                    remediations=None,
                    variables={},
                ),
                actions.ActionMessage(
                    level="INFO",
                    id="SPECIAL_PACKAGES_REMOVED",
                    title="Special packages to be removed",
                    description=(
                        "We have identified installed packages that match a pre-defined list of packages that are"
                        " to be removed during the conversion"
                    ),
                    diagnosis="The following packages will be removed during the conversion: kernel-core",
                    remediations=None,
                    variables={},
                ),
            )
        )
        monkeypatch.setattr(pkghandler, "get_packages_to_remove", GetPackagesToRemoveMocked(pkg_selection="key_ids"))
        monkeypatch.setattr(
            handle_packages,
            "_remove_packages_unless_from_redhat",
            RemovePkgsUnlessFromRedhatMocked(return_value=pkgs_removed),
        )
        monkeypatch.setattr(pkgmanager, "TYPE", "dnf")
        remove_special_packages_instance.run()

        assert expected.issuperset(remove_special_packages_instance.messages)
        assert expected.issubset(remove_special_packages_instance.messages)
        assert pkghandler.get_packages_to_remove.call_count == 2
        assert handle_packages._remove_packages_unless_from_redhat.call_count == 1
        assert remove_special_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]

    def test_run_packages_error(self, monkeypatch, remove_special_packages_instance):
        monkeypatch.setattr(
            pkghandler, "get_packages_to_remove", mock.Mock(side_effect=SystemExit("Raising SystemExit"))
        )
        remove_special_packages_instance.run()

        unit_tests.assert_actions_result(
            remove_special_packages_instance,
            level="ERROR",
            id="SPECIAL_PACKAGE_REMOVAL_FAILED",
            title="Failed to remove some packages necessary for the conversion.",
            description="The cause of this error is unknown, please look at the diagnosis for more information.",
            diagnosis="Raising SystemExit",
        )


def test_remove_packages_unless_from_redhat_no_pkgs(caplog):
    assert not handle_packages._remove_packages_unless_from_redhat(pkgs_list=[])
    assert "\nNothing to do." in caplog.records[-1].message


def test_remove_packages_unless_from_redhat(pkgs_to_remove, monkeypatch, caplog):
    monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    handle_packages._remove_packages_unless_from_redhat(pkgs_list=pkgs_to_remove)

    assert "Removing the following %s packages" % len(pkgs_to_remove) in caplog.records[-3].message
    assert "Successfully removed %s packages" % len(pkgs_to_remove) in caplog.records[-1].message
