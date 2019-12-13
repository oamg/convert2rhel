#!/bin/bash
# Run this script on CentOS/OL/RHEL 5 in the root of the cloned convert2rhel repo
python setup.py sdist --formats=gztar
mkdir -p /usr/src/redhat/SOURCES
rm -rf /usr/src/redhat/{SOURCES,SRPMS}/*
rm -rf /var/tmp/convert2rhel*
cp dist/* /usr/src/redhat/SOURCES
rpmbuild -ba convert2rhel.spec
