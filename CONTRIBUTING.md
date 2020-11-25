# Contributing to convert2rhel

## Coding guidelines
1. All python code must be python 2.6/2.7/3.6 compatible
1. The code should follow linting from pylint

## Unit tests
Our unit tests are run within containers. To first create the container images, run:

```bash
$ make images
```

Once images have been setup, you can now run unit tests within the containers using:

```bash
$ make tests
```

## Linting
Linting can be done locally using `virtualenv`.

```bash
# Setup a virtual environment
$ pip install virtualenv
$ virtualenv .venv --python=python2
$ source .venv/bin/activate

# Run pylint
$ pylint --rcfile=.pylintrc convert2rhel/
```

## Releasing a new version to EPEL

Q: Who's expected to release new versions of convert2rhel to EPEL?

A: Mainly the convert2rhel developers. Only members of [the convert2rhel-sig FAS group](https://src.fedoraproject.org/group/convert2rhel-sig) have the permissions to do so.
If you want to become a member of that group, [let us know](https://github.com/oamg/convert2rhel/#contact).

Q: When are we supposed to do that?

A: Whenever we decide that users of CentOS and Oracle Linux should be able to take advantage of the new fixes and features we introduce in upstream/GitHub.


The procedure below expects that [a new upstream GitHub release](https://github.com/oamg/convert2rhel/releases) has been created already.

```bash
$ # replace the <version_released_in_GitHub> below with the version for which you've created a release in GitHub
$ VER=<version_released_in_GitHub>  # e.g. VER=0.12
$ # replace the <your_FAS_user_name> below with your Fedora Account System user name
$ kinit <your_FAS_user_name>@FEDORAPROJECT.ORG  # see [1] on setting up Kerberos credentials
$ fedpkg clone convert2rhel convert2rhel-distgit  # to get the fedpkg utility, see [2]
$ cd convert2rhel-distgit

$ fedpkg switch-branch el6  # for EPEL 6
$ fedpkg pull  # make sure you work with the latest branch content
$ rm -rf convert2rhel*  # remove all the files related to the previous release
$ wget https://raw.githubusercontent.com/oamg/convert2rhel/master/packaging/convert2rhel.spec
$ spectool -g -A *.spec  # download the new version tarball from GitHub
$ fedpkg new-sources *.tar.gz  # upload the tarball to dist-git
$ fedpkg srpm
$ fedpkg lint  # make sure there are no errors or warnings in the lint output
$ git add -u
$ fedpkg clog  # generate a 'clog' file containing the last version changelog from the specfile
$ sed -i "1iVersion ${VER}\n" clog  # just add a summary line to the top of the commit description
$ fedpkg commit -F clog
$ fedpkg push
$ fedpkg scratch-build  # create a temporary build to see if the package builts successfully
$ # wait for the above command to finish
$ fedpkg build  # create the official build
$ fedpkg update  # -> this creates a Bodhi request; read [3] and play it by your ear
 
$ fedpkg switch-branch epel7  # for EPEL 7
$ # all the steps as for the branch 'el6' above
$ fedpkg switch-branch epel8  # for EPEL 8
$ # all the steps as for the branch 'el6' above
```

Related resources:

[1] https://fedoraproject.org/wiki/Infrastructure/Kerberos

[2] https://fedoraproject.org/wiki/Package_maintenance_guide

[3] https://fedoraproject.org/wiki/Bodhi
