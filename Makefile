.PHONY: \
	install \
	tests-locally \
	lint-locally \
	clean \
	images \
	image7 \
	image8 \
	image9 \
	tests \
	tests7 \
	tests8 \
	tests9 \
	lint \
	lint-errors \
	rpms \

# Project constants
IMAGE_REPOSITORY ?= ghcr.io
IMAGE_ORG ?= oamg
IMAGE_PREFIX ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
PYLINT ?= pylint
PYLINT_ARGS ?=
VENV ?= .venv3
PRE_COMMIT ?= pre-commit
SHOW_CAPTURE ?= no
PYTEST_ARGS ?= -p no:cacheprovider
BUILD_IMAGES ?= 1

ifdef KEEP_TEST_CONTAINER
	CONTAINER_RM =
else
	CONTAINER_RM = --rm
endif

# Let the user specify PODMAN at the CLI, otherwise try to autodetect a working podman
ifndef PODMAN
	PODMAN := $(shell podman run --rm alpine echo podman 2> /dev/null)
	ifndef PODMAN
		DUMMY := $(warning podman is not detected. Majority of commands will not work. Please install and verify that podman --version works.)
	endif
endif

ifdef PODMAN
	CONTAINER_TEST_WARNING := "*** convert2rhel directory will be read-only while tests are executing ***"
	CONTAINER_CLEANUP := podman unshare chown -R 0:0 $(shell pwd)
endif

all: clean images tests

install: .install .pre-commit

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
	. $(VENV)/bin/activate; $(PYLINT) --rcfile=.pylintrc $(PYLINT_ARGS) convert2rhel/

clean:
	@rm -rf build/ dist/ *.egg-info .pytest_cache/
	@find . -name '__pycache__' -exec rm -fr {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '.build-image*' -exec rm -f {} +

ifeq ($(BUILD_IMAGES), 1)
images: .build-image-message .build-image7 .build-image8 .build-image9
image7: .build-image-message .build-image7
image8: .build-image-message .build-image8
image9: .build-image-message .build-image9
IMAGE=$(IMAGE_ORG)/$(IMAGE_PREFIX)
else
images: .fetch-image-message .fetch-image7 .fetch-image8 .fetch-image9
image7: .fetch-image-message .fetch-image7
image8: .fetch-image-message .fetch-image8
image9: .fetch-image-message .fetch-image9
IMAGE=$(IMAGE_REPOSITORY)/$(IMAGE_ORG)/$(IMAGE_PREFIX)
endif

.fetch-image-message:
	@echo "Fetching image(s) from github."
	@echo
	@echo "If this fails, on authentication,"
	@echo "either build the images locally using 'make BUILD_IMAGES=1 $$make_target'"
	@echo "or login first with '$(PODMAN) login ghcr.io -u $$github_username'"
	@echo "https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry"
	@echo
.fetch-image7:
	@echo "Pulling $(IMAGE)-centos7"
	@$(PODMAN) pull $(IMAGE)-centos7
.fetch-image8:
	@echo "Pulling $(IMAGE)-centos8"
	@$(PODMAN) pull $(IMAGE)-centos8
.fetch-image9:
	@echo "Pulling $(IMAGE)-centos9"
	@$(PODMAN) pull $(IMAGE)-centos9

.build-image-message:
	@echo "Building images"
.build-image7:
	@$(PODMAN) build -f Containerfiles/centos7.Containerfile -t $(IMAGE)-centos7 .
	touch $@
.build-image8:
	@$(PODMAN) build -f Containerfiles/centos8.Containerfile -t $(IMAGE)-centos8 .
	touch $@
.build-image9:
	@$(PODMAN) build -f Containerfiles/centos9.Containerfile -t $(IMAGE)-centos9 .
	touch $@

lint: images
	@$(PODMAN) run $(CONTAINER_RM) -v $(shell pwd):/data:Z $(IMAGE)-centos8 bash -c "$(PYLINT) --rcfile=.pylintrc $(PYLINT_ARGS) convert2rhel/"

tests: tests7 tests8 tests9

# These files need to be made writable for pytest to run
WRITABLE_FILES=. .coverage coverage.xml
CONTAINER_TEST_FUNC=echo $(CONTAINER_TEST_WARNING) ; $(PODMAN) run -v $(shell pwd):/data:Z --name pytest-container -u root:root $(CONTAINER_RM) $(IMAGE)-$(1) /bin/sh -c 'touch $(WRITABLE_FILES) ; chown app:app $(WRITABLE_FILES) ; su app -c "pytest $(2) $(PYTEST_ARGS)"' ; CONTAINER_RETURN=$${?} ; $(CONTAINER_CLEANUP) ; exit $${CONTAINER_RETURN}

tests7: image7
	@echo 'CentOS Linux 7 tests'
	@$(call CONTAINER_TEST_FUNC,centos7,--show-capture=$(SHOW_CAPTURE))

tests8: image8
	@echo 'CentOS Linux 8 tests'
	@$(call CONTAINER_TEST_FUNC,centos8,--show-capture=$(SHOW_CAPTURE))

tests9: image9
	@echo 'CentOS 9 tests'
	@$(call CONTAINER_TEST_FUNC,centos9,--show-capture=$(SHOW_CAPTURE))

rpms:
	mkdir -p .rpms
	rm -frv .rpms/*
	$(PODMAN) build -f Containerfiles/rpmbuild.centos9.Containerfile -t $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos9rpmbuild .
	$(PODMAN) build -f Containerfiles/rpmbuild.centos8.Containerfile -t $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild .
	$(PODMAN) build -f Containerfiles/rpmbuild.centos7.Containerfile -t $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild):/data/.rpms .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild):/data/.rpms .
	$(PODMAN) rm $$($(PODMAN) ps -aq) -f

copr-build: rpms
	mkdir -p .srpms
	rm -frv .srpms/*
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos9rpmbuild):/data/.srpms .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild):/data/.srpms .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild):/data/.srpms .
	$(PODMAN) rm $$($(PODMAN) ps -aq) -f
	copr-cli --config .copr.conf build --nowait @oamg/convert2rhel .srpms/*
