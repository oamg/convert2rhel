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
	rpms \

# Project constants
IMAGE ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv3
PRE_COMMIT ?= pre-commit
SHOW_CAPTURE ?= no
PYTEST_ARGS ?=

# Let the user specify DOCKER at the CLI, otherwise try to autodetect a working podman or docker
ifndef DOCKER
  DOCKER := $(shell podman run alpine echo podman 2> /dev/null)
  ifndef DOCKER
    DOCKER := $(shell docker run alpine echo docker 2> /dev/null)
    ifndef DOCKER
      DUMMY := $(warning Many of the make targets require a working podman or docker.  Please install one of those and check that `podman run alpine echo hello` or `docker run alpine echo hello` work)
    endif
  endif
endif


all: clean images tests

install: .install .images .env .pre-commit

.install:
	virtualenv --system-site-packages --python $(PYTHON) $(VENV); \
	. $(VENV)/bin/activate; \
	$(PIP) install --upgrade -r ./requirements/local.centos8.requirements.txt; \
	touch $@

.pre-commit:
	$(PRE_COMMIT) install --install-hooks
	touch $@

.env:
	cp .env.example .env

tests-locally: install
	. $(VENV)/bin/activate; pytest $(PYTEST_ARGS)

lint-locally: install
	. $(VENV)/bin/activate; ./scripts/run_lint.sh

clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +

images: .images

.images:
	@$(DOCKER) build -f Dockerfiles/centos7.Dockerfile -t $(IMAGE)/centos7 .
	@$(DOCKER) build -f Dockerfiles/centos8.Dockerfile -t $(IMAGE)/centos8 .
	@$(DOCKER) build -f Dockerfiles/rpmbuild.centos8.Dockerfile -t $(IMAGE)/centos8rpmbuild .
	@$(DOCKER) build -f Dockerfiles/rpmbuild.centos7.Dockerfile -t $(IMAGE)/centos7rpmbuild .
	touch $@

lint: images
	@$(DOCKER) run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh"

lint-errors: images
	@$(DOCKER) run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh --errors-only"

tests: tests7 tests8

tests7: images
	@echo 'CentOS Linux 7 tests'
	@$(DOCKER) run --rm --user=$(id -ur):$(id -gr) -v $(shell pwd):/data:Z $(IMAGE)/centos7 pytest --show-capture=$(SHOW_CAPTURE) $(PYTEST_ARGS)

tests8: images
	@echo 'CentOS Linux 8 tests'
	@$(DOCKER) run --rm --user=$(id -ur):$(id -gr) -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest --show-capture=$(SHOW_CAPTURE) $(PYTEST_ARGS)

rpms: images
	mkdir -p .rpms
	rm -frv .rpms/*
	$(DOCKER) build -f Dockerfiles/rpmbuild.centos8.Dockerfile -t $(IMAGE)/centos8rpmbuild .
	$(DOCKER) build -f Dockerfiles/rpmbuild.centos7.Dockerfile -t $(IMAGE)/centos7rpmbuild .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE)/centos8rpmbuild):/data/.rpms .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE)/centos7rpmbuild):/data/.rpms .
	$(DOCKER) rm $$($(DOCKER) ps -aq) -f

copr-build: rpms
	mkdir -p .srpms
	rm -frv .srpms/*
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE)/centos8rpmbuild):/data/.srpms .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE)/centos7rpmbuild):/data/.srpms .
	$(DOCKER) rm $$($(DOCKER) ps -aq) -f
	copr-cli --config .copr.conf build --nowait @oamg/convert2rhel .srpms/*

update-vms:
	virsh start c2r_centos8_template
	virsh start c2r_centos7_template
	virsh start c2r_oracle8_template
	virsh start c2r_oracle7_template
	sleep 10
	ansible-playbook -v -c community.libvirt.libvirt_qemu -i c2r_centos8_template,c2r_centos7_template,c2r_oracle8_template,c2r_oracle7_template tests/ansible_collections/update_templates.yml
	virsh shutdown c2r_centos8_template
	virsh shutdown c2r_centos7_template
	virsh shutdown c2r_oracle8_template
	virsh shutdown c2r_oracle7_template
