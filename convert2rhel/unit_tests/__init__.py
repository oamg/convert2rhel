# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
__metaclass__ = type

import collections
import functools
import itertools
import os
import sys

import pytest
import six

from convert2rhel import (
    backup,
    breadcrumbs,
    exceptions,
    grub,
    main,
    pkghandler,
    subscription,
    systeminfo,
    toolopts,
    utils,
)
from convert2rhel.actions import STATUS_CODE, report
from convert2rhel.pkghandler import PackageInformation, PackageNevra
from convert2rhel.utils import run_subprocess


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock as six_mock


TMP_DIR = "/tmp/convert2rhel_test/"
NONEXISTING_DIR = os.path.join(TMP_DIR, "nonexisting_dir/")
NONEXISTING_FILE = os.path.join(TMP_DIR, "nonexisting.file")
# Dummy file for built-in open function
DUMMY_FILE = os.path.join(os.path.dirname(__file__), "dummy_file")
_MAX_LENGTH = 80


def create_pkg_information(
    packager=None,
    vendor=None,
    name=None,
    epoch="0",
    version=None,
    release=None,
    arch=None,
    fingerprint=None,
    signature=None,
):
    pkg_info = PackageInformation(
        packager,
        vendor,
        PackageNevra(name, epoch, version, release, arch),
        fingerprint,
        signature,
    )
    return pkg_info


class TestPkgObj:
    class PkgObjHdr:
        def sprintf(self, *args, **kwargs):
            return "RSA/SHA256, Sun Feb  7 18:35:40 2016, Key ID 73bde98381b46521"

    hdr = PkgObjHdr()


def create_pkg_obj(
    name,
    epoch=0,
    version="",
    release="",
    arch="",
    packager=None,
    from_repo="",
    manager="yum",
    vendor=None,
):
    class DumbObj:
        pass

    obj = TestPkgObj()
    obj.yumdb_info = DumbObj()
    obj.name = name
    obj.epoch = obj.e = epoch
    obj.version = obj.v = version
    obj.release = obj.r = release
    obj.evr = version + "-" + release
    obj.arch = arch
    obj.packager = packager
    if vendor:
        obj.vendor = vendor
    if manager == "yum":
        obj.rpmdb = six_mock.Mock()
        if from_repo:
            obj.yumdb_info.from_repo = from_repo
    elif manager == "dnf":
        if from_repo:
            obj._from_repo = from_repo
        else:
            obj._from_repo = "@@System"
    return obj


def mock(class_or_module, orig_obj, mock_obj):
    """
    This is a decorator to be applied to any test method that needs to mock
    some module/class object (be it function, method or variable). It replaces
    the original object with any arbitrary object. The original is still
    accessible through "<original object name>_orig" attribute.

    Parameters:
    class_or_module - module/class in which the original function/method is
                      defined
    orig_obj - name of the original object as a string
    mock_obj - object that will replace the orig_obj, for example:
               -- instance of some fake function
               -- string

    Example:
    @tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    -- replaces the original run_subprocess function from the utils module
       with the RunSubprocessMocked function.
    @tests.mock(logging.FileHandler, "_open", FileHandler_open_mocked())
    -- replaces the original _open method of the FileHandler class within
       the logging module with the FileHandler_open_mocked function.
    @tests.mock(gpgkey, "gpg_key_system_dir", "/nonexisting_dir/")
    -- replaces the gpgkey module-scoped variable gpg_key_system_dir with the
       "/nonexisting_dir/" string
    """

    def wrap(func):
        # The @wraps decorator below makes sure the original object name
        # and docstring (in case of a method/function) are preserved.
        @functools.wraps(func)
        def wrapped_fn(*args, **kwargs):
            # Save temporarily the original object
            orig_obj_saved = getattr(class_or_module, orig_obj)
            # Replace the original object with the mocked one
            setattr(class_or_module, orig_obj, mock_obj)
            # To be able to use the original object within the mocked object
            # (e.g. to have the mocked function just as a wrapper for the
            # original function), save it as a temporary attribute
            # named "<original object name>_orig"
            orig_obj_attr = "%s_orig" % orig_obj
            setattr(class_or_module, orig_obj_attr, orig_obj_saved)
            # Call the decorated test function
            return_value = None
            try:
                try:
                    return_value = func(*args, **kwargs)
                except:
                    raise
            finally:
                # NOTE: finally need to be used in this way for Python 2.4
                # Restore the original object
                setattr(class_or_module, orig_obj, orig_obj_saved)
                # Remove the temporary attribute holding the original object
                delattr(class_or_module, orig_obj_attr)
            return return_value

        return wrapped_fn

    return wrap


