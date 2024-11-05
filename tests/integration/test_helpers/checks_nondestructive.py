import os
import re

import pytest

from test_helpers.common_functions import get_log_file_data


@pytest.fixture(autouse=True)
def check_validate_deprecated_envar_message():
    """
    Check fixture.
    Validate that the warning message for deprecated environment variables is present,
    if the respective environment variable is used.
    """

    yield

    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        missing_envar_messages = []
        log_file_data = get_log_file_data()
        for key in os.environ.keys():
            if re.match("CONVERT2RHEL_", key):
                if not re.search(f"The environment variable {key} is deprecated", log_file_data):
                    missing_envar_messages.append(key)
        if missing_envar_messages:
            pytest.fail(f"The warning message for deprecated envars {missing_envar_messages} is not not present.")
