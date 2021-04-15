# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7/3.6 compatible
1. The code should follow linting from pylint

## Developing locally

The commands below installs a python3 virtual environment
with all the necessary dependencies installed:
```bash
make install
```

and you're ready to run tests with:
```bash
make tests-locally
```

## Unit tests (inside the container)
You can run unit tests also within containers. To first create the container 
images, run:

```bash
$ make images
```

Once images have been setup, you can now run unit tests within the containers using:

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
