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
# Tests location: convert2rhel/tests

# -- SPECIFIC TESTS EXECUTION --
# To execute specific tests only, add the tests as arguments to this script.
# Example:
# ./run_unit_tests.sh convert2rhel.tests.example_test:TestExample.test_example

# -- CODE COVERAGE --
# To see how much of the convert2rhel python code is covered by tests:
# 1. python-coverage package needs to be installed
# 2. Uncomment the following line:
#GET_COVERAGE="--cover-package=convert2rhel --with-coverage --cover-html"

# -- TEST OUTPUT --
# To let the tests print to stdout, uncomment the following line:
#TEST_OUTPUT="--nocapture"

# -- CLEAR LOGGING HANDLERS --
# Clear existing logging handlers because our custom logging class creates them
#CLEAR_HANDLERS="--logging-clear-handlers"

VIRTUALENV=.venv

command -v pip >/dev/null 2>&1 || {
    echo >&2 "python-pip package required. Aborting.";
    exit 1;
}
command -v virtualenv >/dev/null 2>&1 || {
    echo >&2 "python-virtualenv package required. Aborting.";
    exit 1;
}

virtualenv --python=python2.7 $VIRTUALENV
source $VIRTUALENV/bin/activate
pip install -r convert2rhel/unit_tests/requirements.txt

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pushd $SCRIPT_DIR > /dev/null
nosetests -v $GET_COVERAGE $TEST_OUTPUT $CLEAR_HANDLERS $REDNOSE "$@"
ret_code=$?
popd > /dev/null

exit $ret_code # Exit the script with the code returned by nosetests
