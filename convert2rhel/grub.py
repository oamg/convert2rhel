# -*- coding: utf-8 -*-
#
# Copyright(C) 2021 Red Hat, Inc.
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

import logging
import os
import re
import shutil

from convert2rhel import systeminfo, utils

logger = logging.getLogger(__name__)

EFI_MOUNTPOINT = "/boot/efi/"
"""The path to the required mountpoint for ESP."""

CENTOS_EFIDIR_CANONICAL_PATH = os.path.join(EFI_MOUNTPOINT, "EFI/centos/")
"""The canonical path to the default efi directory on for CentOS Linux system."""

RHEL_EFIDIR_CANONICAL_PATH = os.path.join(EFI_MOUNTPOINT, "EFI/redhat/")
"""The canonical path to the default efi directory on for RHEL system."""

# TODO(pstodulk): following constants are valid only for x86_64 arch
DEFAULT_INSTALLED_EFIBIN_FILENAMES = ("shimx64.efi", "grubx64.efi")
"""Filenames of the EFI binary files that could be by default instaled on the system.

Sorted by the recommended preferences. The first one is most preferred, but it
is provided by the shim rpm which does not have to be installed on the system.
In case it's missing, another files should be used instead.
"""


class BootloaderError(Exception):
    """The generic error related to this module."""

    def __init__(self, message):
        super(BootloaderError, self).__init__(message)
        self.message = message

class UnsupportedEFIConfiguration(BootloaderError):
    """Raised when the bootloader EFI configuration seems unsupported.

    E.g. when we expect the ESP is mounted to /boot/efi but it is not.
    """
    pass


class NotUsedEFI(BootloaderError):
    """Raised when expected a use on EFI only but BIOS is detected."""
    pass


class InvalidPathEFI(BootloaderError):
    """Raise when path to EFI is invalid."""
    pass


def is_efi():
    """Return True if EFI is used."""
    return os.path.exists("/sys/firmware/efi")


def is_secure_boot():
    """Return True if the secure boot is enabled."""
    if not is_efi():
        return False
    try:
        stdout, ecode = utils.run_subprocess("mokutil --sb-state", print_output=False)
    except OSError:
        return False
    if ecode or "enabled" not in stdout:
        return False
    return True


def _log_critical_error(title):
        logger.critical(
            "%s\n"
            "The migration of the bootloader setup was not successful.\n"
            "Do not reboot your machine before the manual check of the\n"
            "bootloader configuration. Ensure grubenv and grub.cfg files\n"
            "are present inside the /boot/efi/EFI/redhat/ directory and\n"
            "the new bootloader entry for Red Hat Enterprise Linux exist\n"
            "(check `efibootmgr -v` output).\n"
            "The entry should point to '\\EFI\\redhat\\shimx64.efi'." % title
        )


def _get_partition(directory):
    """Return the disk partition for the specified directory.

    Raise BootloaderError if the partition cannot be detected.
    """
    stdout, ecode = utils.run_subprocess(
        "/usr/sbin/grub2-probe --target=device %s" % directory, print_output=False
    )
    if ecode or not stdout:
        logger.error("grub2-probe ended with non-zero exit code.\n%s" % stdout)
        raise BootloaderError("Cannot get device information for %s." % directory)
    return stdout.strip()


def get_boot_partition():
    """Return the disk partition with /boot present.

    Raise BootloaderError if the partition cannot be detected.
    """
    return _get_partition("/boot")


def get_efi_partition():
    """Return the EFI System Partition (ESP).

    Raise NotUsedEFI if EFI is not detected.
    Raise UnsupportedEFIConfiguration when ESP is not mounted where expected.
    Raise BootloaderError if the partition cannot be obtained from GRUB.
    """
    if not is_efi():
        raise NotUsedEFI("Cannot get ESP when BIOS is used.")
    if not os.path.exists(EFI_MOUNTPOINT) or not os.path.ismount(EFI_MOUNTPOINT):
        raise UnsupportedEFIConfiguration(
            "The EFI has been detected but the ESP is not mounted"
            " in /boot/efi as required."
        )
    return _get_partition(EFI_MOUNTPOINT)


