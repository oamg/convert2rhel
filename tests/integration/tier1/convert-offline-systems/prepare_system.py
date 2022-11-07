from conftest import SATELLITE_URL, SATELLITE_PKG_URL, SATELLITE_PKG_DST
import re
import socket


# Replace urls in rhsm.conf file to the satellite server
def replace_urls_rhsm():
    with open("/etc/rhsm/rhsm.conf", "r+") as f:
        file = f.read()
        # Replacing the urls
        file = re.sub("hostname = .*", "hostname = {}".format(SATELLITE_URL), file)
        file = re.sub("baseurl = .*", "baseurl = https://{}/pulp/repos".format(SATELLITE_URL), file)

        # Setting the position to the top of the page to insert data
        f.seek(0)
        f.write(file)
        f.truncate()


# Configure and limit connection to the satellite server only
def configure_connection():
    satellite_ip = socket.gethostbyname(SATELLITE_URL)

    with open("/etc/dnsmasq.conf", "a") as f:
        # Satellite url
        f.write("address=/{}/{}\n".format(SATELLITE_URL, satellite_ip))

        # Everything else is resolved to localhost
        f.write("address=/#/127.0.0.1")

    with open("/etc/resolv.conf", "w") as f:
        f.write("nameserver 127.0.0.1")


def test_prepare_system(shell):
    assert shell("yum install dnsmasq wget -y").returncode == 0

    # Install katello package
    assert shell("wget --no-check-certificate --output-document {} {}".format(SATELLITE_PKG_DST, SATELLITE_PKG_URL)).returncode == 0
    assert shell("rpm -i {}".format(SATELLITE_PKG_DST)).returncode == 0

    replace_urls_rhsm()

    configure_connection()

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0

    shell("rm -rf /etc/yum.repos.d/*")
