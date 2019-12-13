#!/bin/bash -eux

# Remove MACAddress ref from network config
sed -i '/HWADDR/d' /etc/sysconfig/network-scripts/ifcfg-eth0

# SSH Daemon config
sed -i '/UseDNS/d' /etc/ssh/sshd_config
sed -i '/GSSAPIAuthentication/d' /etc/ssh/sshd_config
echo 'UseDNS no' >> /etc/ssh/sshd_config
echo 'GSSAPIAuthentication no' >> /etc/ssh/sshd_config

# Vagrant SSH config
mkdir -m 0700 /home/vagrant/.ssh
echo "ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key" > /home/vagrant/.ssh/authorized_keys
chown -R vagrant:vagrant /home/vagrant/.ssh
chmod -R 0600 /home/vagrant/.ssh/*
