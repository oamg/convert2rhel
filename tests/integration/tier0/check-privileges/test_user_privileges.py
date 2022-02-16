import os


def test_check_user_privileges(shell):
    user = "testuser"
    # Create non-root user if not created already
    os.system(f"useradd '{user}'")
    # Set user to non-root entity 'testuser' and run c2r
    result = shell("runuser -l testuser -c 'convert2rhel'")
    # Check the program exits as it is required to be run by root
    assert result.returncode != 0
    # Check the program exits for the correct reason
    assert (
        result.output == "The tool needs to be run under the root user.\n" "\n" "No changes were made to the system.\n"
    )
    # Delete testuser (if present)
    os.system(f"userdel -r '{user}'")
