#!/bin/bash

# Note: The <RHEL6_repo_URL> and <RHEL7_repo_URL> are to be changed before executing this script.
# The system tests require the access to RHEL repositories through yum repo "baseurl" (HTTP/FTP).
# RHEL repositories are not publicly available. You can download the RHEL ISOs from
# https://access.redhat.com/downloads/, mount them and then serve them through your local FTP or web server.

# Start all defined system testing VMs
branch_name=master

if [[ -n "${1}" ]]; then
  branch_name=${1}
fi

run_vagrant() {
  pushd $1 > /dev/null
  vagrant --convert2rhel-branch=${branch_name} --copr-baseurl=$2 --rhel-repo=$3 up
  if [ $? -ne 0 ]; then
      ret_code=$?
  fi
  vagrant destroy -f
  popd
}

ret_code=0
pushd "${BASH_SOURCE%/*}" || exit
# There's no public copr with EPEL5 chroot
#run_vagrant "system_tests/vmdefs/centos5/" \
#            "<convert2rhel repo with RHEL5-compatible builds>" \
#            "<RHEL5_repo_URL>"
run_vagrant "system_tests/vmdefs/centos6/" \
            "https://download.copr.fedorainfracloud.org/results/@oamg/convert2rhel/epel-6-x86_64/" \
            "<RHEL6_repo_URL>"
run_vagrant "system_tests/vmdefs/centos7/" \
            "https://download.copr.fedorainfracloud.org/results/@oamg/convert2rhel/epel-7-x86_64/" \
            "<RHEL7_repo_URL>"
popd > /dev/null

exit $ret_code
