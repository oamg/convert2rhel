#!/bin/bash

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
run_vagrant "system_tests/vmdefs/centos5/" \
            "https://<copr_hostname>/results/mbocek/convert2rhel/rhel-5-x86_64/" \
            "http://<rhel_storage_hostname>/pub/rhel/released/RHEL-5-Server/U11/x86_64/os/Server/"
run_vagrant "system_tests/vmdefs/centos6/" \
            "https://<copr_hostname>/results/mbocek/convert2rhel/rhel-6-x86_64/" \
            "http://<rhel_storage_hostname>/pub/rhel/released/RHEL-6/6.10/Server/x86_64/os/"
run_vagrant "system_tests/vmdefs/centos7/" \
            "https://<copr_hostname>/results/mbocek/convert2rhel/rhel-7-x86_64/" \
            "http://<rhel_storage_hostname>/pub/rhel/released/RHEL-7/7.6/Server/x86_64/os/"
popd > /dev/null

exit $ret_code
