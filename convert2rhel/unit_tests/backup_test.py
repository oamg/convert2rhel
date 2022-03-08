import os
import sys
import unittest

import pytest

from convert2rhel import backup, unit_tests, utils  # Imports unit_tests/__init__.py


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


class TestBackup(unittest.TestCase):
    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output="Test output", ret_code=0):
            self.cmd = []
            self.cmds = []
            self.called = 0
            self.output = output
            self.ret_code = ret_code

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            self.cmds.append(cmd)
            self.called += 1
            return self.output, self.ret_code

    class DummyFuncMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kargs):
            self.called += 1

    class RemovePkgsMocked(unit_tests.MockFunction):
        def __init__(self):
            self.pkgs = None
            self.should_bkp = False
            self.critical = False

        def __call__(self, pkgs_to_remove, backup=False, critical=False):
            self.pkgs = pkgs_to_remove
            self.should_bkp = backup
            self.critical = critical

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_with_empty_list(self):
        backup.remove_pkgs([])
        self.assertEqual(utils.run_subprocess.called, 0)

    @unit_tests.mock(backup.changed_pkgs_control, "backup_and_track_removed_pkg", DummyFuncMocked())
    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_without_backup(self):
        pkgs = ["pkg1", "pkg2", "pkg3"]
        backup.remove_pkgs(pkgs, False)
        self.assertEqual(backup.changed_pkgs_control.backup_and_track_removed_pkg.called, 0)

        self.assertEqual(backup.run_subprocess.called, len(pkgs))

        rpm_remove_cmd = ["rpm", "-e", "--nodeps"]
        for cmd, pkg in zip(backup.run_subprocess.cmds, pkgs):
            self.assertEqual(rpm_remove_cmd + [pkg], cmd)

    @unit_tests.mock(backup.ChangedRPMPackagesController, "backup_and_track_removed_pkg", DummyFuncMocked())
    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_with_backup(self):
        pkgs = ["pkg1", "pkg2", "pkg3"]
        backup.remove_pkgs(pkgs)
        self.assertEqual(backup.ChangedRPMPackagesController.backup_and_track_removed_pkg.called, len(pkgs))

        self.assertEqual(backup.run_subprocess.called, len(pkgs))

        rpm_remove_cmd = ["rpm", "-e", "--nodeps"]
        for cmd, pkg in zip(backup.run_subprocess.cmds, pkgs):
            self.assertEqual(rpm_remove_cmd + [pkg], cmd)

        def test_track_installed_pkg(self):
            control = backup.ChangedRPMPackagesController()
            pkgs = ["pkg1", "pkg2", "pkg3"]
            for pkg in pkgs:
                control.track_installed_pkg(pkg)
            self.assertEqual(control.installed_pkgs, pkgs)

    @unit_tests.mock(backup.RestorablePackage, "backup", DummyFuncMocked())
    def test_backup_and_track_removed_pkg(self):
        control = backup.ChangedRPMPackagesController()
        pkgs = ["pkg1", "pkg2", "pkg3"]
        for pkg in pkgs:
            control.backup_and_track_removed_pkg(pkg)
        self.assertEqual(backup.RestorablePackage.backup.called, len(pkgs))
        self.assertEqual(len(control.removed_pkgs), len(pkgs))

    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    def test_install_local_rpms_with_empty_list(self):
        backup.changed_pkgs_control._install_local_rpms([])
        self.assertEqual(backup.run_subprocess.called, 0)

    @unit_tests.mock(backup.changed_pkgs_control, "track_installed_pkg", DummyFuncMocked())
    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    def test_install_local_rpms_without_replace(self):
        pkgs = ["pkg1", "pkg2", "pkg3"]
        backup.changed_pkgs_control._install_local_rpms(pkgs)
        self.assertEqual(backup.changed_pkgs_control.track_installed_pkg.called, len(pkgs))

        self.assertEqual(backup.run_subprocess.called, 1)
        self.assertEqual(["rpm", "-i", "pkg1", "pkg2", "pkg3"], backup.run_subprocess.cmd)

    @unit_tests.mock(backup.changed_pkgs_control, "track_installed_pkg", DummyFuncMocked())
    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    def test_install_local_rpms_with_replace(self):
        pkgs = ["pkg1", "pkg2", "pkg3"]
        backup.changed_pkgs_control._install_local_rpms(pkgs, replace=True)
        self.assertEqual(backup.changed_pkgs_control.track_installed_pkg.called, len(pkgs))

        self.assertEqual(backup.run_subprocess.called, 1)
        self.assertEqual(["rpm", "-i", "--replacepkgs", "pkg1", "pkg2", "pkg3"], backup.run_subprocess.cmd)


