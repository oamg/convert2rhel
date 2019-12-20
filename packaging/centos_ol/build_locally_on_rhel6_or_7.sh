#!/bin/bash
# Run this script on CentOS/OL/RHEL 6 or 7 in the root of the cloned convert2rhel repo
python setup.py sdist
cp dist/* ~/rpmbuild/SOURCES
rpmlint convert2rhel.spec
rpmbuild -ba convert2rhel.spec --define "debug_package %{nil}"
rpmlint ~/rpmbuild/RPMS/x86_64/convert2rhel*.rpm
