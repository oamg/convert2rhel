# Project constants
IMAGE ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv3

.PHONY: all
all: clean images tests

.PHONY: install
install:
	virtualenv --system-site-packages --python $(PYTHON) $(VENV); \
	. $(VENV)/bin/activate; \
	$(PIP) install --upgrade -r ./requirements/local.centos8.requirements.txt; \
	$(PIP) install -e .

.PHONY: tests-locally
tests-locally:
	. $(VENV)/bin/activate; pytest


.PHONY: clean
clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +

.PHONY: images
images:
	@docker build -f Dockerfiles/centos6.Dockerfile -t $(IMAGE)/centos6 .
	@docker build -f Dockerfiles/centos7.Dockerfile -t $(IMAGE)/centos7 .
	@docker build -f Dockerfiles/centos8.Dockerfile -t $(IMAGE)/centos8 .

.PHONY: tests
tests:
	@echo 'CentOS 6 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos6 pytest
	@echo 'CentOS 7 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos7 pytest
	@echo 'CentOS 8 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest

.PHONY: lint
lint:
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh"

.PHONY: lint-errors
lint-errors:
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh --errors-only"

.PHONY: tests8
tests8:
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest
