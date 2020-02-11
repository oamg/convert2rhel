# [convert2rhel] System Tests

**System Tests** for convert2rhel consist of scenarios where the tool is used to convert one of the supported source systems, such as CentOS and OL, to RHEL. A script is provided to run all scenarios and notify the user of any problem.

## Requirements

The following software must be installed/present on your local machine before you can run the tests:

  - [Vagrant](http://vagrantup.com/)
  - [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html)

## Usage

Make sure the required software (listed above) is installed. Then run:

    $ ./run_system_tests.sh

## Scenarios Definitions

**System Tests** for convert2rhel are executed against CentOS and OL virtual machines (VMs) of many supported versions. To instantiate and setup the VMs [Vagrant](http://vagrantup.com/) is used with libvirt as a default provider. Each test scenario consists of a Vagrantfile which contains JSON data defining which Vagrant Box should be used and which resources the new VM will have available. After instantiation, an Ansible Playbook is used to setup a new VM. It is responsible to update and install necessary packages in such a way that convert2rhel can be executed succesfully. All Vagrantfiles and Ansible Playbooks are stored inside **"vmdefs"** folder.

To create a new test scenario, a new folder should be placed under **"vmdefs"**, containing at least a Vagrantfile pointing to a Vagrant Box and specifing how to set it up and to execute convert2rhel. It is recommended to extend one of the existing Ansible Playbooks to setup the new VM.

The following test scenarios are available, with more comming in the future:
- Run `convert2rhel --debug --disable-submgr  --disablerepo=*  --enablerepo=rhel -v Server -y` in the following Vagrant Boxes:
 - CentOS 5.11 (https://app.vagrantup.com/artmello/boxes/centos5)
 - CentOS 6 (latest minor version available at https://app.vagrantup.com/centos/boxes/6)
 - CentOS 7 (latest minor version available at https://app.vagrantup.com/centos/boxes/7)

## Vagrant Boxes

By default, tests are executed against Vagrant Boxes (using libvirt provider) available at [Vagrant Cloud](https://app.vagrantup.com/). Whenever some desired system is not available, it is possible to generate a new Vagrant Box using [Packer](http://www.packer.io/). This tool uses a group of Kickstart and JSON configuration files to define how the Box should be created. Inside the folder name **"packer"**, it is stored all necessary files to regenerate or customize boxes used by **system tests** that are not provided by an official channel.

