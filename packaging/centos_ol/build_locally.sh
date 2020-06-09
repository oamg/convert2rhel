#!/bin/bash
# Run this script on CentOS/OL/RHEL 6 or 7 in the root of the cloned convert2rhel repo
pushd ../../
python setup.py sdist
cp dist/* ~/rpmbuild/SOURCES
rpmlint packaging/centos_ol/convert2rhel.spec
rpmbuild -ba packaging/centos_ol/convert2rhel.spec --define "debug_package %{nil}"
rpmlint ~/rpmbuild/RPMS/noarch/convert2rhel*.rpm
popd
