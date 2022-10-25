#!/bin/bash

set -e

# Run this script on CentOS Linux/OL/RHEL 6/7/8
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
cp -v dist/* ~/rpmbuild/SOURCES
echo "Building the RPM ..."
rpmbuild -ba packaging/convert2rhel.spec --define "debug_package %{nil}"
echo "RPM was built successfully"
echo "Cleaning up the target directory..."
mkdir -p .rpms
mkdir -p .srpms
rm -frv .rpms/*
rm -frv .srpms/*
mv -vf ~/rpmbuild/RPMS/noarch/* .rpms/
mv -vf ~/rpmbuild/SRPMS/* .srpms/
echo "RPM was moved to the target directory."