def safe_repr(obj, short=False):
    """
    Safetly calls repr().
    Returns a truncated string if repr message is too long.
    """
    try:
        result = repr(obj)
    except Exception:
        result = object.__repr__(obj)
    if not short or len(result) < _MAX_LENGTH:
        return result
    return result[:_MAX_LENGTH] + " [truncated]..."


def get_pytest_marker(request, mark_name):
    """
    Get a pytest mark from a request.

    The pytest API to retrieve a mark. This function is a compatibility shim to retrieve the value.

    Use this function instead of pytest's `request.node.get_closest_marker(mark_name)` so that it will work on all versions of RHEL that we are targeting.
    .. seealso::
        * `pytest's get_closest_marker() function which this function wraps <https://docs.pytest.org/en/stable/reference/reference.html#pytest.nodes.Node.get_closest_marker>`_
        * `A technique you might use where you would need to use this function to retrieve a mark's value. <https://docs.pytest.org/en/stable/how-to/fixtures.html#using-markers-to-pass-data-to-fixtures>`_
    """
    if pytest.__version__.split(".") <= ["3", "6", "0"]:
        mark = request.node.get_marker(mark_name)
    else:
        mark = request.node.get_closest_marker(mark_name)

    return mark


def is_rpm_based_os():
    """Check if the OS is rpm based."""
    try:
        run_subprocess(["rpm"])
    except EnvironmentError:
        return False
    else:
        return True


class MockFunctionObject:
    """
    Base class for mocked functions.

    * Mocked functions which use this will have all the capabilities of mock.Mock().
    * Subclasses must provide a `spec`, the function that is being mocked, as either an attribute on
      the class or passed in to `__init__()`. This allows the MockFunctionObject to throw an
      exception if it is called with an incorrect number of positional arguments or an unknown
      keyword arg. If a spec is given through both a class attribute and parameter to `__init__`,
      the parameter takes precedence.
      * There is also a method_spec attribute.  This is set instead of spec, then the function will
        be treated as a metod.  There is no equivalent to pass this as a parameter.
    * The naming convention for Mock Functions is that base classes end in `*Object`
      and classes which are ready to replace a function end in `*Mocked`.
    """

    spec = None
    method_spec = None

    def __init__(self, **kwargs):
        if self.spec and self.method_spec:
            raise TypeError("Cannot define both spec and method spec")

        if "spec" not in kwargs:
            if self.spec:
                # mock detects self.spec as a method and self.__class__.spec as a function
                kwargs["spec"] = self.__class__.spec
            elif self.method_spec:
                kwargs["spec"] = self.method_spec
            else:
                raise TypeError(
                    "MockFunctionObjects require the spec parameter to be set as an attribute on the class or passed in when instantiating."
                )

        self._mock = six_mock.MagicMock(**kwargs)

    def __getattr__(self, name):
        # Need to use a base class's methods for looking up attributes which might not exist
        # to avoid infinite recursion. (This could be called before self._mock has been created)
        _mock = super(MockFunctionObject, self).__getattribute__("_mock")
        return getattr(_mock, name)

    def __call__(self, *args, **kwargs):
        return self._mock(*args, **kwargs)


class SysExitCallableObject(MockFunctionObject):
    """
    Base class for any mock function which needs to raise SystemExit() when called.
    """

    def __init__(self, msg, **kwargs):
        self.msg = msg
        super(SysExitCallableObject, self).__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        super(SysExitCallableObject, self).__call__(*args, **kwargs)
        return sys.exit(self.msg)


class CriticalErrorCallableObject(MockFunctionObject):
    """
    Base class for any mock function which raises the CriticalError Exception.
    """

    def __init__(self, id_, title, description=None, diagnosis=None, remediation=None, variables=None, **kwargs):
        self.id = id_
        self.title = title
        self.description = description
        self.diagnosis = diagnosis
        self.remediation = remediation
        self.variables = {} if variables is None else variables

        super(CriticalErrorCallableObject, self).__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        super(CriticalErrorCallableObject, self).__call__(*args, **kwargs)
        raise exceptions.CriticalError(
            self.id,
            self.title,
            description=self.description,
            diagnosis=self.diagnosis,
            remediation=self.remediation,
            variables=self.variables,
        )


