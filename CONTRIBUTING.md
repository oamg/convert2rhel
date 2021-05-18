# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7/3.6 compatible
1. The code should follow linting from pylint

## Developing locally

Required dependencies:
- virtualenv
- pre-commit

The commands below create a python3 virtual environment with all the necessary dependencies installed,
build needed images,
create .env file, and
setup pre-commit hooks
```bash
make install
```

and you're ready to run tests with:
```bash
make tests-locally
```

## Unit tests (inside the container)
You can run unit tests also within containers.

```bash
$ make tests
```

## Linting

```bash
make lint   # inside the centos8 container
```
Or locally
```bash
make lint-locally
```

## Work with pre-commit hooks

```bash
# installs hooks into the repo (included into make install)
pre-commit install --install-hooks

# run hooks for staged files
pre-commit run

# run hooks for all files in repo
pre-commit run --all-files

# bump versions of the ooks automatically
pre-commit autoupdate

# bypass pre-commit check
git commit --no-verify
```
