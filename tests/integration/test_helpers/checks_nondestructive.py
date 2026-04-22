import os
import re

import pytest

from test_helpers.common_functions import get_log_file_data
from test_helpers.vars import SYSTEM_RELEASE_ENV


@pytest.fixture(autouse=True)
def check_validate_deprecated_envar_message(request):
    """
    Check fixture.
    Validate that the warning message for deprecated environment variables is present,
    if the respective environment variable is used.
    """

    yield

    # We're using multiple envars in the amzn2 tests globally and the tests usually don't even get to the point of
    # the deprecation message, disable for whole instead of listing the nodes
    if SYSTEM_RELEASE_ENV == "amazon2":
        return

    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        missing_envar_messages = []
        log_file_data = get_log_file_data()
        for key in os.environ.keys():
            if re.match("CONVERT2RHEL_", key):
                if not re.search(f"The environment variable {key} is deprecated", log_file_data):
                    missing_envar_messages.append(key)
        if missing_envar_messages:
            pytest.fail(f"The warning message for deprecated envars {missing_envar_messages} is not not present.")
