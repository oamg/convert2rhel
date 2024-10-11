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
	rpm7 \
	rpm8 \
	rpm9 \

# Project constants
IMAGE_REPOSITORY ?= ghcr.io
IMAGE_ORG ?= oamg
IMAGE_PREFIX ?= convert2rhel
PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv3
PRE_COMMIT ?= pre-commit
SHOW_CAPTURE ?= no
PYTEST_ARGS ?= -n auto --override-ini=addopts= -p no:cacheprovider
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
.fetch-image%:
	@echo "Pulling $(IMAGE)-centos:$*"
	@$(PODMAN) pull $(IMAGE)-centos:$*

.build-image-message:
	@echo "Building images"
.build-image%:
	@$(PODMAN) build -f Containerfiles/centos$*.Containerfile -t $(IMAGE)-centos:$* .
	@$(PODMAN) tag $(IMAGE)-centos:$* $(IMAGE_REPOSITORY)/$(IMAGE_ORG)/$(IMAGE_PREFIX)-centos:$*
	touch $@

# These files need to be made writable for pytest to run
WRITABLE_FILES=. .coverage coverage.xml
CONTAINER_TEST_FUNC=echo $(CONTAINER_TEST_WARNING) ; $(PODMAN) run -v $(shell pwd):/data:z --name convert2rhel-centos$(1) -u root:root $(CONTAINER_RM) $(IMAGE)-centos:$(1) /bin/sh -c 'touch $(WRITABLE_FILES) ; chown app:app $(WRITABLE_FILES) ; su app -c "pytest $(2) $(PYTEST_ARGS)"' ; CONTAINER_RETURN=$${?} ; $(CONTAINER_CLEANUP) ; exit $${CONTAINER_RETURN}

tests: tests7 tests8 tests9

tests7: image7
	@echo 'CentOS Linux 7 tests'
	@$(call CONTAINER_TEST_FUNC,7,--show-capture=$(SHOW_CAPTURE))

tests8: image8
	@echo 'CentOS Linux 8 tests'
	@$(call CONTAINER_TEST_FUNC,8,--show-capture=$(SHOW_CAPTURE))

tests9: image9
	@echo 'CentOS Stream 9 tests'
	@$(call CONTAINER_TEST_FUNC,9,--show-capture=$(SHOW_CAPTURE))

.srpm-clean:
	rm -frv .srpms/*el*

.srpm-clean%:
	rm -frv .srpms/*el$**

.rpm-clean:
	rm -frv .rpms/*el*

.rpm-clean%:
	rm -frv .rpms/*el$**

.rpm%:
	$(PODMAN) run -v $(shell pwd):/data:z,rw --name convert2rhel-centos$* -u root:root $(CONTAINER_RM) $(IMAGE)-centos:$* scripts/build_locally.sh

rpms: images .rpm-clean .srpm-clean .rpm7 .rpm8 .rpm9
rpm7: image7 .rpm-clean7 .srpm-clean7 .rpm7
rpm8: image8 .rpm-clean8 .srpm-clean8 .rpm8
rpm9: image9 .rpm-clean9 .srpm-clean9 .rpm9

copr-build: rpms
	mkdir -p .srpms
	rm -frv .srpms/*
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos9rpmbuild):/data/.srpms .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos8rpmbuild):/data/.srpms .
	$(PODMAN) cp $$($(PODMAN) create $(IMAGE_ORG)/$(IMAGE_PREFIX)-centos7rpmbuild):/data/.srpms .
	copr-cli --config .copr.conf build --nowait @oamg/convert2rhel .srpms/*
