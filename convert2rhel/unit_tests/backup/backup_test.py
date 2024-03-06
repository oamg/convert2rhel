__metaclass__ = type

import pytest

from convert2rhel import backup
from convert2rhel.unit_tests import ErrorOnRestoreRestorable, MinimalRestorable


@pytest.fixture
def backup_controller():
    return backup.BackupController()


class TestBackupController:
    def test_push(self, backup_controller, restorable):
        backup_controller.push(restorable)

        assert restorable.called["enable"] == 1
        assert restorable in backup_controller._restorables

    def test_push_invalid(self, backup_controller):
        with pytest.raises(TypeError, match="`1` is not a RestorableChange object"):
            backup_controller.push(1)

    def test_pop(self, backup_controller, restorable):
        backup_controller.push(restorable)
        popped_restorable = backup_controller.pop()

        assert popped_restorable is restorable
        assert restorable.called["restore"] == 1

    def test_pop_multiple(self, backup_controller):
        restorable1 = MinimalRestorable()
        restorable2 = MinimalRestorable()
        restorable3 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(restorable2)
        backup_controller.push(restorable3)

        popped_restorable3 = backup_controller.pop()
        popped_restorable2 = backup_controller.pop()
        popped_restorable1 = backup_controller.pop()

        assert popped_restorable1 is restorable1
        assert popped_restorable2 is restorable2
        assert popped_restorable3 is restorable3

        assert restorable1.called["restore"] == 1
        assert restorable2.called["restore"] == 1
        assert restorable3.called["restore"] == 1

    def test_pop_when_empty(self, backup_controller):
        with pytest.raises(IndexError, match="No backups to restore"):
            backup_controller.pop()

    def test_pop_all(self, backup_controller):
        restorable1 = MinimalRestorable()
        restorable2 = MinimalRestorable()
        restorable3 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(restorable2)
        backup_controller.push(restorable3)

        restorables = backup_controller.pop_all()

        assert len(restorables) == 3
        assert restorables[0] is restorable3
        assert restorables[1] is restorable2
        assert restorables[2] is restorable1

        assert restorable1.called["restore"] == 1
        assert restorable2.called["restore"] == 1
        assert restorable3.called["restore"] == 1

    def test_ready_to_push_after_pop_all(self, backup_controller):
        restorable1 = MinimalRestorable()
        restorable2 = MinimalRestorable()

        backup_controller.push(restorable1)
        popped_restorables = backup_controller.pop_all()
        backup_controller.push(restorable2)

        assert len(popped_restorables) == 1
        assert popped_restorables[0] == restorable1
        assert len(backup_controller._restorables) == 1
        assert backup_controller._restorables[0] is restorable2

    def test_pop_all_when_empty(self, backup_controller):
        with pytest.raises(IndexError, match="No backups to restore"):
            backup_controller.pop_all()

    def test_pop_all_error_in_restore(self, backup_controller, caplog):
        restorable1 = MinimalRestorable()
        restorable2 = ErrorOnRestoreRestorable(exception=ValueError("Restorable2 failed"))
        restorable3 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(restorable2)
        backup_controller.push(restorable3)

        popped_restorables = backup_controller.pop_all()

        assert len(popped_restorables) == 3
        assert popped_restorables == [restorable3, restorable2, restorable1]
        assert caplog.records[-1].message == "Error while rolling back a ErrorOnRestoreRestorable: Restorable2 failed"

    # The following tests are for the 1.4 kludge to split restoration via
    # backup_controller into two parts.  They can be removed once we have
    # all rollback items ported to use the BackupController and the partition
    # code is removed.

    def test_pop_with_partition(self, backup_controller):
        restorable1 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(backup_controller.partition)

        restorable = backup_controller.pop()

        assert restorable == restorable1
        assert backup_controller._restorables == []

    def test_pop_all_with_partition(self, backup_controller):
        restorable1 = MinimalRestorable()
        restorable2 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(backup_controller.partition)
        backup_controller.push(restorable2)

        restorables = backup_controller.pop_all()

        assert restorables == [restorable2, restorable1]

    def test_pop_to_partition(self, backup_controller):
        restorable1 = MinimalRestorable()
        restorable2 = MinimalRestorable()

        backup_controller.push(restorable1)
        backup_controller.push(backup_controller.partition)
        backup_controller.push(restorable2)

        assert backup_controller._restorables == [restorable1, backup_controller.partition, restorable2]

        backup_controller.pop_to_partition()

        assert backup_controller._restorables == [restorable1]

        backup_controller.pop_to_partition()

        assert backup_controller._restorables == []

    # End of tests that are for the 1.4 partition hack.
