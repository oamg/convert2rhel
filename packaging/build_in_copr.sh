#!/bin/bash

# Make sure you have .copr.conf in the same directory as this script.
# The .copr.conf needs to contain the token from https://<copr URL>/api/.
# Currently it's set up to build the package in the Red Hat internal Copr.

cleanup() {
  rm -f convert2rhel.spec
  rm -rf dist/
  popd
}

BASEDIR=$(dirname "$0")
pushd ${BASEDIR}/..

rm -rf dist/ SRPMS/
echo "Creating a tarball for building the RPM ..."
if [ -x "$(command -v python3)" ]; then
  python3 setup.py sdist
elif [ -x "$(command -v python2)" ]; then
  python2 setup.py sdist
else
  echo "Error: Can't find python interpreter."
  exit 1
fi

cp ${BASEDIR}/convert2rhel.spec convert2rhel.spec
rpmlint convert2rhel.spec

TIMESTAMP=`date +%Y%m%d%H%MZ -u`
GIT_BRANCH=`git rev-parse --abbrev-ref HEAD`
GIT_BRANCH=${GIT_BRANCH////_}  # Sanitize the git branch name (no "/" allowed for sed)
sed -i "s/1%{?dist}/0.${TIMESTAMP}.${GIT_BRANCH}/g" convert2rhel.spec

rpmbuild -bs convert2rhel.spec --define "debug_package %{nil}" \
    --define "_sourcedir `pwd`/dist" \
    --define "_srcrpmdir `pwd`/SRPMS" \
    && { copr --config ${BASEDIR}/.copr.conf build mbocek/convert2rhel \
         SRPMS/convert2rhel-*.src.rpm & } \
    || { cleanup; exit 1; }

rpmlint SRPMS/convert2rhel*.rpm

cleanup
