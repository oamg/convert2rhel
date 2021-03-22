from envparse import env

from . import shell


def main():
    shell(
        command=[
            (
                "convert2rhel -y "
                "--serverurl {} --username {} "
                "--password {} --pool {} "
                "--debug"
            ).format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ]
    )


__name__ == "__main__" and main()
