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
	@docker build -f Dockerfiles/centos7.Dockerfile -t $(IMAGE)/centos7 .
	@docker build -f Dockerfiles/centos8.Dockerfile -t $(IMAGE)/centos8 .
	@docker build -f Dockerfiles/rpmbuild.centos8.Dockerfile -t $(IMAGE)/centos8rpmbuild .
	@docker build -f Dockerfiles/rpmbuild.centos7.Dockerfile -t $(IMAGE)/centos7rpmbuild .
	touch $@

tests: images
	@echo 'CentOS Linux 7 tests'
	@docker run --user=$(id -ur):$(id -gr) --rm -v $(shell pwd):/data:Z $(IMAGE)/centos7 pytest
	@echo 'CentOS Linux 8 tests'
	@docker run --user=$(id -ur):$(id -gr) --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest

lint: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh"

lint-errors: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 bash -c "scripts/run_lint.sh --errors-only"

tests8: images
	@docker run --rm -v $(shell pwd):/data:Z $(IMAGE)/centos8 pytest

rpms: images
	mkdir -p .rpms
	rm -frv .rpms/*
	docker build -f Dockerfiles/rpmbuild.centos8.Dockerfile -t $(IMAGE)/centos8rpmbuild .
	docker build -f Dockerfiles/rpmbuild.centos7.Dockerfile -t $(IMAGE)/centos7rpmbuild .
	docker cp $$(docker create $(IMAGE)/centos8rpmbuild):/data/.rpms .
	docker cp $$(docker create $(IMAGE)/centos7rpmbuild):/data/.rpms .
	docker rm $$(docker ps -aq) -f

copr-build: rpms
	mkdir -p .srpms
	rm -frv .srpms/*
	docker cp $$(docker create $(IMAGE)/centos8rpmbuild):/data/.srpms .
	docker cp $$(docker create $(IMAGE)/centos7rpmbuild):/data/.srpms .
	docker rm $$(docker ps -aq) -f
	copr-cli --config .copr.conf build --nowait zhukovgreen/convert2rhel .srpms/*

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
