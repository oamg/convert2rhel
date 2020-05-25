# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7 compatible
1. Code should follow linting from pylint

## Unit tests
Our unit tests are run within containers. To first create the container images run

```bash
$ make images
```

Once images have been setup you can now run unit tests within the containers using

```bash
$ make tests
```

## Linting
Linting can be done locally using `virtualenv`.

```bash
# Setup a virtual environment
$ pip install virtualenv
$ virtualenv .venv --python=python2
$ source .venv/bin/activate
$ pip install -r requirements.txt

# Run pylint
$ pylint convert2rhel/
```