mkfile_dir := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
repo_root := $(mkfile_dir)/../
yum_or_dnf := $(shell command -v dnf || command -v yum)

install_build_deps:
	@echo --- Installing SRPM build requirements ---
	@$(yum_or_dnf) install -y git python2 python2-setuptools rpmlint rpm-build

srpm: install_build_deps
	@echo --- Building SRPM ---
	$(repo_root)/packaging/create_epel_srpm.sh
	@mv $(repo_root)/SRPMS/*.rpm $(outdir)
	@rm -rf $(repo_root)/SRPMS/
	@echo --- Done ---
