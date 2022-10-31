.PHONY: \
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
IMAGE_REPOSITORY ?= ghcr.io
IMAGE_ORG ?= oamg
IMAGE_PREFIX ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv3
PRE_COMMIT ?= pre-commit
SHOW_CAPTURE ?= no
PYTEST_ARGS ?=
BUILD_IMAGES ?= 1

ifdef KEEP_TEST_CONTAINER
  DOCKER_RM_CONTAINER =
else
  DOCKER_RM_CONTAINER = --rm
endif

# Let the user specify DOCKER at the CLI, otherwise try to autodetect a working podman or docker
ifndef DOCKER
  DOCKER := $(shell podman run --rm alpine echo podman 2> /dev/null)
  ifndef DOCKER
    DOCKER := $(shell docker run --rm alpine echo docker 2> /dev/null)
    ifndef DOCKER
      DUMMY := $(warning Many of the make targets require a working podman or docker.  Please install one of those and check that `podman run alpine echo hello` or `docker run alpine echo hello` work)
    endif
  endif
endif

ifdef DOCKER
  ifeq ($(DOCKER), podman)
    DOCKER_TEST_WARNING := "*** convert2rhel directory will be read-only while tests are executing ***"
    DOCKER_CLEANUP := podman unshare chown -R 0:0 $(shell pwd)
  else
    # Docker
    DOCKER_TEST_WARNING := -n
    DOCKER_CLEANUP := echo -n
  endif
else
  # No docker found
  DOCKER_TEST_WARNING ?= -n
  DOCKER_CLEANUP ?= echo -n
endif

all: clean images tests

install: .install .build-images .pre-commit

.install:
	virtualenv --system-site-packages --python $(PYTHON) $(VENV); \
	. $(VENV)/bin/activate; \
	$(PIP) install --upgrade -r ./requirements/centos8.requirements.txt; \
	touch $@

.pre-commit:
	$(PRE_COMMIT) install --install-hooks
	touch $@

tests-locally: install
	. $(VENV)/bin/activate; pytest $(PYTEST_ARGS)

lint-locally: install
	. $(VENV)/bin/activate; ./scripts/run_lint.sh

clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/ .build-images
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +

ifeq ($(BUILD_IMAGES), 1)
images: .build-images
IMAGE=$(IMAGE_ORG)/$(IMAGE_PREFIX)
else
images: .fetch-images
IMAGE=$(IMAGE_REPOSITORY)/$(IMAGE_ORG)/$(IMAGE_PREFIX)
endif

.fetch-images:
	@echo "Fetching images from github."
	@echo
	@echo "If this fails, on authentication,"
	@echo "either build the images locally using 'make BUILD_IMAGES=1 $$make_target'"
	@echo "or login first with '$(DOCKER) login ghcr.io -u $$github_username'"
	@echo "https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry"
	@echo
	@echo "Pulling $(IMAGE)-centos6"
	@$(DOCKER) pull $(IMAGE)-centos6
	@echo "Pulling $(IMAGE)-centos7"
	@$(DOCKER) pull $(IMAGE)-centos7
	@echo "Pulling $(IMAGE)-centos8"
	@$(DOCKER) pull $(IMAGE)-centos8
.build-images:
	@echo "Building images"
	@$(DOCKER) build -f Dockerfiles/centos6.Dockerfile -t $(IMAGE)-centos6 .
	@$(DOCKER) build -f Dockerfiles/centos7.Dockerfile -t $(IMAGE)-centos7 .
	@$(DOCKER) build -f Dockerfiles/centos8.Dockerfile -t $(IMAGE)-centos8 .
	touch $@

lint: images
	@$(DOCKER) run $(DOCKER_RM_CONTAINER) -v $(shell pwd):/data:Z $(IMAGE)-centos8 bash -c "scripts/run_lint.sh"

lint-errors: images
	@$(DOCKER) run $(DOCKER_RM_CONTAINER) -v $(shell pwd):/data:Z $(IMAGE)-centos8 bash -c "scripts/run_lint.sh --errors-only"

tests: tests6 tests7 tests8

# These files need to be made writable for pytest to run
WRITABLE_FILES=. .coverage coverage.xml
DOCKER_TEST_FUNC=echo $(DOCKER_TEST_WARNING) ; $(DOCKER) run -v $(shell pwd):/data:Z --name pytest-container -u root:root $(DOCKER_RM_CONTAINER) $(IMAGE)-$(1) /bin/sh -c 'touch $(WRITABLE_FILES) ; chown app:app $(WRITABLE_FILES) ; su app -c "pytest $(2) $(PYTEST_ARGS)"' ; DOCKER_RETURN=$${?} ; $(DOCKER_CLEANUP) ; exit $${DOCKER_RETURN}

tests6: images
	@echo 'CentOS Linux 6 tests'
ifneq ("$(SHOW_CAPTURE)", "no")
		@$(call DOCKER_TEST_FUNC,centos6,--show-capture=$(SHOW_CAPTURE))
else
		@$(call DOCKER_TEST_FUNC,centos6,)
endif

tests7: images
	@echo 'CentOS Linux 7 tests'
	@$(call DOCKER_TEST_FUNC,centos7,--show-capture=$(SHOW_CAPTURE))

tests8: images
	@echo 'CentOS Linux 8 tests'
	@$(call DOCKER_TEST_FUNC,centos8,--show-capture=$(SHOW_CAPTURE))

rpms:
	mkdir -p .rpms
	rm -frv .rpms/*
	$(DOCKER) build -f Dockerfiles/rpmbuild.centos8.Dockerfile -t $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild .
	$(DOCKER) build -f Dockerfiles/rpmbuild.centos7.Dockerfile -t $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild):/data/.rpms .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild):/data/.rpms .
	$(DOCKER) rm $$($(DOCKER) ps -aq) -f

copr-build: rpms
	mkdir -p .srpms
	rm -frv .srpms/*
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild):/data/.srpms .
	$(DOCKER) cp $$($(DOCKER) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild):/data/.srpms .
	$(DOCKER) rm $$($(DOCKER) ps -aq) -f
	copr-cli --config .copr.conf build --nowait @oamg/convert2rhel .srpms/*
