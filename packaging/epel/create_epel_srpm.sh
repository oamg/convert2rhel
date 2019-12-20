#!/bin/bash

cleanup() {
  rm -f ${REPO_ROOT}/convert2rhel.spec
  rm -rf ${REPO_ROOT}/dist/
  popd
}

SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
REPO_ROOT=${SCRIPTPATH}/../..
pushd ${REPO_ROOT}

rm -rf dist/ SRPMS/
python2 setup.py sdist

cp ${SCRIPTPATH}/convert2rhel.spec convert2rhel.spec
rpmlint convert2rhel.spec

TIMESTAMP=`date +%Y%m%d%H%MZ -u`
GIT_BRANCH=`git rev-parse --abbrev-ref HEAD`
RELEASE="0"
[ "${GIT_BRANCH}" = "master" ] && RELEASE="1"
sed -i "s/1%{?dist}/${RELEASE}.${TIMESTAMP}.${GIT_BRANCH}%{?dist}/g" convert2rhel.spec

rpmbuild -bs convert2rhel.spec --define "debug_package %{nil}" \
    --define "_sourcedir ${REPO_ROOT}/dist" \
    --define "_srcrpmdir ${REPO_ROOT}/SRPMS" || { cleanup; exit 1; }

rpmlint SRPMS/convert2rhel*.rpm

cleanup
