# Contributing to Convert2RHEL

The following is a set of guidelines for contributing to Convert2RHEL codebase,
which are hosted in the [OAMG Organization](https://github.com/oamg) on GitHub.
These are mostly guidelines, not rules.

## What should I know before I get started?

Below are a list of things to keep in mind when developing and submitting
contributions to this repository.

1. All python code must be compatible with versions 2.6/2.7/3.6.
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

### Dependencies for local development

We have some required dependencies you should have installed on your system
(either your local computer or a docker container) to get ready to write some
code:

Required dependencies:

- virtualenv
- python
- pre-commit
- git
- podman or docker

Optional dependencies:

- [make](https://www.gnu.org/software/make/#download)

### Setting up the environment

The commands below will create a python3 virtual environment with all the
necessary dependencies installed, images built, `.env` file created, and setup
`pre-commit` hooks.

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

### Building rpms locally

For building the rpms locally, you will need:

- podman or a docker

```bash
make rpms
```

### Building copr builds locally

For building the copr locally, you will need:

- podman or a docker installed
- have an account at https://copr.fedorainfracloud.org/api/, copy copr config
  and paste it to the repo root as .copr.conf
- request build permissions at
  https://copr.fedorainfracloud.org/coprs/g/oamg/convert2rhel/permissions/

> WARNING: Do not bump the Release in packaging/convert2rhel.spec. Otherwise,
> this version will be automatically installed during yum install

```bash
make copr-build
```
