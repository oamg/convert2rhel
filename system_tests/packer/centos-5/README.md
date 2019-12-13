# Packer - CentOS 5 minimal LibVirt Vagrant Box

**Current CentOS Version Used**: 5.11

**Pre-built Vagrant Box**:

  - [`vagrant init artmello/centos5`](https://vagrantcloud.com/artmello/boxes/centos5)

This example build configuration installs and configures CentOS 5 x86_64
minimal, and then generates a Vagrant box file for LibVirt.

## Requirements

The following software must be installed/present on your local machine before
you can use Packer to build the Vagrant box file:

  - [Packer](http://www.packer.io/)
  - [Vagrant](http://vagrantup.com/)

## Usage

Make sure the required software (listed above) is installed, then cd to the
directory containing this README.md file, and run:

    $ packer build -var 'version=0.1.0' centos5.json

After a few minutes, Packer should tell you the box was generated successfully

## Try the Box

You may want to experiment with the created Vagrant Box. To run and connect to
the box, you need to add this new file to your local library. To do this just
execute:

    $ vagrant box add libvirt-centos5.box --name <BOX_NAME>

From now on every time you use <BOX_NAME> in a Vagrantfile it will use the box
from your local library. You can also list all boxes or remove one using:

    $ vagrant box list $ vagrant box remove <BOX_NAME>

You can create a new Vagrantfile by using:

    $ vagrant init <BOX_NAME>

This will bring up a basic Vagrantfile using <BOX_NAME>. However in case of
CentOS 5, there's an NFS sharing problem, which can be circumvented by adding
the following line to the Vagrantfile:

    config.vm.synced_folder ".", "/vagrant", disabled: true

To start and ssh to the Vagrant Box, run the following in the folder with the
Vagrantfile:

    $ vagrant up
    $ vagrant ssh

To stop running the Vagrant Box, run:

    $ vagrant destroy

## Author Information

This is mostly based on [Jeff Geerling](https://www.jeffgeerling.com/) works,
as presented here [Packer Example - CentOS 7](https://github.com/geerlingguy/packer-centos-7).
