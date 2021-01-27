.PHONY: \
	force-rebuild \
	install \
	tests-locally \
	lint-locally \
	clean \
	images \
	tests \
	lint \
	lint-errors \
	tests8 \

# Project constants
IMAGE ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv3

all: clean images tests

install: .install

.install:
	virtualenv --system-site-packages --python $(PYTHON) $(VENV); \
	. $(VENV)/bin/activate; \
	$(PIP) install --upgrade -r ./requirements/local.centos8.requirements.txt; \
	$(PIP) install -e .
	touch $@

tests-locally: install
	. $(VENV)/bin/activate; pytest

lint-locally: install
	. $(VENV)/bin/activate; ./scripts/run_lint.sh

clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +

images: .images

.images:
	@docker build -f Dockerfiles/centos6.Dockerfile -t $(IMAGE)/centos6 .
	@docker build -f Dockerfiles/centos7.Dockerfile -t $(IMAGE)/centos7 .
	@docker build -f Dockerfiles/centos8.Dockerfile -t $(IMAGE)/centos8 .
	touch $@

tests: images
	@echo 'CentOS 6 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos6 pytest
	@echo 'CentOS 7 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos7 pytest
	@echo 'CentOS 8 tests'
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest

lint: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh"

lint-errors: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh --errors-only"

tests8: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest
