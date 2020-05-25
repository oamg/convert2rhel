# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7 compatible
1. Code should follow linting from pylint

## Unit tests
Our unit tests are run within containers. To first create the container images run

    $ make images

Once images have been setup you can now run unit tests within the containers using

    $ make tests

## Linting
Linting can be done using 

    $ make lint

Or by installing locally using `pipenv`

    $ pipenv install
    $ pipenv run pylint convert2rhel/