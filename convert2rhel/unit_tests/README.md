# Unit testing in Convert2RHEL

In this file, you will understand a bit more the key concepts for working with
unit tests in Convert2RHEL, such as:

* Writing unit tests
* Running the tests (Container / Locally)
* Coverage

## Getting started

To start interacting with the project's unit tests, you first need to do a
simple setup on your machine, this setup is basically to install some
dependencies on your `virtualenv` and build the docker images.

The only thing you have to do is run the following command in your terminal
(You must be inside the project's root directory):

```bash
# Install dependencies, pre-commit and container images
make install
```

This command can take a while to finish, depending on your internet connection.
After finishing, the command will create some hidden files in the root
directory, such as `.install`, `.pre-commit`, `.images` and so on... Don't
worry, this is just a way to tell `make` to not run the same commands over and
over if you try.

## Writing unit tests

Unit tests basically consist of testing small units of code, either a function
call or a class definition to assert the code is doing what is expected.
Usually, unit tests tend to mock all the external dependencies and other
function calls that are not part of the testing code, but this is not something
entirely necessary for every case. Mocking of external dependencies should be
done sparingly for things that are unreliable (e.g. mocking a filepath, API
calls, or some system-related commands).

For instance, take the following test pseudo-code as an example of something
that needs to be mocked:

```python
import mock
import package_handler

def test_check_for_yum_updates(monkeypatch):
    packages_to_update_mock = mock.Mock(return_value=["package-1", "package-2"])
    monkeypatch.setattr(package_handler, "get_packages_to_update", value=packages_to_update_mock)

    assert package_handler.get_packages_to_update() is not None
    packages_to_update_mock.assert_called_once_with(["package-1", "package-2"])
```

And this other example, of a test that don't need any mocks for external
dependencies:

```python
import os
import file_handler

def test_archive_old_files(tmpdir):
    tmpdir = str(tmpdir)
    some_dir = os.path.join(tmpdir, "some_dir")
    some_file = os.path.join(tmpdir, "some_file.txt")
    test_data = "test data\n"

    open(some_file, "w").write(test_data)

    assert "some_file.txt" in os.listdir(tmpdir)

    file_handler.archive_old_files(tmpdir)

    old_files = os.listdir(some_dir)
    assert len(old_files) == 1
    with open(os.path.join(some_dir, old_files[0])) as old_f:
        assert old_f.read() == test_data
```

The difference between the two is that, the first one we can't rely on the
output of the `package_handler` (Because in every test run, the result may be
different depending on the system, because we are relying on an external
dependency), so we mock it to be sure we have full control over the results,
and for the second one, we know it's such a simple function that just move old
files to another directory, so it's better to provide the files and some tmp
path, still having full control of the output, no mocking necessary.

## Running the tests

The tests can be run in two different ways, in a container and locally.

Running the tests locally has the advantage of using a debugger to follow the
execution of the code.

In the other hand, running the tests in a container guarantees that you have a
isolated running test case, without interference from your machine.

### Container

To run the tests using a docker container, you can do so with the below command.

This command will run the full tests suit in both CentOS Linux 7 and 8.

```bash
# Running tests in both CentOS Linux 7 and 8
make tests
```

And, if you want to run the tests in versions individually, you can just do
this:

```bash
# Running the tests only in CentOS Linux 7
make tests7

# Running the tests only in CentOS Linux 8
make tests8
```

If you want to pass extra arguments for the pytest execution inside the container
you can do so by just using the variable `PYTEST_ARGS` after the make command you
are trying to use, like this:

```bash
# Run only the test_something test case
make tests7 PYTEST_ARGS="-k test_something"

# Print pytest version
make tests7 PYTEST_ARGS="--version"
```

The same is true when you're trying to execute the tests both with `make tests7` and
`make tests8`, the `PYTEST_ARGS` will be passed down to both of them

```bash
# Print pytest version in both containers
make tests PYTEST_ARGS="--version"
```

### Locally

To run the tests locally, you can use an alteady made `make` command we have
defined in our `Makefile`, which is:

```bash
# Make command to run the tests with pytest
make tests-locally
```

Running the tests locally also allow you to execute other commands from pytest,
such as:

```bash
# Run pytest and gather code coverage
pytest --cov

# Run a specific test (or group of tests based on name)
pytest -k test_my_thing
```

## Checking for test coverage

After running the tests, you can check for the coverage in a nicer HTML
visualization instead of the terminal output.

For this, run those command in your terminal:

```bash
# Run pytest and gather code coverage
pytest --cov

# Transform the coverage into HTML
coverage html

# Open it with your browser (Can be any browser, firefox is just an example)
firefox htmlcov/index.html
```

Refer to the documentation of
[coverage.py](https://coverage.readthedocs.io/en/6.2/) if you want to know more
about it.
