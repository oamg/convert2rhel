%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{!?python2_sitearch: %global python2_sitearch %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib(1))")}

Name:           convert2rhel
Version:        0.9
Release:        1%{?dist}
Summary:        Automates the conversion of RHEL derivative distributions to RHEL

License:        GPLv3
URL:            https://github.com/oamg/convert2rhel
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python-devel
BuildRequires:  python-setuptools
%if ! 0%{?rhel:1}
BuildRequires:  buildsys-macros
%endif
Requires:       dbus-python
Requires:       gnupg2
Requires:       m2crypto
Requires:       python
# Warning: The python-dateutil package is available since OL/CentOS 5.10
#          If the convert2rhel is to be installed on an older system, add
#          any repo that contains the package or install it manually first
#          from a downloaded rpm.
Requires:       python-dateutil
Requires:       python-dmidecode
Requires:       python-iniparse
# Warning: The python-ethtool package is available since OL/CentOS 5.7
Requires:       python-ethtool
Requires:       rpm
Requires:       sed
Requires:       usermode
# Warning: The virt-what package is available since OL/CentOS 5.7
Requires:       virt-what
Requires:       yum
Requires:       yum-utils
%if 0%{?rhel} && 0%{?rhel} <= 5
# Warning: The python-simplejson package is available since OL/CentOS 5.7
Requires:       python-simplejson
%endif
%if 0%{?rhel} && 0%{?rhel} == 6
Requires:       python-decorator
Requires:       python-six
Requires:       pygobject2
%endif
%if 0%{?rhel} && 0%{?rhel} >= 7
Requires:       gobject-introspection
Requires:       pygobject3-base
Requires:       python-decorator
Requires:       python-inotify
Requires:       python-setuptools
Requires:       python-six
Requires:       python-syspurpose
%endif

%description
The purpose of the convert2rhel tool is to provide an automated way of
converting the installed other-than-RHEL OS distribution to Red Hat Enterprise
Linux (RHEL). The tool replaces all the original OS-signed packages with the
RHEL ones. Available are conversions of CentOS 5/6/7 and Oracle Linux 5/6/7 to
the respective major version of RHEL.

%prep
%setup -q

%build
%{__python2} setup.py build
%{__python2} setup.py build_manpage

# Do not include unit test in the package
rm -rf build/lib/%{name}/unit_tests
# Do not include the man building script
rm -rf build/lib/man

%install
%{__python2} setup.py install --skip-build --root %{buildroot}

# Move system version and architecture specific tool data
# to /usr/share/convert2rhel
rm -rf %{buildroot}%{python2_sitelib}/%{name}/data
install -d %{buildroot}%{_datadir}/%{name}
cp -a build/lib/%{name}/data/version-independent/. \
      %{buildroot}%{_datadir}/%{name}
cp -a build/lib/%{name}/data/%{rhel}/%{_arch}/. \
      %{buildroot}%{_datadir}/%{name}

install -d -m 755 %{buildroot}%{_mandir}/man8
install -p man/%{name}.8 %{buildroot}%{_mandir}/man8/

%files
%{_bindir}/%{name}

%{python2_sitelib}/%{name}*
%{_datadir}/%{name}

%{!?_licensedir:%global license %%doc}
%license LICENSE
%doc README.md
%{_mandir}/man8/%{name}.8*

%changelog
* Fri Dec 13 2019 Michal Bocek <mbocek@redhat.com> 0.9-1
- basic rollback capability up to the point before replacing all pkgs
- added basic system tests running on CentOS 5/6/7 Vagrant boxes
- unit tests can be run now in CentOS 5/6/7 Docker images
- improved handling of kernel installation corner cases
- added possibility to upgrade i386 OL5
- added --debug option
- license changed from GPLv2 to GPLv3
- autogenerating manpage
- collecting output of 'rpm -Va' before the conversion
- added possibility to use custom repositories instead of RHSM
- removed bundled rpms and repomapping for the public release

* Fri Nov 10 2017 Michal Bocek <mbocek@redhat.com> 0.8-1
- added support for conversion from CentOS/OL 5 to RHEL 5
- the oldest supported version is CentOS/OL 5.6

* Fri Mar 31 2017 Michal Bocek <mbocek@redhat.com> 0.7-1
- remove shebang from all the python scripts
- update spec to create arch specific rpms
- move all the tool data into /usr/share/convert2rhel/
- remove ppc64 RHEL 6 data - CentOS 6 and OL 6
  were not released for this arch
- create new SystemReleaseFile class for handling
  /etc/system-release
- do not print traceback on keyboard interrupt
- move initializing Red Hat GPG key fingerprint variable
  from main to gpgkey.py
- update configs to add centos-release* to blacklist

* Wed Jul 20 2016 Michal Bocek <mbocek@redhat.com> 0.6-1
- Code refactored and split into new files
- Added support for CentOS/OL 6 to RHEL 6 conversion
- Created 'framework' for unit tests
- Added logging to a file

* Wed Jun 15 2016 Michal Bocek <mbocek@redhat.com> 0.5-1
- The tool renamed to convert2rhel.
- All the original kernels are removed during the conversion now.
- Added man page.
- EULA needs to be accepted before the conversion.
- Packages are filtered per signature, not per vendor.
- Added support for conversions from Oracle Linux 7 to RHEL 7.
- Added support for --auto-attach, --activationkey and --org
  subscription-manager arguments.

* Mon May 09 2016 Michal Bocek <mbocek@redhat.com> 0.4-1
- Added both interactive and cmd line option for choosing RHEL variant.
- Added autodetection of platform architecture.
- Implemented handling of unsuccessful subscription attachment.
- Added a config file for each supported distribution.
- Added possibility to blacklist conflicting pkgs.

* Thu Apr 28 2016 Michal Bocek <mbocek@redhat.com> 0.3-1
- Added determining appropriate RHEL repository to use for upgrade.

* Mon Apr 25 2016 Michal Bocek <mbocek@redhat.com> 0.2-1
- Added dark matrix data

* Tue Apr 19 2016 Michal Bocek <mbocek@redhat.com> 0.1-1
- Initial RPM release
