# Contributing to Convert2RHEL

The following is a set of guidelines for contributing to Convert2RHEL codebase,
which are hosted in the [OAMG Organization](https://github.com/oamg) on GitHub.
These are mostly guidelines, not rules.

## What should I know before I get started?

Below are a list of things to keep in mind when developing and submitting
contributions to this repository.

1. All python code must be compatible with versions 2.7/3.6.
2. The code should follow linting from pylint.
3. All commits should have passed the pre-commit checks.
4. Don't change code that is not related to your issue/ticket, open a new
   issue/ticket if that's the case.

### Working with GitHub

If you are not sure on how GitHub works, you can read the quickstart guide from
GitHub to introduce you on how to get started at the platform. [GitHub
Quickstart - Hello
World](https://docs.github.com/en/get-started/quickstart/hello-world).

### Setting up Git

If you never used `git` before, GitHub has a nice quickstart on how to set it
up and get things ready. [GitHub Quickstart - Set up
Git](https://docs.github.com/en/get-started/quickstart/set-up-git)

### Forking a repository

Forking is necessary if you want to contribute with Convert2RHEL, but if you
are unsure on how this work (Or what a fork is), head out to this quickstart
guide from GitHub. [GitHub Quickstart - Fork a
repo](https://docs.github.com/en/get-started/quickstart/fork-a-repo)

As an additional material, check out this Red Hat blog post about [What is an
open source
upstream?](https://www.redhat.com/en/blog/what-open-source-upstream)

### Collaborating with Pull Requests

Check out this guide from GitHub on how to collaborate with pull requests. This
is an in-depth guide on everything you need to know about PRs, forks,
contributions and much more. [GitHub - Collaborating with pull
requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests)

## Getting started with development

### Develop in a container through VS Code

> **Note**
>
> This has only been tested with Podman

For an easy setup where you can get up and running within a minute, we have a dedicated development container setup with
VS Code. This creates a container with extensions and allows you to run convert2rhel and tests without drawbacks.

This does not work with VSCodium as Dev Container is deliberately limited to only work with Microsoft VS Code binaries.

Note: we need to run tests in a container as convert2rhel is volatile, a small mistake in tests can make modifications
on your system.

To get started with a Dev Container, you need to install the [Dev Container extensions in VS Code](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers). You can follow the link or install this ID
```
ms-vscode-remote.remote-containers
```

Once the extension is installed, all you need to do is open up the repository inside a container, pressing `F1` or
`Ctrl-Shift-P` and starting the following will open up the container for you
```
Dev Containers: Open Folder in Container
```

You are now inside a container as indicated by the bottom left box. There is an extension for tests in the left
navigation that auto-discovers tests that you can run. This will be much faster than developing using `make tests`

### Dependencies for local development

We have some required dependencies you should have installed on your system
(either your local computer or a container) to get ready to write some
code:

Required dependencies:

- virtualenv
- python
- pre-commit
- git
- podman

Optional dependencies:

- [make](https://www.gnu.org/software/make/#download)

### Setting up the environment

The commands below will create a python3 virtual environment with all the
necessary dependencies installed, images built, and setup `pre-commit` hooks.

Beware this command can take a while to finish, depending on your internet
connection.

```bash
make install
```

#### Running the linters/pre-commit

You can run the linters against the codebase to get a complete summary of what
is not standardized in the current codebase (as a whole)

```bash
make lint # Runs inside a centos8 container
```

or locally, with:

```bash
make lint-locally
```

#### Pre-commit

Pre-commit is an important tool for our development workflow, with this tool we
can run a series of pre-defined hooks against our codebase to keep it clean and
maintainable. Here is an example of output from `pre-commit` being run:

```
(.venv3) [r0x0d@fedora convert2rhel]$ pre-commit run --all-files
Format code (black)......................................................Passed
isort....................................................................Passed
Fix End of Files.........................................................Passed
Trim Trailing Whitespace.................................................Passed
Check JSON...........................................(no files to check)Skipped
Check Toml...............................................................Passed
Check Yaml...............................................................Passed
Check for merge conflicts................................................Passed
```

We automatically run `pre-commit` as part of our CI infrastructure as well. If you have a PR it will run and see if everything passes. Sometimes there may be an outage or unexpected result from `pre-commit`, if that happens you can create a new comment on the PR saying:

> pre-commit.ci run

Install `pre-commit` hooks to automatically run when doing `git commit`.

```bash
# installs pre-commit hooks into the repo (included into make install)
pre-commit install --install-hooks
```

Running `pre-commit` against our files

```bash
# run pre-commit hooks for staged files
pre-commit run

# run pre-commit hooks for all files in repo
pre-commit run --all-files

# bypass pre-commit hooks
git commit --no-verify
```

And lastly but not least, if you wish to update our hooks, we can do so by
running the command:

```bash
# bump versions of the pre-commit hooks automatically to the latest available
pre-commit autoupdate
```

If you wish to learn more about all the things that `pre-commit` can do, refer
to their documentation on [how to use
pre-commit](https://pre-commit.com/#usage).

### Writing tests

Tests are an important part of the development process, they guarantee to us
that our code is working in the correct way as expected, and for Convert2RHEL,
we separate these tests in two categories.

- Unit testing
- Integration testing

If you're in doubt on how to make a test, you can read this great article from
[Real Python - Getting Started With Testing in
Python](https://realpython.com/python-testing/) to get a better idea between
the differences between these tests and how they are usually made.

Also, you can check out our
[unit_tests/README.md](https://github.com/oamg/convert2rhel/blob/main/convert2rhel/unit_tests/README.md#unit-testing-in-convert2rhel)
file to get a better understanding on how to write, run and see the coverage of
the unit tests.

To learm more about our integration tests, see
[tests/integration/README.md](https://github.com/oamg/convert2rhel/blob/main/tests/integration/README.md).

## Styleguide

### Git commit message

* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or fewer
* If you are fixing a GitHub issue, include something like "Closes #xyz"

To know more about best practices for commit messages, go ahead and read [How
to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/).

### Python code styleguide

For Convert2RHEL we use the [PEP 8 -- Style Guide for Python
Code](https://www.python.org/dev/peps/pep-0008/) as well some
linters/formatters that are run directly from
[pre-commit](https://pre-commit.com).

Don't worry, most of the code formatting and styleguide is handled by
[black](https://github.com/psf/black), an awesome formatter for python code.

### Python documentation styleguide

The documentation for our python code should follow the [PEP 8 -- Documentation
Strings](https://www.python.org/dev/peps/pep-0008/#toc-entry-20) or more
precisely the [PEP 257 -- Docstring
Conventions](https://www.python.org/dev/peps/pep-0257/) and preferably all
functions should contain at least a minimum docstring to identify what that
function is used for.

## Additional information

Additional technical information is located [on the
wiki](https://github.com/oamg/convert2rhel/wiki).  When you add a new feature that others might need
to plug into or affects how their code should be written in the future, please add a new page there
and link it to the toplevel [Topics section](https://github.com/oamg/convert2rhel/wiki#topics).


### Building rpms locally

For building the rpms locally, you will need:

- podman

```bash
make rpms
```

### Building copr builds locally

For building the copr locally, you will need:

- podman installed
- have an account at https://copr.fedorainfracloud.org/api/, copy copr config
  and paste it to the repo root as .copr.conf
- request build permissions at
  https://copr.fedorainfracloud.org/coprs/g/oamg/convert2rhel/permissions/

> WARNING: Do not bump the Release in packaging/convert2rhel.spec. Otherwise,
> this version will be automatically installed during yum install

```bash
make copr-build
```

### Avoiding calling yum API in some specific cases

We found a bug that happened during the handling of a SIGINT
signal (or pressing CTRL + C). The bug occurred when a user pressed that
combination of keys during any step of the conversion before the point of no
return. The Ctrl-C started the rollback process and failed in the first
`yum` API call to check whether or not some packages were installed on the system.

The problem is that when we enter rollback after a SIGINT, `librpm` handles the
signal in its code (without any possibility to change this). The `librpm` handler
detects that a SIGINT was raised, decides that the execution of the process
should stop, and sends 1 as the program's exit code. One way to bypass this
problem is not to call `yum` methods that actually trigger `librpm` in the
process, instead, calling the `yum` binary or any other binary that achieves
the same goal. By calling `yum` via `call_yum_cmd()` or `run_subprocess()`,
a separate process is started and the SIGINT is handled by that separate
process rather than the main convert2rhel process.

For example, checkout
[PR#411](https://github.com/oamg/convert2rhel/pull/411/files#diff-51e9ff11d39778d3b26778b293fc350430a82e2feed0dab2938da7c0069ffdc6R84)
which introduced the fix for this bug, as well, some explanation on why the code was
changed from calling the yum API to calling the `rpm` command.

Here's the ticket that originated this issue:
[OAMG-5756](https://issues.redhat.com/browse/OAMG-5756).

Lastly, a minimal reproducer from
[@abadger](https://github.com/abadger) where you can see the issue.

```python
#!/usr/bin/python2 -tt
import time
from yum import YumBase
from rpmUtils.miscutils import checkSignals

yb = YumBase()
try:
    #yb.doConfigSetup(init_plugins=False)
    yb.runTransaction(False)
except (BaseException, SystemExit, Exception) as e:
    print('We were able to catch an exception from runTransaction!')
    print(type(e))
    print(e)
print('Sleeping')
time.sleep(3)
# Hit Ctrl-C
# If KeyboardInterrupt is raised, chances are that this did not cause the
# problem
try:
    checkSignals()
except (BaseException, SystemExit, Exception) as e:
    print('We were able to catch an exception from checkSignals!')
    print(type(e))
    print(e)
finally:
    print('In the finally block')
# If the previous try: except  exits immediately without message, then the
# issue occurred.
# If it raises a KeyboardInterrupt traceback then we're okay.
# If it prints out anything then we're either okay or encountering a different
# behaviour.
```