def _get_blk_device(device):
    """Get the block device.

    In case of the block device itself (e.g. /dev/sda) returns just the block
    device. For a partition, returns its block device:
        /dev/sda  -> /dev/sda
        /dev/sda1 -> /dev/sda

    Raise ValueError on empty / None device
    Raise the BootloaderError when cannot get the block device.
    """
    if not device:
        raise ValueError("The device must be speficied.")
    stdout, ecode = utils.run_subprocess("lsblk -spnlo name %s" % device, print_output=False)
    if ecode:
        logger.error("Cannot get the block device for '%s'." % device)
        logger.debug("lsblk ... output:\n-----\n%s\n-----" % stdout)
        raise BootloaderError("Cannot get the block device")

    return stdout.strip().splitlines()[-1].strip()


def _get_device_number(device):
    """Return dict with 'major' and 'minor' number of specified device/partition.

    Raise ValueError on empty / None device
    """
    if not device:
        raise ValueError("The device must be specified.")
    stdout, ecode = utils.run_subprocess("lsblk -spnlo MAJ:MIN %s" % device, print_output=False)
    if ecode:
        logger.error("Cannot get information about the '%s' device." % device)
        logger.debug("lsblk ... output:\n-----\n%s\n-----" % stdout)
        return None
    # for partitions the output contains multiple lines (for the partition
    # and all parents till the devices itself). We want maj:min number just
    # for the specified device/partition, so take the first line only
    majmin = stdout.splitlines()[0].strip().split(":")
    return {"major": int(majmin[0]), "minor": int(majmin[1])}


def get_grub_device():
    """Get the block device where GRUB is located.

    We assume GRUB is on the same device as /boot (or ESP).
    Raise UnsupportedEFIConfiguration when EFI detected but ESP
          has not been discovered.
    Raise BootloaderError if the block device cannot be obtained.
    """
    # in 99% it should not matter to distinguish between /boot and /boot/efi,
    # but seatbelt is better
    partition = get_efi_partition() if is_efi() else get_boot_partition()
    return _get_blk_device(partition)


class EFIBootLoader(object):
    """Representation of an EFI boot loader entry"""

    def __init__(self, boot_number, label, active, efi_bin_source):
        self.boot_number = boot_number
        """Expected string, e.g. '0001'. """

        self.label = label
        """Label of the EFI entry. E.g. 'Centos'"""

        self.active = active
        """True when the EFI entry is active (asterisk is present after the boot number)"""

        self.efi_bin_source = efi_bin_source
        """Source of the EFI binary.

        It could contain various values, e.g.:
            FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
            HD(1,GPT,28c77f6b-3cd0-4b22-985f-c99903835d79,0x800,0x12c000)/File(\\EFI\\redhat\\shimx64.efi)
            PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
        """

    def __eq__(self, other):
        return all([
            self.boot_number == other.boot_number,
            self.label == other.label,
            self.active == other.active,
            self.efi_bin_source == other.efi_bin_source,
        ])

    def __ne__(self, other):
        return not self.__eq__(other)

    def is_referring_to_file(self):
        """Return True when the boot source is a file.

        Some sources could refer e.g. to PXE boot. Return true if the source
        refers to a file ("ends with /Files(...path...)")

        Does not matter whether the file exists or not.
        """
        return "/File(\\" in self.efi_bin_source

    @staticmethod
    def _efi_path_to_canonical(efi_path):
        return os.path.join(EFI_MOUNTPOINT, efi_path.replace("\\", "/").lstrip("/"))


    def get_canonical_path(self):
        """Return expected canonical path for the referred EFI bin or None.

        Return None in case the entry is not referring to any EFI bin
        (e.g. when refers to a PXE boot).
        """
        if not self.is_referring_to_file():
            return None
        match = re.search(r"/File\((?P<path>\\.*)\)$", self.efi_bin_source)
        if not match:
            raise BootloaderError("Cannot get the path to EFI binary for boot number: %s" % self.boot_number)
        return EFIBootLoader._efi_path_to_canonical(match.groups("path")[0])


