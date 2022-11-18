C2R_LOG = "/var/log/convert2rhel/convert2rhel.log"


def test_verify_logfile_starts_with_command(shell):
    """
    This test verifies, that the command passed to the command line is at the beginning of the log file.
    Also verify, that the passed password is obfuscated.
    """
    serverurl = "subscription.pls.register.me"
    username = "jdoe"
    password = "foobar"
    activationkey = "a-map-of-a-key"

    command_long = (
        "convert2rhel --debug --no-rpm-va --serverurl {} --username {} --password {} --activationkey {}".format(
            serverurl, username, password, activationkey
        )
    )
    command_short = "convert2rhel --debug --no-rpm-va --serverurl {} -u {} -p {} -k {}".format(
        serverurl, username, password, activationkey
    )

    command_verification = "convert2rhel --debug --no-rpm-va --serverurl {}".format(serverurl)

    commands = [command_long, command_short]

    # Run command twice with both long and short options to verify, the secrets are obfuscated.
    for command in commands:
        # There is no need to run the conversion past the first prompt
        # pass the command with appending 'n'
        assert shell(f"{command} <<< n").returncode != 0

        with open(C2R_LOG, "r") as logfile:
            command_line = None
            for i, line in enumerate(logfile):
                # The actual command is logged to a second line
                if i == 1:
                    command_line = line.strip()
                    break

            assert command_verification in command_line
            assert password not in command_line
            assert activationkey not in command_line
