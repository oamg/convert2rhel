mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
mkfile_dir := $(dir $(mkfile_path))
repo_root := $(mkfile_dir)/../

srpm:
	@echo --- Building SRPM ---
	$(repo_root)/packaging/epel/create_epel_srpm.sh
	@mv $(repo_root)/SRPMS/*.rpm $(outdir)
	@rm -rf $(repo_root)/SRPMS/
	@echo --- Done ---
