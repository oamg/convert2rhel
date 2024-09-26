import os
import shutil
import subprocess

import pytest

from test_helpers.common_functions import SystemInformationRelease


@pytest.fixture(autouse=True)
def workaround_missing_os_release_package(shell):
    # TODO(danmyway) remove when/if the issue gets fixed
    """
    Fixture to workaround issues with missing `*-linux-release`
    package, after incomplete rollback.
    """
    # run only after the test finishes
    yield

    os_to_pkg_mapping = {
        "centos-7": ["centos-release"],
        "centos-8": ["centos-linux-release"],
        "almalinux": ["almalinux-release"],
        "rocky": ["rocky-release"],
        "oracle": ["oraclelinux-release"],
        "stream": ["centos-stream-release"],
    }

    # Run only for non-destructive tests.
    # The envar is added by tmt and is defined in main.fmf for non-destructive tests.
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ:
        os_name = SystemInformationRelease.distribution
        os_ver = SystemInformationRelease.version.major
        if "centos" in os_name:
            os_key = f"{os_name}-{os_ver}"
        else:
            os_key = os_name

        system_release_pkgs = os_to_pkg_mapping.get(os_key)

        if os_key == "oracle":
            system_release_pkgs.append(f"oraclelinux-release-el{SystemInformationRelease.version.major}")

        for pkg in system_release_pkgs:
            installed = shell(f"rpm -q {pkg}").returncode
            if installed == 1:
                shell(f"yum install -y --releasever={os_ver} {pkg}")

        # Since we try to mitigate any damage caused by the incomplete rollback
        # try to update the system, in case anything got downgraded
        print("TESTS >>> Updating the system.")
        shell("yum update -y", silent=True)


@pytest.fixture(scope="session", autouse=True)
def workaround_remove_uek():
    """
    Fixture to remove the Unbreakable Enterprise Kernel package.
    The package might cause dependency issues.
    Reference issue https://issues.redhat.com/browse/RHELC-1544
    """
    if SystemInformationRelease.distribution == "oracle":
        subprocess.run(
            ["yum", "remove", "-y", "kernel-uek"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    yield


def workaround_grub_setup(shell):
    """
    Workaround.
    /usr/lib/kernel/install.d/99-grub-mkconfig.install sets DISABLE_BLS=true when the hypervisor is xen
    Due to all AWS images having xen type hypervisor, GRUB_ENABLE_BLSCFG is set to false as well
    as a consequence. We need GRUB_ENABLE_BLSCFG set to true to be able to boot into different kernel
    than the latest.
    """
    if SystemInformationRelease.version.major == 9:
        print("TESTS >>> Setting grub default to correct values.")
        shell(r"sed -i 's/^\s*GRUB_ENABLE_BLSCFG\s*=.*/GRUB_ENABLE_BLSCFG=true/g' /etc/default/grub")


@pytest.fixture(autouse=True)
def workaround_keep_centos_pointed_to_vault(shell):
    """
    Fixture.
    In some rare cases we (re)install the centos-release package.
    This overwrites the repofiles to its default state using mirrorlist instead of vault
    which won't work since the EOL.
    Make sure the repositories are pointed to the vault to keep the system usable.
    """
    if "C2R_TESTS_NONDESTRUCTIVE" in os.environ and "centos" in SystemInformationRelease.distribution:
        sed_repos_to_vault = r'sed -i -e "s|^\(mirrorlist=.*\)|#\1|" -e "s|^#baseurl=http://mirror\(.*\)|baseurl=http://vault\1|" /etc/yum.repos.d/CentOS-*'
        print("TESTS >>> Resetting the repos to vault")
        shell(sed_repos_to_vault, silent=True)


@pytest.fixture()
def workaround_hybrid_rocky_image(shell):
    """
    Fixture to detect a hybrid Rocky Linux cloud image.
    Removes symlink from /boot/grub2/grubenv -> ../efi/EFI/rocky/grubenv
    The symlink prevents grub to read the grubenv and boot to a different
    kernel than the last selected.
    """
    grubenv_file = "/boot/grub2/grubenv"
    is_efi = shell("efibootmgr", silent=True).returncode
    if "rocky" in SystemInformationRelease.distribution and is_efi not in (None, 0):
        if os.path.islink(grubenv_file):
            target_grubenv_file = os.path.realpath(grubenv_file)

            os.remove(grubenv_file)
            shutil.copy2(target_grubenv_file, grubenv_file)