#
# actions.report mocks
#


class SummaryAsJsonMocked(MockFunctionObject):
    spec = report.summary_as_json


#
# backup mocks
#


class RemovePkgsMocked(MockFunctionObject):
    """
    Mock for the remove_pkgs function.

    This differs from Mock in that it:
    * Makes it easy to check just the pkgs passed in to remove.
    """

    spec = backup.remove_pkgs

    def __init__(self, **kwargs):
        self.pkgs = None

        super(RemovePkgsMocked, self).__init__(**kwargs)

    def __call__(self, pkgs_to_remove, *args, **kwargs):
        self.pkgs = pkgs_to_remove

        return super(RemovePkgsMocked, self).__call__(pkgs_to_remove, *args, **kwargs)


#
# breadcrumbs mocks
#


class CollectEarlyDataMocked(MockFunctionObject):
    spec = breadcrumbs.Breadcrumbs.collect_early_data


class FinishCollectionMocked(MockFunctionObject):
    spec = breadcrumbs.Breadcrumbs.finish_collection


class PrintDataCollectionMocked(MockFunctionObject):
    spec = breadcrumbs.Breadcrumbs.print_data_collection


#
# main mocks
#


class InitializeLoggerMocked(MockFunctionObject):
    spec = main.initialize_logger


class MainLockedMocked(MockFunctionObject):
    spec = main.main_locked


class RollbackChangesMocked(MockFunctionObject):
    spec = main.rollback_changes


class ShowEulaMocked(MockFunctionObject):
    spec = main.show_eula


#
# pkghandler mocks
#


class CallYumCmdMocked(MockFunctionObject):
    """
    Mock for the call_yum_cmd function.

    This differs from Mock in that it:
    * Allows an easy way to just check command and args.
    * Has special handling to make failing a single time and then succeeding easy.
    """

    spec = pkghandler.call_yum_cmd

    def __init__(self, return_code=0, return_string="Test output", fail_once=False, **kwargs):
        self.command = ""
        self.args = []

        if "side_effect" not in kwargs:
            side_effect = itertools.repeat((return_string, return_code))
            if fail_once:
                side_effect = itertools.chain([(return_string, 1)], side_effect)

        super(CallYumCmdMocked, self).__init__(side_effect=side_effect, **kwargs)

    def __call__(self, command, *other_args, **kwargs):
        self.command = command
        self.args = kwargs.get("args", [])

        return super(CallYumCmdMocked, self).__call__(command, *other_args, **kwargs)


class ClearVersionlockMocked(MockFunctionObject):
    spec = pkghandler.clear_versionlock


class GetInstalledPkgInformationMocked(MockFunctionObject):
    spec = pkghandler.get_installed_pkg_information

    # Prebake several return values for a couple different use cases

    # fingerprints
    pkg1 = create_pkg_information(name="pkg1", fingerprint="199e2f91fd431d51")  # RHEL
    pkg2 = create_pkg_information(name="pkg2", fingerprint="72f97b74ec551f03")  # OL
    pkg3 = create_pkg_information(
        name="gpg-pubkey", version="1.0.0", release="1", arch="x86_64", fingerprint="199e2f91fd431d51"  # RHEL
    )

    # Oracle Kernel Packages
    kernel1 = create_pkg_information(
        name="kernel",
        version="3.10.0",
        release="1127.19.1.el7",
        arch="x86_64",
        packager="Oracle",
    )
    kernel2 = create_pkg_information(
        name="kernel-uek",
        version="0.1",
        release="1",
        arch="x86_64",
        packager="Oracle",
    )
    kernel3 = create_pkg_information(
        name="kernel-headers",
        version="0.1",
        release="1",
        arch="x86_64",
        packager="Oracle",
    )
    kernel4 = create_pkg_information(
        name="kernel-uek-headers",
        version="0.1",
        release="1",
        arch="x86_64",
        packager="Oracle",
    )
    kernel5 = create_pkg_information(
        name="kernel-firmware",
        version="0.1",
        release="1",
        arch="x86_64",
        packager="Oracle",
    )
    kernel6 = create_pkg_information(
        name="kernel-uek-firmware",
        version="0.1",
        release="1",
        arch="x86_64",
        packager="Oracle",
    )

    prebaked_pkgs = {
        "fingerprints": [pkg1, pkg2, pkg3],
        "kernels": [kernel1, kernel2, kernel3, kernel4, kernel5, kernel6],
        "empty": [],
    }

    def __init__(self, pkg_selection=None, **kwargs):
        if "return_value" in kwargs:
            if pkg_selection is not None:
                raise TypeError("You cannot use return_value together with pkg_selection.")
        else:
            if pkg_selection is not None:
                kwargs["return_value"] = self.prebaked_pkgs[pkg_selection]

        super(GetInstalledPkgInformationMocked, self).__init__(**kwargs)


