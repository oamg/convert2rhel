import sys

import pexpect

from envparse import env

def test_remove_all_submgr_pkgs(shell):
    """Test that all subscription-manager pkgs (no matter the signature) get removed.
    
    And that the system is unregistered before that.
    """

    c2r = pexpect.spawn(
        (
            "convert2rhel --no-rpm-va "
            "--serverurl {} --username {} "
            "--password {} --pool {} "
            "--debug -y"
        ).format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        encoding="utf-8",
        timeout=30 * 60, # The conversion can take a long time
    )

    c2r.logfile_read = sys.stdout

    with open('/etc/system-release', 'r') as file:
        system_release = file.read()

    if "Oracle Linux Server release 7" in system_release:  # We're not installing sub-mgr on OL 7
        c2r.expect("The subscription-manager package is not installed.")
    else:  # All other tests systems
        # Check that the system is unregistered before removing the sub-mgr
        c2r.expect("Calling command 'subscription-manager unregister'")
        # Check that the pre-installed sub-mgr gets removed
        c2r.expect("Calling command 'rpm -e --nodeps subscription-manager'")
    # Just to make sure the above output appeared before installing the subscription-manager pkgs
    c2r.expect("Installing subscription-manager RPMs.")

    c2r.expect(pexpect.EOF)  # Wait for the conversion to finish
    c2r.close()  # Per the pexpect API, this is necessary in order to get the return code
    assert c2r.exitstatus == 0
    shell("subscription-manager unregister")

    # Check that the subscription-manager installed by c2r has the Red Hat signature
    assert "199e2f91fd431d51" in shell("rpm -q --qf '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:"
                                       "{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{(none)}|}|' "
                                       "subscription-manager").output
