#!/bin/bash

# Make sure you have .copr.conf in the same directory as this script.
# The .copr.conf needs to contain the token from https://<copr URL>/api/.
# Currently it's set up to build the package in the Red Hat internal Copr.

rm -rf dist/ SRPMS/
python2 setup.py sdist

cp convert2rhel.spec convert2rhel.spec.bak

TIMESTAMP=`date +%Y%m%d%H%MZ -u`
GIT_BRANCH=`git rev-parse --abbrev-ref HEAD`
sed -i "s/1%{?dist}/0.${TIMESTAMP}.${GIT_BRANCH}/g" convert2rhel.spec

rpmbuild -bs convert2rhel.spec --define "debug_package %{nil}" \
    --define "_sourcedir `pwd`/dist" \
    --define "_srcrpmdir `pwd`/SRPMS"

copr --config .copr.conf build mbocek/convert2rhel SRPMS/convert2rhel-*.src.rpm &

mv convert2rhel.spec.bak convert2rhel.spec
rm -rf dist/