class GetInstalledPkgsWDifferentFingerprintMocked(GetInstalledPkgInformationMocked):
    spec = pkghandler.get_installed_pkgs_w_different_fingerprint


class GetInstalledPkgsByFingerprintMocked(GetInstalledPkgInformationMocked):
    spec = pkghandler.get_installed_pkgs_by_fingerprint


class GetPackagesToRemoveMocked(GetInstalledPkgsWDifferentFingerprintMocked):
    spec = pkghandler.get_packages_to_remove


class GetThirdPartyPkgsMocked(GetInstalledPkgInformationMocked):
    spec = pkghandler.get_third_party_pkgs


class FormatPkgInfoMocked(MockFunctionObject):
    spec = pkghandler.format_pkg_info


class RemovePkgsUnlessFromRedhatMocked(MockFunctionObject):
    spec = pkghandler.remove_pkgs_unless_from_redhat


#
# subscription mocks
#


class RegisterSystemMocked(MockFunctionObject):
    """
    Mock of the register_system() function.

    It just adds a spec for the function on top of all the standard mock functionality.
    """

    spec = subscription.register_system


class UnregisterSystemMocked(MockFunctionObject):
    """
    Mock of the unregister_system() function.

    It just adds a spec for the function on top of all the standard mock functionality.
    """

    spec = subscription.unregister_system


#
# systeminfo mocks
#


class PrintSystemInformationMocked(MockFunctionObject):
    spec = systeminfo.system_info.print_system_information


class ResolveSystemInfoMocked(MockFunctionObject):
    spec = systeminfo.system_info.resolve_system_info


#
# toolopts mocks
#


class CLIMocked(MockFunctionObject):
    spec = toolopts.CLI


#
# utils mocks
#


class DownloadPkgMocked(MockFunctionObject):
    """
    Mock for the download_pkgs function.

    This differs from Mock in that it:
    * Makes it easy to check each of the parameters to the function individually.
    """

    spec = utils.download_pkg

    def __init__(self, **kwargs):
        self.pkg = None
        self.dest = None
        self.enable_repos = []
        self.disable_repos = []

        super(DownloadPkgMocked, self).__init__(**kwargs)

    def __call__(self, pkg, *args, **kwargs):
        self.pkg = pkg
        self.dest = kwargs.get("dest", None)
        self.enable_repos = kwargs.get("enable_repos", [])
        self.disable_repos = kwargs.get("disable_repos", [])

        return super(DownloadPkgMocked, self).__call__(pkg, *args, **kwargs)


class PromptUserMocked(MockFunctionObject):
    spec = utils.prompt_user

    def __init__(self, retries=0, **kwargs):
        self.retries = retries
        self.prompts = collections.Counter()

        if "return_value" not in kwargs:
            kwargs["return_value"] = "test"

        super(PromptUserMocked, self).__init__(**kwargs)

    def __call__(self, question, *args, **kwargs):
        return_value = super(PromptUserMocked, self).__call__(question, *args, **kwargs)
        self.prompts[question] += 1

        # Emulate the user not providing a valid value until retries times.
        if self.prompts[question] <= self.retries:
            return ""

        return return_value


class RequireRootMocked(MockFunctionObject):
    spec = utils.require_root


class RunSubprocessMocked(MockFunctionObject):
    """
    Mock for the run_subprocess function.

    This differs from Mock in that it:
    * Makes it easy to check just the cmds passed to the function.
    """

    spec = utils.run_subprocess

    def __init__(self, return_code=None, return_string=None, **kwargs):
        self.cmd = ""
        self.cmds = []

        if "return_value" in kwargs:
            if return_code is not None or return_string is not None:
                raise TypeError("You cannot use return_code together or return_string with return_value.")
        else:
            return_code = 0 if return_code is None else return_code
            return_string = "Test output" if return_string is None else return_string
            kwargs["return_value"] = (return_string, return_code)

        super(RunSubprocessMocked, self).__init__(**kwargs)

    def __call__(self, cmd, *args, **kwargs):
        self.cmd = cmd
        self.cmds.append(cmd)

        return super(RunSubprocessMocked, self).__call__(cmd, *args, **kwargs)


