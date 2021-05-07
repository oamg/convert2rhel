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

# set secrets for running integration tests
vim .env
```

# Creating integration tests

We use TMT testing framework as a meta testing platform which manages
integration tests lifecycle (https://tmt.readthedocs.io/en/stable/index.html).
It uses FMF format (https://fmf.readthedocs.io/en/stable/index.html) to declare
testing plans and tests.

Basic structure of the feature integration test is as follows:
```bash
# feature plan is stored as a directory in plans/integration dir
#     in our case this is - inhibit-if-oracle-system-uses-not-standard-kernel
$ tree plans
plans/
├── integration
│   └── inhibit-if-oracle-system-uses-not-standard-kernel
│       ├── main.fmf
│       ├── vm_oracle7.fmf
│       └── vm_oracle8.fmf
└── main.fmf
# primary (root) plan
$ cat plans/main.fmf
execute:
    how: tmt
discover:
    how: fmf
prepare:
    how: ansible
    playbook:
        - tests/ansible_collections/basic_setup.yml      
# root feature plan, it extends the root plan by adding filtering tag to mach only
# the given feature tests
$ cat plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/main.fmf 
 discover+:
     filter:
         - 'tag: inhibit-if-oracle-system-uses-not-standard-kernel'
# vm type specific plans. They are included subplans /good and /bad
$ cat plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/vm_oracle8.fmf 
discover+:
    filter+:
        - 'tag: oracle8'
provision:
    how: libvirt
    origin_vm_name: c2r_oracle8_template
    develop: true

/good:
    discover+:
        filter+:
            - 'tag: good_test'
    prepare+:
        playbook+:
            - tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/ansible/replace_oracle_kernel.yml
/bad:
    discover+:
        filter+:
            - 'tag: bad_test'
```
As the result we have the following set of 4 plans:
```bash
$ tmt plans show
/plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/vm_oracle7/bad
    discover 
         how fmf
      filter tag: inhibit-if-oracle-system-uses-not-standard-kernel
             tag: oracle7
             tag: bad_test
   provision 
         how libvirt
origin_vm_name c2r_oracle7_template
     develop yes
     prepare 
         how ansible
    playbook tests/ansible_collections/basic_setup.yml

/plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/vm_oracle7/good
    discover 
         how fmf
      filter tag: inhibit-if-oracle-system-uses-not-standard-kernel
             tag: oracle7
             tag: good_test
   provision 
         how libvirt
origin_vm_name c2r_oracle7_template
     develop yes
     prepare 
         how ansible
    playbook tests/ansible_collections/basic_setup.yml
             tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/ansible/replace_oracle_kernel.yml

/plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/vm_oracle8/bad
    discover 
         how fmf
      filter tag: inhibit-if-oracle-system-uses-not-standard-kernel
             tag: oracle8
             tag: bad_test
   provision 
         how libvirt
origin_vm_name c2r_oracle8_template
     develop yes
     prepare 
         how ansible
    playbook tests/ansible_collections/basic_setup.yml

/plans/integration/inhibit-if-oracle-system-uses-not-standard-kernel/vm_oracle8/good
    discover 
         how fmf
      filter tag: inhibit-if-oracle-system-uses-not-standard-kernel
             tag: oracle8
             tag: good_test
   provision 
         how libvirt
origin_vm_name c2r_oracle8_template
     develop yes
     prepare 
         how ansible
    playbook tests/ansible_collections/basic_setup.yml
             tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/ansible/replace_oracle_kernel.yml
```

Plans defines the testing environment, how to prepare it and which tests to run
within this environment (select tests based on tags).
Now let's look how to define tests. For this feature we need to have only two
tests (good and bad), which will be running in oracle 7 and oracle 8 environments.
Goal is to have the following fmf configs for tests:
```bash
$  tmt tests show
/tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/bad
     summary inhibit-if-oracle-system-uses-not-standard-kernel
        test pytest -svv --tb=no -m bad_tests
        path /tests/integration/inhibit-if-oracle-system-uses-not-
             standard-kernel
      manual no
    duration 5m
     enabled yes
      result respect
         tag oracle7
             oracle8
             inhibit-if-oracle-system-uses-not-standard-kernel
             bad_test

/tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/good
     summary inhibit-if-oracle-system-uses-not-standard-kernel
        test pytest -svv --tb=no -m good_tests
        path /tests/integration/inhibit-if-oracle-system-uses-not-
             standard-kernel
      manual no
    duration 5m
     enabled yes
      result respect
         tag oracle7
             oracle8
             inhibit-if-oracle-system-uses-not-standard-kernel
             good_test
```
The corresponding files context:
```bash
$ tree tests
tests
├── ansible_collections       # for storing general playbooks to reuse in different plans
│   ├── basic_setup.yml       # this one is use in the very root tmt plan
│   └── scripts       # place for storing scripts to call in ansible
└── integration
    ├── conftest.py       # place for pytest fixtures
    ├── inhibit-if-oracle-system-uses-not-standard-kernel     # place for tmt tests for the given feature
    │   ├── ansible       # feature related playbooks
    │   │   └── replace_oracle_kernel.yml
    │   ├── main.fmf
    │   └── test_oracle_bad_kernel.py       # definition of pytest tests 
    ├── main.fmf      # root tmt tests definition
    └── README.md
$  cat tests/integration/inhibit-if-oracle-system-uses-not-standard-kernel/main.fmf
summary: inhibit-if-oracle-system-uses-not-standard-kernel
tag+:
  - oracle7
  - oracle8
  - inhibit-if-oracle-system-uses-not-standard-kernel

/good:
  tag+:
    - good_test
  test: |
    pytest -svv --tb=no -m good_tests       # tmt has the test fmf file parent dir as a cwd

/bad:
  tag+:
    - bad_test
  test: |
    pytest -svv --tb=no -m bad_tests
```


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
```
