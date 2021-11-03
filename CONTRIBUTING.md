# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7/3.6 compatible
1. The code should follow linting from pylint

## Developing locally

Required dependencies:
- virtualenv
- pre-commit
- podman (or a working docker)

The commands below create a python3 virtual environment with all the necessary dependencies installed,
build needed images,
create .env file, and
setup pre-commit hooks
```bash
make install
```

and you're ready to run tests inside the containers with:
```bash
make tests
```

## Linting

```bash
make lint   # runs inside a centos8 container
```
Or locally
```bash
make lint-locally
```

## Work with pre-commit hooks

```bash
# installs pre-commit hooks into the repo (included into make install)
pre-commit install --install-hooks

# run pre-commit hooks for staged files
pre-commit run

# run pre-commit hooks for all files in repo
pre-commit run --all-files

# bump versions of the pre-commit hooks automatically
pre-commit autoupdate

# bypass pre-commit check
git commit --no-verify
```

# Building rpms locally

You need podman or a working docker installed

```bash
make rpms
```

# Building copr builds locally

You need:
- podman or a working docker installed
- have an account at https://copr.fedorainfracloud.org/api/, copy copr config
  and paste it to the repo root as .copr.conf
- request build permissions at https://copr.fedorainfracloud.org/coprs/g/oamg/convert2rhel/permissions/

```bash
make copr-build
```

Warning: Do not bump the Release in packaging/convert2rhel.spec.
Otherwise, this version will be automatically installed during yum install