class RunCmdInPtyMocked(RunSubprocessMocked):
    """
    Mock for utils.run_cmd_in_pty.

    It offers the same features as RunSubrocessMocked.
    """

    spec = utils.run_cmd_in_pty


class StoreContentToFileMocked(MockFunctionObject):
    spec = utils.store_content_to_file

    def __init__(self, **kwargs):
        self.filename = None
        self.content = None

        super(StoreContentToFileMocked, self).__init__(**kwargs)

    def __call__(self, filename, content, *args, **kwargs):
        self.filename = filename
        self.content = content

        super(StoreContentToFileMocked, self).__call__(filename, content, *args, **kwargs)

        return True


def run_subprocess_side_effect(*stubs):
    """Side effect function for utils.run_subprocess.
    :type stubs: Tuple[Tuple[command, ...], Tuple[command_stdout, exit_code]]

    Allows you to parametrize the mocking by providing list of stubs

    if run_subprocess called with args, which are not specified in
    stubs, then no mocking happening and a real subprocess call will be made.

    Example:
    >>> run_subprocess_mock = mock.Mock(
    >>>     side_effect=run_subprocess_side_effect(
    >>>         (("uname",), ("5.8.0-7642-generic\n", 0)),
    >>>         (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
    >>>         (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
    >>>     )
    >>> )
    """

    def factory(*args, **kwargs):
        for kws, result in stubs:
            if all(kw in args[0] for kw in kws):
                return result

        return run_subprocess(*args, **kwargs)

    return factory


def mock_decorator(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapped


#: Used as a sentinel value for assert_action_result() so we only check
#: attributes that the test has asked for.
_NO_USER_VALUE = object()


def assert_actions_result(
    instance,
    level=_NO_USER_VALUE,
    id=_NO_USER_VALUE,
    title=_NO_USER_VALUE,
    description=_NO_USER_VALUE,
    diagnosis=_NO_USER_VALUE,
    remediation=_NO_USER_VALUE,
    variables=_NO_USER_VALUE,
):
    """Helper function to assert result set by Actions Framework."""

    if level and level != _NO_USER_VALUE:
        assert instance.result.level == STATUS_CODE[level]

    if id and id != _NO_USER_VALUE:
        assert instance.result.id == id

    if title and title != _NO_USER_VALUE:
        assert title in instance.result.title

    if description and description != _NO_USER_VALUE:
        assert description in instance.result.description

    if diagnosis and diagnosis != _NO_USER_VALUE:
        assert diagnosis in instance.result.diagnosis

    if remediation and remediation != _NO_USER_VALUE:
        assert remediation in instance.result.remediation

    if variables and variables != _NO_USER_VALUE:
        assert variables in instance.result.variables


class EFIBootInfoMocked:
    def __init__(
        self,
        current_bootnum="0001",
        next_boot=None,
        boot_order=("0001", "0002"),
        entries=None,
        exception=None,
    ):
        self.current_bootnum = current_bootnum
        self.next_boot = next_boot
        self.boot_order = boot_order
        self.entries = entries
        self.set_default_efi_entries()
        self._exception = exception

    def __call__(self):
        """Tested functions call existing object instead of creating one.
        The object is expected to be instantiated already when mocking
        so tested functions are not creating new object but are calling already
        the created one. From the point of the tested code, the behaviour is
        same now.
        """
        if not self._exception:
            return self
        raise self._exception  # pylint: disable=raising-bad-type

    def set_default_efi_entries(self):
        if not self.entries:
            self.entries = {
                "0001": grub.EFIBootLoader(
                    boot_number="0001",
                    label="Centos Linux",
                    active=True,
                    efi_bin_source=r"HD(1,GPT,28c77f6b-3cd0-4b22-985f-c99903835d79,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)",
                ),
                "0002": grub.EFIBootLoader(
                    boot_number="0002",
                    label="Foo label",
                    active=True,
                    efi_bin_source="FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)",
                ),
            }


class MinimalRestorable(backup.RestorableChange):
    def __init__(self):
        self.called = collections.defaultdict(int)
        super(MinimalRestorable, self).__init__()

    def enable(self):
        self.called["enable"] += 1
        super(MinimalRestorable, self).enable()

    def restore(self):
        self.called["restore"] += 1
        super(MinimalRestorable, self).restore()