class EFIBootInfo(object):
    """Data about the current EFI boot configuration.

    Raise BootloaderError when cannot obtain info about the EFI configuration.
    Raise NotUsedEFI when BIOS is detected.
    Raise UnsupportedEFIConfiguration when ESP is not mounted where expected.
    """

    def __init__(self):
        if not is_efi():
            raise NotUsedEFI("Cannot collect data about EFI on BIOS system.")
        brief_stdout, ecode = utils.run_subprocess("/usr/sbin/efibootmgr", print_output=False)
        verbose_stdout, ecode2 = utils.run_subprocess("/usr/sbin/efibootmgr -v", print_output=False)
        if ecode or ecode2:
            raise BootloaderError("Cannot get information about EFI boot entries.")

        self.current_boot = None
        """The boot number (str) of the current boot."""
        self.next_boot = None
        """The boot number (str) of the next boot - if set."""
        self.boot_order = None
        """The tuple of the EFI boot loader entries in the boot order."""
        self.entries = {}
        """The EFI boot loader entries {'boot_number': EFIBootLoader}"""
        self.efi_partition = get_efi_partition()
        """The EFI System Partition (ESP)"""

        self._parse_efi_boot_entries(brief_stdout, verbose_stdout)
        self._parse_current_boot(brief_stdout)
        self._parse_boot_order(brief_stdout)
        self._parse_next_boot(brief_stdout)

    def _parse_efi_boot_entries(self, brief_data, verbose_data):
        """Return dict of EFI boot loader entries: {"<boot_number>": EFIBootLoader}"""
        self.entries = {}
        regexp_entry = re.compile(r"^Boot(?P<bootnum>[0-9]+)[\s*]\s*(?P<label>[^\s].*)$")
        for line in brief_data.splitlines():
            match = regexp_entry.match(line)
            if not match:
                continue
            # find the source in verbose data
            vline = [i for i in verbose_data.splitlines() if i.strip().startswith(line)][0]
            efi_bin_source = vline[len(line):].strip()

            self.entries[match.group("bootnum")] = EFIBootLoader(
                boot_number=match.group("bootnum"),
                label=match.group("label"),
                active="*" in line,
                efi_bin_source=efi_bin_source,
            )
        if not self.entries:
            # it's not expected that no entry exists
            raise BootloaderError("EFI: Cannot detect EFI bootloaders.")

    def _parse_current_boot(self, data):
        # e.g.: BootCurrent: 0002
        for line in data.splitlines():
            if line.startswith("BootCurrent:"):
                self.current_boot = line.split(":")[1].strip()
                return
        raise BootloaderError("EFI: Cannot detect current boot number.")

    def _parse_next_boot(self, data):
        # e.g.:  BootCurrent: 0002
        for line in data.splitlines():
            if line.startswith("BootNext:"):
                self.next_boot = line.split(":")[1].strip()
                return
        logger.debug("EFI: the next boot is not set.")

    def _parse_boot_order(self, data):
        # e.g.:  BootOrder: 0001,0002,0000,0003
        for line in data.splitlines():
            if line.startswith("BootOrder:"):
                self.boot_order = tuple(line.split(":")[1].strip().split(","))
                return
        raise BootloaderError("EFI: Cannot detect current boot order.")


def canonical_path_to_efi_format(canonical_path):
    """Transform the canonical path to the EFI format.

    e.g. /boot/efi/EFI/redhat/shimx64.efi -> \\EFI\\redhat\\shimx64.efi
    (just single backslash; so the strin needs to be put into apostrophes
    when used for /usr/sbin/efibootmgr cmd)

    The path has to start with /boot/efi otherwise the path is invalid for EFI.

    Raise ValueError on invalid EFI path.
    """
    if not canonical_path.startswith(EFI_MOUNTPOINT):
        raise ValueError("Invalid path to the EFI binary: %s" % canonical_path)
    # len(EFI_MOUNTPOINT) == 10, but we want to keep the leading "/", so.. 9
    return canonical_path[9:].replace("/", "\\")


def _copy_grub_files():
    """Copy grub files from centos dir to the /boot/efi/EFI/redhat/ dir.

    The grub.cfg, grubenv, ... files are not present in the redhat directory
    after the conversion on centos system. These files are usually created
    during the OS installation by anaconda and have to be present in the
    redhat directory after the conversion.

    The copy from the centos directory should be ok. In case of the conversion
    from OL, the redhat directory is already used.

    Return False when any required file has not been copied or is missing.
    """
    if systeminfo.system_info.id != "centos":
        logger.debug("Skipping the copy of grub files - related only for centos.")
        return True

    # TODO(pstodulk): check behaviour for efibin from a different dir or with
    # a different name for the possibility of the different grub content...
    # E.g. if  the efibin is located in different directory, are these two files
    # valid???
    logger.info("Copy the GRUB2 configuration files to the new EFI directory.")
    src_efidir = CENTOS_EFIDIR_CANONICAL_PATH
    flag_ok = True
    required_files = ["grubenv", "grub.cfg"]
    all_files = required_files + ["user.cfg"]
    for filename in all_files:
        src_path = os.path.join(src_efidir, filename)
        dst_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
        if os.path.exists(dst_path):
            logger.info("The %s file already exists. Copying skipped." % dst_path)
            continue
        if not os.path.exists(src_path):
            if filename in required_files:
                # without the required files user should not reboot the system
                logger.error(
                    "Cannot find the original file required for the proper"
                    " configuration: %s" % src_path)
                flag_ok = False
            continue
        logger.info("Copying '%s' to '%s'" % (src_path, dst_path))
        try:
            shutil.copy2(src_path, dst_path)
        except IOError as err:
                # FIXME: same as fixme above
                logger.error("I/O error(%s): %s" % (err.errno, err.strerror))
                flag_ok = False
    return flag_ok


