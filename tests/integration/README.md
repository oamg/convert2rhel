# Integration tests

## Prepare testing environment (tested on Fedora 33)

## Step 1 - prepare libvirt provisioning environment

Final goal of this task is to have 4 VMs enabled for qemu communication and
ssh there with your key
```bash
virsh list --all
# the domain (vms) names should match (used in the tests declaration)
# you have to have the following output
#  Id   Name                   State
# ---------------------------------------
#  -    c2r_centos7_template   shut off
#  -    c2r_centos8_template   shut off
#  -    c2r_oracle7_template   shut off
#  -    c2r_oracle8_template   shut off

# Each VM should have working qemu-guest-agent daemon
virsh qemu-agent-command --domain c2r_centos8_template '{"execute":"guest-ping"}'
# {"return":{}}

# Possibility to ssh to each VM with your key (no password)
ssh root@{VM_IP_ADDR}
```

1. Install necessary dependencies

```bash
# install deps
sudo dnf install -y \
  make \
  python3-virtualenv \
  podman \
  podman-docker \
  ansible \
  vagrant \
  virt-install \
  virt-manager \
  virt-viewer \
  qemu-kvm \
  libvirt-devel \
  libvirt-daemon-config-network \
  libvirt-daemon-kvm \
  libguestfs-tools

# add libvirt collection
ansible-galaxy collection install community.libvirt

# add yourself to libvirt group, so might work with libvirt without sudo
sudo usermod --append --groups libvirt $(whoami)

# switch libvirt uri to a system to enable NAT support for networking
echo 'uri_default = "qemu:///system"' >> ~/.config/libvirt/libvirt.conf

# [OPTIONAL] Use custom image storage location (if you have limited space in /var/lib/libvirt/images)
virsh pool-edit --pool default
# adjust <path> to a new location could (could be any existing dir)
#  <target>
#    <path>/any/existing/dir</path>
# say to qemu to use your user for qemu processes
echo -e "user = \"$(whoami)\"\ngroup = \"$(whoami)\"" | sudo tee -a /etc/libvirt/qemu.conf

# apply changes
sudo systemctl restart libvirtd
```

2. Create and setup VMs
```bash
# cd to the c2r-vagrant repo dir, e.g.
cd ~/Documents/c2r-vagrant

# Build vagrant VM
SYSTEM=centos8 SYSTEM_SESSION=1 vagrant up

# [OPTIONAL] generate your ssh key if you still don't have one (ls -al ~/.ssh/*.pub)
# follow instructions in https://docs.gitlab.com/ee/ssh/#generate-an-ssh-key-pair

# copy you ssh key to the VM (you'll be asking to enter the password (`vagrant`)
ssh-copy-id root@$(virsh domifaddr --domain c2r-vagrant_default | gawk 'match($0, /(192.+)\/.+/, ary) {print ary[1]}')

# ssh to the vagrant VM
ssh root@$(virsh domifaddr --domain c2r-vagrant_default | gawk 'match($0, /(192.+)\/.+/, ary) {print ary[1]}')
    # update packages
    yum update -y

    # Disable blacklisted rpc in qemu config
    sed -i "s/BLACKLIST_RPC/\# BLACKLIST_RPC/" /etc/sysconfig/qemu-ga

    # Switch selinux into permissive mode
    sed -i "s/SELINUX=enforcing/SELINUX=permissive/" /etc/selinux/config

    # enable qemu-ga
    systemctl enable qemu-guest-agent

    # install python pip and rsync
    yum install -y python3 rsync
    curl https://bootstrap.pypa.io/pip/get-pip.py | python3

    # Remove installed version of convert2rhel
    yum remove convert2rhel -y

    # exit the VM Ctrl+D

# shutdown the vagrant VM
virsh shutdown c2r-vagrant_default

# clone the VM and give it corresponding name (--name)
# SYSTEM=centos8 -> c2r_centos8_template
# SYSTEM=centos7 -> c2r_centos7_template
# SYSTEM=ol8 -> c2r_oracle8_template
# SYSTEM=ol7 -> c2r_oracle7_template
virt-clone --original c2r-vagrant_default --name c2r_centos8_template --auto-clone --check disk_size=off

# remove the origin vagrant VM
virsh undefine --domain c2r-vagrant_default

# remove stale volume
vagrant destroy -f

# Now do the same for SYSTEM={centos7,ol8,ol7}
```

3. Perform post setup for each VM

3.1. In Virtual Machine Manager go to Edit -> Preferences and set enable
xml editing

3.2. For each VM in VM Manager click Open and:
- set network source (NIC device) to default (Virtual network 'default': NAT)
- add qemu-ga channel, by clicking Add Hardware button:
select Channel, use XML to declar the device and add:
```xml
<channel type="unix">
  <target type="virtio" name="org.qemu.guest_agent.0"/>
  <address type="virtio-serial" controller="0" bus="0" port="1"/>
</channel>
```
click Finish, click Apply

## Step 3 - Setup TMT-Pytest framework
Install local development environment:
```bash
# cd to the cloned convert2rhel github repository dir, e.g.
cd ~/Documents/convert2rhel/

# install venv, python deps and build images
rm .images .install
make install

# configure the integration tests by setting environment variables in .env
vim .env
```

# Creating integration tests

We use TMT testing framework as a meta testing platform which manages
integration tests lifecycle (https://tmt.readthedocs.io/en/stable/index.html).

It uses FMF format (https://fmf.readthedocs.io/en/stable/index.html) to declare
testing plans and tests.

Plans define the testing environment, how to prepare it and which tests to run
within this environment (filtering tests based on tags).

Tests themselves are written using python pytest framework.

Examples of plans and tests can be found in `plans/integration` and
`tests/integration` directories.


# Running integration tests

```bash
# activate venv that was setup through `make install`
. .venv3/bin/activate
# show available plans and tests
tmt
# Found 2 tests: /tests/integration/read-only-mnt-sys/mnt_ro and /tests/integration/read-only-mnt-sys/sys_ro.
# Found 4 plans: /plans/integration/read-only-mnt-sys/container_centos7_bad_mnt, /plans/integration/read-only-mnt-sys/container_centos7_bad_sys, /plans/integration/read-only-mnt-sys/container_centos8_bad_mnt and /plans/integration/read-only-mnt-sys/container_centos8_bad_sys.
# Found 0 stories.

# show tmt plans and tests
tmt plans show -vvv
tmt tests show -vvv

# list all plans
tmt plans ls

# run all integration tests
tmt run

# run one integration test (after --name specify the plan name)
tmt run plans --name /plans/integration/read-only-mnt-sys/container_centos8_bad_mnt
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

# run one integration test with plans matching the regex (in example all goo tests)
tmt run plans --name /plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/.+/good -vvvddd
```
