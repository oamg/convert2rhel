import re

import click


@click.command()
@click.argument("spec_path")
def get_convert2rhel_version(spec_path: str) -> None:
    """Parse rpm spec file and returns its name-version-release part.

    Example:
    ```bash
    python scripts/extract_version_from_rpm_spec.py packaging/convert2rhel.spec
    # 0.21-1
    ```

    """
    with open(spec_path) as rpm_f:
        try:
            click.echo(
                "-".join(
                    re.findall(
                        r"""
                        # Line which starts with these words
                        ^(?:Version|Release):
                        # Spaces afterwards
                        \s+
                        # capturing group which we are interested in
                        (
                            # Any word could be here
                            (?:\w+)|
                            # Or int or float i.e. 21 or 0.21
                            (?:\d+[.]*\d*)
                        )
                        # some special internal rpm spec var (skipping it)
                        (?:%{.+)*$
                        """,
                        rpm_f.read(),
                        flags=(re.MULTILINE | re.VERBOSE),
                    )
                ),
            )
        except Exception as e:
            raise click.ClickException(repr(e)) from e


__name__ == "__main__" and get_convert2rhel_version()
