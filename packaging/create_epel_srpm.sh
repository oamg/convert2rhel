#!/bin/bash

SPECNAME=convert2rhel.spec

cleanup() {
  rm -f ${REPO_ROOT}/${SPECNAME}
  rm -rf ${REPO_ROOT}/dist/
  popd
}
CHANGE_RELEASE=true
# Do not change the release in spec, e.g. for Koji builds
[ "$1" = "--orig-release" ] && CHANGE_RELEASE=false

SCRIPTPATH=$(dirname "$0")
REPO_ROOT=${SCRIPTPATH}/..
pushd ${REPO_ROOT}

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

cp ${SCRIPTPATH}/${SPECNAME} ${SPECNAME}
rpmlint ${SPECNAME}

TIMESTAMP=`date +%Y%m%d%H%MZ -u`
GIT_BRANCH=$(git for-each-ref --format='%(objectname) %(refname:short)' refs/heads | head -n1 | awk "{print \$2}")
GIT_BRANCH=${GIT_BRANCH////_}  # Sanitize the git branch name (no "/" allowed for sed)
RELEASE="0"
[ "${GIT_BRANCH}" = "master" ] && RELEASE="100"
if [ "$CHANGE_RELEASE" = true ]; then
    # Suitable for Continous Delivery
    sed -i "s/1%{?dist}/${RELEASE}.${TIMESTAMP}.${GIT_BRANCH}%{?dist}/g" ${SPECNAME}
fi

rpmbuild -bs ${SPECNAME} --define "debug_package %{nil}" \
    --define "_sourcedir ${REPO_ROOT}/dist" \
    --define "_srcrpmdir ${REPO_ROOT}/SRPMS" || { cleanup; exit 1; }

rpmlint SRPMS/convert2rhel*.rpm

cleanup
