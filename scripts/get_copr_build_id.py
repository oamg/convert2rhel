#!/usr/bin/env python3

import json
import os
import re
import sys

import copr.v3


ENV_VARS = {
    "_COPR_CONFIG": "~/.config/copr",  # Copr config file. Get it through https://<copr instance>/api/.
    "COPR_OWNER": "@oamg",  # Owner of the Copr project
    "COPR_PROJECT": "convert2rhel",  # The Copr project to search
    "COPR_PACKAGE": "",  # Name of the package to look for. This is optional - if empty, any package in the
    # project is considered.
    "REGEX": "",  # A more general way to search for release_id matches via regex. Generalization of PKG_RELEASE
}
# override defaults with environment variables
for env, default in ENV_VARS.items():
    ENV_VARS[env] = os.getenv(env, default)


def get_builds(ownername, projectname, configpath, client=None, debug=False):
    """ """
    client = client or copr.v3.Client(copr.v3.config_from_file(path=configpath))
    builds = client.build_proxy.get_list(
        status="succeeded",
        pagination={"order": "id", "order_type": "DESC"},
        ownername=ownername,
        projectname=projectname,
        packagename=ENV_VARS["COPR_PACKAGE"],
    )
    if debug:
        json.dump(builds, sys.stderr, sort_keys=True, indent=2)
        sys.stderr.write("\n")
    return builds


def get_latest_build(ownername, projectname, configpath, match_criteria, client=None, debug=False):
    """ """
    client = client or copr.v3.Client(copr.v3.config_from_file(path=configpath))
    builds = get_builds(ownername, projectname, configpath, client, debug)
    for build in builds:
        # Version in COPR contains VERSION-RELEASE string. We need just the release.
        full_name = "{}-{}".format(build["source_package"]["name"], build["source_package"]["version"])
        release = build["source_package"]["version"].split("-")[-1]
        if re.match(match_criteria, full_name) or release.startswith(match_criteria):
            return build["id"]
    return None


def _fail(error):
    """ """
    if not error.endswith("\n"):
        error += "\n"
    sys.stderr.write(error)
    # dump ENV dictionary
    sys.stderr.write("Passed (or default) environment variables:\n")
    for var, value in ENV_VARS.items():
        sys.stderr.write("  {}: {}\n".format(var, value))
    sys.exit(1)


def main():
    build_id = get_latest_build(
        ENV_VARS["COPR_OWNER"],
        ENV_VARS["COPR_PROJECT"],
        ENV_VARS["_COPR_CONFIG"],
        ENV_VARS["REGEX"],
        debug="--debug" in sys.argv[1:],
    )

    if not build_id:
        error_msg = "Error: The build with the required release has not been found: {}".format(ENV_VARS["REGEX"])
        _fail(error_msg)

    # Output the id of the latest matching build
    print(build_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