@pytest.mark.parametrize(
    ("filepath", "backup_dir", "file_content", "expected"),
    (("test.rpm", "backup", "test", None), ("test.rpm", "backup", "", "Can't find")),
)
def test_restorable_file_backup(filepath, backup_dir, file_content, expected, tmpdir, monkeypatch, caplog):
    tmp_file = tmpdir.join(filepath)
    tmp_backup = tmpdir.mkdir(backup_dir)
    if file_content:
        tmp_file.write(file_content)

    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_backup)
    rf = backup.RestorableFile(filepath=tmp_file)
    rf.backup()

    if expected:
        assert expected in caplog.records[-1].message


def test_restorable_file_backup_oserror(tmpdir, caplog):
    tmp_file = tmpdir.join("test.rpm")
    tmp_file.write("test")
    rf = backup.RestorableFile(filepath=tmp_file)

    with pytest.raises(SystemExit):
        rf.backup()

    assert "Error(2): No such file or directory" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("filepath", "backup_dir", "file_content", "expected"),
    (("test.rpm", "backup", "test", "File {} restored"), ("test.rpm", "backup", "", "{} hasn't been backed up")),
)
def test_restorable_file_restore(filepath, backup_dir, file_content, expected, tmpdir, monkeypatch, caplog):
    tmp_backup = tmpdir
    tmp_file = tmpdir.join(filepath)
    tmp_backup = tmp_backup.mkdir(backup_dir).join(filepath)
    if file_content:
        tmp_backup.write(file_content)

    monkeypatch.setattr(backup, "BACKUP_DIR", os.path.dirname(tmp_backup))
    rf = backup.RestorableFile(filepath=tmp_file)
    rf.restore()

    if expected:
        assert expected.format(tmp_backup) in caplog.records[-1].message


def test_restorable_file_restore_oserror(tmpdir, caplog, monkeypatch):
    tmp_backup = tmpdir
    tmp_backup = tmp_backup.mkdir("backup").join("test.rpm")
    tmp_backup.write("test")

    monkeypatch.setattr(backup, "BACKUP_DIR", os.path.dirname(tmp_backup))

    rf = backup.RestorableFile(filepath=tmp_backup)
    rf.restore()

    # Source and dest files are the same, which throws this error
    assert "Error(None): None" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("pkgs_to_remove", "ret_code", "backup_pkg", "critical", "expected"),
    ((["pkg1"], 1, False, True, "Error: Couldn't remove {}."), (["pkg1"], 1, False, False, "Couldn't remove {}.")),
)
def test_remove_pkgs_failed_to_remove(pkgs_to_remove, ret_code, backup_pkg, critical, expected, monkeypatch, caplog):
    run_subprocess_mock = mock.Mock(
        side_effect=unit_tests.run_subprocess_side_effect(
            (("rpm", "-e", "--nodeps", pkgs_to_remove[0]), ("test", ret_code)),
        )
    )
    monkeypatch.setattr(
        backup,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    if critical:
        with pytest.raises(SystemExit):
            backup.remove_pkgs(pkgs_to_remove=pkgs_to_remove, backup=backup_pkg, critical=critical)
    else:
        backup.remove_pkgs(pkgs_to_remove=pkgs_to_remove, backup=backup_pkg, critical=critical)

    assert expected.format(pkgs_to_remove[0]) in caplog.records[-1].message
