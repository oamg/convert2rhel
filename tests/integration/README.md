# Integration tests

The general idea of our integration tests is to run the Convert2RHEL tool as a
black box and look for explicit outputs given a system state and inputs - like
environment variables and CLI parameters.

Usually, the integration tests are written by the QE team in Convert2RHEL using
all the best practices they already have for integration tests, but every
developer can help them to write the integration tests as well.

The structure of the integration tests can be found in the
[convert2rhel/plans](https://github.com/oamg/convert2rhel/tree/main/plans)
folder. Plans define the testing environment, how to prepare it and which tests
to run within this environment (filtering tests based on tags).

We use the [fmf](https://fmf.readthedocs.io/en/stable/index.html) format to
define testing plans and tests. Tests are then executed using the
[tmt](https://tmt.readthedocs.io/en/stable/index.html) tool.

Tests themselves are written mostly in `Python`. However, one can write the
integration test in any other language, eg. in `Bash`.

Finally, you can find out all the integration tests for Convert2RHEL in the
[convert2rhel/tests](https://github.com/oamg/convert2rhel/tree/main/tests)
folder.
