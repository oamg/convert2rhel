# Integration tests

## Prepare testing environment

```bash
# install qemu/kvm utils
# TODO not validated as I did the installation on debian
sudo dnf -y install bridge-utils libvirt virt-install qemu-kvm python3-libvirt

# Create clean centos7 and centos8 qemu kvm VMs
# TODO describe how to do this
virsh list --all
# the domain (vms) names should match (used in the tests declaration)
# you have to have the following output
#  Id   Name                   State
# ---------------------------------------
#  -    c2r_centos7_template   shut off
#  -    c2r_centos8_template   shut off

# Copy your ssh key to each machine
ssh-copy-id root@{CENTOS7_VM_IP} # you'll be asked for a password
ssh-copy-id root@{CENTOS_8_VM_IP} # you'll be asked for a password

# install qemu agent on each of these machines
# go to Virtual Machine manager edit->preferences and enable
#   xml editing
# do on each VM
# In VM manger add the following to XML config of the machine
# somewhere in  <devices>:
#     <channel type="unix">
#       <source mode="bind" path="/var/lib/libvirt/qemu/f16x86_64.agent"/>
#       <target type="virtio" name="org.qemu.guest_agent.0"/>
#       <address type="virtio-serial" controller="0" bus="0" port="1"/>
#     </channel>
ssh root@{CENTOS{7 or 8}_VM_IP}
    # install qemu agent
dnf install yum install qemu-guest-agent
    # unblock needed modules
vim /etc/sysconfig/qemu-ga
    # comment BLACKLIST_RPC and save (:wa)
    # 
# ensure qemu agent is running
systemctl enable qemu-guest-agent
systemctl status qemu-guest-agent
# you should see that service is active(running)
# now shutdown the vm
shutdown now
# do not forget to do it for the second VM

# install ansible globally
sudo dnf install ansible

# cd into covnert2rhel repo and create int tests venv there
cd # where your repo lives
virtualenv --python $(which python3) .int_tests_venv3
. ./.int_tests_venv3/bin/activate

# install docker-compose
pip install docker-compose
# Install our fork of the tmt framework
pip install git+https://github.com/ZhukovGreen/tmt.git@poc/tmt-adoption-for-convert2rhel
# add auto-completions
eval "$(_TMT_COMPLETE=source_bash tmt)"

# This end of the installation
```

# Running integration tests

```bash
# show available plans and tests
tmt 
# Found 2 tests: /tests/integration/read-only-mnt-sys/mnt_ro and /tests/integration/read-only-mnt-sys/sys_ro.
# Found 4 plans: /plans/integration/read-only-mnt-sys/container_centos7_bad_mnt, /plans/integration/read-only-mnt-sys/container_centos7_bad_sys, /plans/integration/read-only-mnt-sys/container_centos8_bad_mnt and /plans/integration/read-only-mnt-sys/container_centos8_bad_sys.
# Found 0 stories.

# show tmt plans
tmt plans --show -vvv

# run integration test (after --name specify the plan name)
tmt run plans --name /plans/integration/read-only-mnt-sys/container_centos8_bad_mnt -vvvddd
# at the end of the test you should see something like this:
# ......truncated........
#        summary: 1 test passed
#        status: done
#        Write file '/var/tmp/tmt/run-531/plans/integration/read-only-mnt-sys/container_centos8_bad_mnt/report/step.yaml'.
#    finish
#        workdir: /var/tmp/tmt/run-531/plans/integration/read-only-mnt-sys/container_centos8_bad_mnt/finish
#        In the develop mode. Skipping stopping the container.
#        In the develop mode. Skipping removing the container 1163ba2a57d3afff0dc97e3615c21ba66e9a436bfa5ccf81841e38fd6e4ef5b3.Use:
#docker attach 1163ba2a57d3afff0dc97e3615c21ba66e9a436bfa5ccf81841e38fd6e4ef5b3
# to connect the machine.
#        summary: 0 tasks completed
#        status: done
#        Write file '/var/tmp/tmt/run-531/plans/integration/read-only-mnt-sys/container_centos8_bad_mnt/finish/step.yaml'.
#
#total: 1 test passed
```