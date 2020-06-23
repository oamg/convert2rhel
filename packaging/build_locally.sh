#!/bin/bash
# Run this script on CentOS/OL/RHEL 6/7/8
pushd $(dirname "$0")/../

echo "Creating a tarball for building the RPM ..."
if [ -x "$(command -v python3)" ]; then
  python3 setup.py sdist
elif [ -x "$(command -v python2)" ]; then
  python2 setup.py sdist
else
  echo "Error: Can't find python interpreter."
  exit 1
fi
mkdir -p ~/rpmbuild/SOURCES
cp dist/* ~/rpmbuild/SOURCES

echo "Linting the spec file ..."
rpmlint packaging/convert2rhel.spec

echo "Building the RPM ..."
rpmbuild -ba packaging/convert2rhel.spec --define "debug_package %{nil}"

echo "Linting the built RPM ..."
rpmlint ~/rpmbuild/RPMS/noarch/convert2rhel*.rpm

popd
