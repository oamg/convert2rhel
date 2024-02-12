import pytest


@pytest.mark.test_rhsm_facts_called_in_analysis
def test_rhsm_facts_called_after_analysis(convert2rhel, pre_registered):
    """
    ...
    """
    with convert2rhel("analyze -y --debug") as c2r:
        # Verify that the analysis report is printed
        c2r.expect("Updating RHSM custom facts collected during the conversion.", timeout=600)
        c2r.expect("RHSM custom facts uploaded successfully.", timeout=600)

    # The analysis should exit with 0, if it finishes successfully
    assert c2r.exitstatus == 0
