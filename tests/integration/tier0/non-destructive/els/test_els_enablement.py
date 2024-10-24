import os.path

import pytest

from conftest import TEST_VARS


@pytest.fixture
def els_mock(shell, backup_directory):
    """
    Fixture to mock different scenarios while handling the ELS candidates.
    Backs up the convert2rhel/systeminfo.py and modifies the ELS_RELEASE_DATE variable.
    Restores the original version after the test is done.
    """
    systeminfo_file = shell("find /usr -path '*/convert2rhel/systeminfo.py'").output.strip()
    bak_systeminfo_file = os.path.join(backup_directory, "systeminfo.py.bkp")
    assert shell(f"cp {systeminfo_file} {bak_systeminfo_file}").returncode == 0

    original_startdate_value = '"2024-06-12"'
    original_releasever_value = "if tool_opts.els and self.version.major == 7:"

    def _update_els_mapping(modified_startdate=None, modified_releasever=None):
        if modified_startdate:
            shell(f"sed -i 's/{original_startdate_value}/{modified_startdate}/' {systeminfo_file}")
        if modified_releasever:
            shell(f"sed -i 's/{original_releasever_value}/{modified_releasever}/' {systeminfo_file}")

    yield _update_els_mapping

    def _restore_els_mapping():
        assert shell(f"mv -v {bak_systeminfo_file} {systeminfo_file}").returncode == 0

    _restore_els_mapping()


REGULAR_REPOID_MSG = "RHEL repository IDs to enable: rhel-7-server-rpms"
ELS_REPOID_MSG = "RHEL repository IDs to enable: rhel-7-server-els-rpms"

MOCKED_ELS_PHASE = '"1970-01-01"'
MOCKED_NON_ELS_SYSVER = "if tool_opts.els and self.version.major == 42:"


els_enablement_parameters = [
    # System not recognized as an ELS candidate with --els option used
    ("--els", REGULAR_REPOID_MSG, None, MOCKED_NON_ELS_SYSVER, False),
    # System recognized as an ELS candidate after the start of ELS phase without --els option
    ("", REGULAR_REPOID_MSG, MOCKED_ELS_PHASE, None, True),
]


@pytest.mark.parametrize(
    "additional_option, repoid_message, modified_startdate, modified_releasever, recommend_els_msg_displayed",
    els_enablement_parameters,
    ids=["non-els-system-els-option-used", "els-system-els-phase-started-no-option-used"],
)
def test_els_enablement(
    convert2rhel,
    fixture_subman,
    els_mock,
    additional_option,
    repoid_message,
    modified_startdate,
    modified_releasever,
    recommend_els_msg_displayed,
):
    """
    Test verifying correct behavior when converting ELS candidates.
    ELS_RELEASE_DATE in convert2rhel/systeminfo.py is modified to mock the different scenarios.
    Verified scenarios (handled by pytest parametrization):
    1/ The system is considered as a non-ELS. This is done by modifying the major system version
        in the els.py file.
        The --els option is used in the command. Only regular (non-els) repoids should be enabled.
    2/ The start date of the ELS phase is set far to the past to simulate the ELS phase began.
        The --els option *is used*.
        The report is expected to print out a WARNING and advise to use the --els option.
    """
    els_mock(modified_startdate, modified_releasever)
    with convert2rhel(
        "analyze -y --debug -u {} -p {} {}".format(
            TEST_VARS["RHSM_SCA_USERNAME"], TEST_VARS["RHSM_SCA_PASSWORD"], additional_option
        )
    ) as c2r:
        c2r.expect(repoid_message, timeout=300)
        # If the system is an ELS candidate and current date is past the beginning of the ELS phase
        # we set the recommend_els_msg_displayed parameter to True
        # We expect the report to print out a warning to use --els option
        if recommend_els_msg_displayed:
            c2r.expect("ELS_SYSTEM_CHECK::ELS_COMMAND_LINE_OPTION_UNUSED")
        else:
            c2r.expect("Repositories enabled through subscription-manager", timeout=120)
            c2r.sendcontrol("c")


def test_rhsm_non_els_account(convert2rhel):
    """
    Verify that Convert2RHEL is working properly when ELS repositories are not available for conversions
    (the account does not have the ELS SKU available) to RHEL ELS version (7.9)
    and the --els option is provided. The regular repositories should be enabled as a fallback option.
    We're deliberately using SCA disabled account for this scenario.
    """

    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug --els".format(
            TEST_VARS["RHSM_SERVER_URL"],
            # We're deliberately using SCA disabled account for this
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
        )
    ) as c2r:
        c2r.expect_exact(ELS_REPOID_MSG)
        c2r.expect_exact("Error: 'rhel-7-server-els-rpms' does not match a valid repository ID.")
        c2r.expect_exact("SUBSCRIBE_SYSTEM::FAILED_TO_ENABLE_RHSM_REPOSITORIES")
    assert c2r.exitstatus == 2
