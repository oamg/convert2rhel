#!/bin/bash

set -e

# Run this script on CentOS Linux/OL/RHEL 7/8/9
echo "Creating a tarball for building the RPM ..."
if [ -x "$(command -v python3)" ]; then
  python3 setup.py sdist
elif [ -x "$(command -v python2)" ]; then
  python2 setup.py sdist
else
  echo "Error: Can't find python interpreter."
  exit 1
fi
echo "Setting up RPM tree in \$HOME"
rpmdev-setuptree
cp -v dist/* ~/rpmbuild/SOURCES
echo "Building the RPM ..."
if [ $container == "podman" ]; then
  echo "Detected running in podman, will not clean up"
  rpmbuild -ba packaging/convert2rhel.spec --define "debug_package %{nil}"
else
  echo "Detected running locally, cleaning up afterwards"
  rpmbuild -ba packaging/convert2rhel.spec --define "debug_package %{nil}" --clean
fi
echo "RPM was built successfully"
echo "Cleaning up the target directory..."
mkdir -p .rpms
mkdir -p .srpms
mv -vf ~/rpmbuild/RPMS/noarch/convert2rhel* .rpms/
mv -vf ~/rpmbuild/SRPMS/convert2rhel* .srpms/
echo "RPM was moved to the target directory."