def _create_new_entry(efibootinfo):
    # This should work fine, unless people would like to use something "custom".
    label = "Red Hat Enterprise Linux %s" % str(systeminfo.system_info.version.major)
    logger.info("Create the '%s' EFI bootloader entry." % label)
    try:
        dev_number = _get_device_number(efibootinfo.efi_partition)
        blk_dev = get_grub_device()
    except BootloaderError:
        raise BootloaderError("Cannot get required information about the EFI partition.")
    logger.debug("Block device: %s" % str(blk_dev))
    logger.debug("ESP device number: %s" % str(dev_number))

    efi_path = None
    for filename in DEFAULT_INSTALLED_EFIBIN_FILENAMES:
        tmp_efi_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
        if os.path.exists(tmp_efi_path):
            efi_path = canonical_path_to_efi_format(tmp_efi_path)
            logger.debug("The new EFI binary: %s" % tmp_efi_path)
            logger.debug("The new EFI binary [efi format]: %s" % efi_path)
            break
    if not efi_path:
        BootloaderError("Cannot detect any RHEL EFI binary file.")

    cmd_fmt = "/usr/sbin/efibootmgr -c -d %s -p %s -l '%s' -L '%s'"
    cmd_params = (blk_dev, dev_number["minor"], efi_path, label)

    stdout, ecode = utils.run_subprocess(cmd_fmt % cmd_params, print_output=False)
    if ecode:
        logger.debug("efibootmgr output:\n-----\n%s\n-----" % stdout)
        raise BootloaderError("Cannot create the new EFI bootloader entry for RHEL.")

    # check that our entry really exists, if yes, it will be default for sure
    logger.info("Check the new EFI bootloader.")
    new_efibootinfo = EFIBootInfo()
    new_boot_entry = None
    for i in new_efibootinfo.entries.values():
        if i.label == label and efi_path in i.efi_bin_source:
            new_boot_entry = i
    if not new_boot_entry:
        raise BootloaderError("Cannot get the boot number of the new EFI bootloader entry.")


def _remove_current_boot_entry(efibootinfo_orig):
    """Remove the current (original) boot entry if ...

    if:
        - the referred EFI binary file doesn't exist anymore and originally
          was located in the default directory for the original OS
        - the referred EFI binary file is same as the current default one

    The conditions could be more complicated if algorithms in this module
    are changed. Additional checks are implemented that could prevent the
    current boot from the removal.

    The function is expected to be called after the new RHEL entry is created.
    but expects to get EFIBootInfo before the new bootloader entry is created.
    """
    efibootinfo_new = EFIBootInfo()
    # the following checks are just preventive. the warnings should not appear,
    # unless someone changes the code in future providing a bug
    orig_boot = efibootinfo_new.entries.get(efibootinfo_orig.current_boot, None)
    if not orig_boot:
        logger.warning(
            "The original default EFI bootloader entry %s has been removed already."
            % orig_boot.boot_number
        )
        return
    if orig_boot != efibootinfo_orig.entries[orig_boot.boot_number]:
        logger.warning(
            "The EFI bootloader entry %s has been modified. Skipping the removal."
            % orig_boot.boot_number
        )
        return
    if not orig_boot.is_referring_to_file():
        logger.warning(
            "The EFI bootloader entry %s is not referring to an EFI binary file."
            " Skipping the removal."
            % orig_boot.boot_number
        )
        return

    efibin_path = orig_boot.get_canonical_path()
    if not efibin_path:
        # this is rather a bug of this modules, as this should not happen
        logger.warning(
            "Skipping the removal of the original default boot '%s':"
            " Cannot get canonical path to the EFI binary file."
            % orig_boot.boot_number
        )
        return

    # the following checks could be hit
    efibin_path_new = efibootinfo_new.entries[efibootinfo_new.boot_order[0]].get_canonical_path()
    if os.path.exists(efibin_path) and efibin_path != efibin_path_new:
        logger.warning(
            "Skipping the removal of the original default boot '%s':"
            " The referred file still exists: %s"
            % (orig_boot.boot_number, efibin_path)
        )
        return
    logger.info("Remove the original EFI boot entry '%s'." % orig_boot.boot_number)
    _, ecode = utils.run_subprocess("/usr/sbin/efibootmgr -Bb %s" % orig_boot.boot_number, print_output=False)
    if ecode:
        # this is not a critical issue; the entry will be even removed
        # automatically if it is invalid (points to non-existing efibin)
        logger.warning("The removal of the original EFI bootloader entry has failed.")


