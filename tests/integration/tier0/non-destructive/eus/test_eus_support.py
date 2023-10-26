import os.path

import pytest

from envparse import env


@pytest.fixture
def eus_mapping_update(shell):
    """
    Fixture to mock different scenarios while handling the EUS candidates.
    Backs up the convert2rhel/systeminfo.py and modifies the EUS_MINOR_VERISONS mapping.
    Restores the original version after the test is done.
    """
    eus_mapping_file = shell("find /usr -path '*/convert2rhel/systeminfo.py'").output.strip()
    backup_dir = "/tmp/c2r_tests_backup/"
    backup_file = f"{backup_dir}systeminfo.py.bkp"
    if not os.path.exists(backup_dir):
        shell(f"mkdir {backup_dir}")
    assert shell(f"cp {eus_mapping_file} {backup_file}").returncode == 0

    original_mapping_value = '"8.8": "2023-11-14",'

    def _update_eus_mapping(modified_mapping):
        shell(f"sed -i 's/{original_mapping_value}/{modified_mapping}/' {eus_mapping_file}")

    yield _update_eus_mapping

    def _restore_eus_mapping():
        assert shell(f"mv {backup_file} {eus_mapping_file}").returncode == 0

    _restore_eus_mapping()


REGULAR_REPOID_MSG = "RHEL repository IDs to enable: rhel-8-for-x86_64-baseos-rpms, rhel-8-for-x86_64-appstream-rpms"
EUS_REPOID_MSG = (
    "RHEL repository IDs to enable: rhel-8-for-x86_64-baseos-eus-rpms, rhel-8-for-x86_64-appstream-eus-rpms"
)

EUS_SYS_PRE_EUS_PHASE = '"8.8": "2042-04-08",'
EUS_SYS_EUS_PHASE = '"8.8": "1970-01-01",'


eus_support_parameters = [
    # System not recognized as an EUS candidate with --eus option used
    ("--eus", REGULAR_REPOID_MSG, "", False, False),
    # System recognized as and EUS candidate before the start of EUS phase without --eus option
    ("", REGULAR_REPOID_MSG, EUS_SYS_PRE_EUS_PHASE, False, False),
    # System recognized as and EUS candidate before the start of EUS phase with --eus option
    ("--eus", EUS_REPOID_MSG, EUS_SYS_PRE_EUS_PHASE, True, False),
    # System recognized as and EUS candidate after the start of EUS phase without --eus option
    ("", REGULAR_REPOID_MSG, EUS_SYS_EUS_PHASE, False, True),
]


@pytest.mark.parametrize(
    "additional_options, repoid_message, modified_mapping, is_eus, eus_recommend",
    eus_support_parameters,
    ids=["non-eus-sys-eus-opt", "eus-sys-pre-eus-no-opt", "eus-sys-pre-eus-eus-opt", "eus-sys-eus-phase-no-opt"],
)
@pytest.mark.test_eus_support
def test_eus_support(
    convert2rhel, eus_mapping_update, additional_options, repoid_message, modified_mapping, is_eus, eus_recommend
):
    """
    Test verifying correct behavior when converting EUS candidates.
    EUS_MINOR_VERISONS mapping in convert2rhel/systeminfo.py is modified to mock the different scenarios.
    Verified scenarios (handled by patest parametrization):
    1/ The running minor version is removed from the mapping to not be considered an EUS candidate.
        The --eus option is used in the command and enabling regular (non-eus) repoids is verified.
    2/ The date of the start of the EUS phase is set far to the future to simulate the EUS phase
        did not start yet.
        The --eus option *is not used* and regular repoids enablement is expected.
    3/ The date of the start of the EUS phase is set far to the future to simulate the EUS phase
        did not start yet.
        The --eus option *is used* and EUS repoids enablement is expected.
    4/ The date of the start of the EUS phase is set far to the past to simulate the EUS phase began.
        The --eus option *is used*.
        The report is expected to print out a WARNING and advise to use the --eus option.
    """
    eus_mapping_update(modified_mapping)
    with convert2rhel(
        "analyze -y --debug --no-rpm-va --serverurl {} -u {} -p {} {}".format(
            env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD"), additional_options
        )
    ) as c2r:
        # If the system is an EUS candidate and current date is past the beginning of the EUS phase
        # we set the eus_recommend parameter to True
        # We expect the report to print out a warning to use --eus option
        if eus_recommend:
            c2r.expect(repoid_message, timeout=120)
            c2r.expect("EUS_SYSTEM_CHECK::EUS_COMMAND_LINE_OPTION_UNUSED")
        else:
            c2r.expect(repoid_message, timeout=120)
            # In case the EUS repositories should get enabled, we set is_eus parameter to True
            if is_eus:
                c2r.expect_exact(
                    "The system version corresponds to a RHEL Extended Update Support (EUS) release.",
                    timeout=120,
                )
            c2r.expect("Repositories enabled through subscription-manager", timeout=120)
            c2r.sendcontrol("c")
