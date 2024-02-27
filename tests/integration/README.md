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

## Run integration test

### Pull Request

The easies way to run integration test is by opening a Pull Request. Packit
will then run it by using a Testing Farm.

### tmt

`tmt` offers multiple ways how to run an integration test. Provided options
defines what OS is provisioned and where.

E.g. to provision a CentOS 7 virtual machine locally, we need:

- setup `context`:  `--context distro=centos-7`
- use `virtual` provider: `--how virtual`
- provide the cloud image for the os: e.g., `--image https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2`

It is possible to issue a rebuild of rpm package and using it in the test by
defining `ANSIBLE_BUILD_RPM=build` and `ANSIBLE_RPM_PROVIDER=local` variables
to be provided as env vars to the executed tasks by `tmt`.

Example:

```
tmt \
       --context distro=centos-7 \
       run \
          -vvv --all \
          -e ANSIBLE_BUILD_RPM=build \
          -e ANSIBLE_RPM_PROVIDER=local \
       provision \
          --how virtual  \
          --image https://cloud.centos.org/centos/7/images/CentOS-7-x86_64-GenericCloud.qcow2 \
       plan \
         --name $TEST_PLAN_NAME
```