def _replace_efi_boot_entry(efibootinfo):
    """Replace the current EFI bootloader entry with the RHEL one.

    The current EFI bootloader entry could be invalid or missleading. It's
    expected the new bootloader entry will refer to one of standard EFI binary
    files, provided by Red Hat, inside RHEL_EFIDIR_CANONICAL_PATH.
    The new EFI bootloader entry is always created / registered and set
    set as default.

    The current (original) EFI bootloader entry is removed under some conditions
    (see _remove_current_boot_entry() for more info).
    """
    _create_new_entry(efibootinfo)
    _remove_current_boot_entry(efibootinfo)


def _remove_efi_centos():
    """Remove the /boot/efi/EFI/centos directory when no efi files remains.

    The centos directory after the conversion contains usually just grubenv,
    grub.cfg, .. files only. Which we copy into the redhat directory. If no
    other efi files are present, we can remove this dir. However, if additional
    efi files are present, we should keep the directory for now, until we
    deal with it.
    """
    if systeminfo.system_info.id != "centos":
        # nothing to do
        return
    # TODO: remove the original centos directory if no efi bin is present
    logger.info(
        "The original /boot/efi/EFI/centos directory is kept."
        " Remove the directory manually after you check it's not needed"
        " anymore."
    )


def post_ponr_set_efi_configuration():
    """Configure GRUB after the conversion.

    Original setup points to \\EFI\\centos\\shimx64.efi but after
    the conversion it should point to \\EFI\\redhat\\shimx64.efi. As well some
    files like grubenv, grub.cfg, ...  are not migrated by default to the
    new directory as these are usually created just during installation of OS.

    The current implementation ignores possible multi-boot installations.
    It expects just one installed OS. IOW, only the CurrentBoot entry is handled
    correctly right now. Other possible boot entries have to be handled manually
    if needed.

    Nothing happens on BIOS.
    """
    if not is_efi():
        logger.info("The BIOS detected. Nothing to do.")
        return

    new_default_efibin = None
    for filename in DEFAULT_INSTALLED_EFIBIN_FILENAMES:
        efi_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
        if os.path.exists(efi_path):
            logger.info("The new expected EFI binary found: %s" % efi_path)
            new_default_efibin = efi_path
            break
        logger.debug("The %s EFI binary not found. Check the next..." % efi_path)
    if not new_default_efibin:
        _log_critical_error("Any of expected RHEL EFI binaries do not exist.")
    if not os.path.exists("/usr/sbin/efibootmgr"):
        _log_critical_error("The /usr/sbin/efibootmgr utility is not installed.")

    # related just for centos. checks inside
    if not _copy_grub_files():
        _log_critical_error("Some GRUB files have not been copied to /boot/efi/EFI/redhat")
    _remove_efi_centos()

    try:
        # load the bootloader configuration NOW - after the grub files are copied
        logger.info("Load the bootloader configuration.")
        efibootinfo = EFIBootInfo()
        logger.info("Replace the current EFI bootloader entry with the RHEL one.")
        _replace_efi_boot_entry(efibootinfo)
    except BootloaderError as e:
        # TODO(pstodulk): originally we discussed it will be better to not use
        # the critical log, for the possibility the additional post converstion
        # actions could exist. However, I cannot come up with a good solution
        # without putting additional logic into the main(). So as currently
        # this is the last action that could fail, I am just using this solution.
        _log_critical_error(e.message)
