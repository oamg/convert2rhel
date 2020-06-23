#!/bin/bash
# -- DESCRIPTION --
# This script executes by default all the existing tests for the convert2rhel
# tool. Optionally it executes just specific tests passed as arguments.

# -- CONVENTION --
# To have the nosetests command execute our tests, the following rules shall
# be adhered to:
# - name of the test file shall:
#   -- start with the name of the original file to be tested
#   -- end with '_test.py'
# - name of each test method (within a class derived from unittest.TestCase)
#   shall start with 'test_' prefix
# - name of the class derived from unittest.TestCase can be arbitrary
# Tests location: convert2rhel/unit_tests

# -- SPECIFIC TESTS EXECUTION --
# To execute specific tests only, add the tests as arguments to this script.
# Example:
# ./run_unit_tests.sh convert2rhel.tests.example_test:TestExample.test_example

# -- TEST OUTPUT --
# To let the tests print to stdout, uncomment the following line:
#TEST_OUTPUT="--nocapture"

# Determine Python version
if command -v python3 -v >/dev/null 2>&1; then
    PYTHON=3
elif command -v python2 -v >/dev/null 2>&1; then
    PYTHON=2
    # Make sure nosetests are installed for Py2 tests
    command -v nosetests >/dev/null 2>&1 || {
        echo >&2 "Nose PyPI package required. Aborting.";
        exit 1;
    }
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pushd $SCRIPT_DIR > /dev/null
if [[ $PYTHON = 2 ]]; then
    nosetests -v $TEST_OUTPUT "$@"
elif [[ $PYTHON = 3 ]]; then
    nosetests-3 -v $TEST_OUTPUT "$@"
else
    echo "Error: Python version not determined"
    exit 1
fi
ret_code=$?
popd > /dev/null

exit $ret_code # Exit the script with the code returned by nosetests
