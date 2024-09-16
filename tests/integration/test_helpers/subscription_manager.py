from test_helpers.common_functions import SystemInformationRelease
from test_helpers.shell import live_shell
from test_helpers.vars import SYSTEM_RELEASE_ENV, TEST_VARS


class SubscriptionManager:
    def __init__(self):
        self.shell = live_shell()

    def add_keys_and_certificates(self):
        """
        Add the SSL certificate for accessing the CDN and the redhat RPM GPG key.
        """
        self.shell(
            "curl --create-dirs -ko /etc/rhsm/ca/redhat-uep.pem https://cdn-public.redhat.com/content/public/repofiles/redhat-uep.pem"
        )
        self.shell(
            "curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://security.access.redhat.com/data/fd431d51.txt"
        )

    def add_client_tools_repo(self):
        """
        Add the client tools repository to install subscription manager from.
        """
        version = "7-server" if SystemInformationRelease.version.major == 7 else SystemInformationRelease.version.major
        repo_url = f"https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-{version}.repo"

        self.shell(f"yum-config-manager --add-repo {repo_url}")

        # On CentOS 8.5 we need to replace the $releasever in the url to 8.5,
        # otherwise the dnf will complain with dependency issues.
        if "centos-8" in SYSTEM_RELEASE_ENV:
            self.shell(r"sed -i 's#\$releasever#8.5#' /etc/yum.repos.d/client-tools-for-rhel-8.repo")

    def install_package(self, package_name="subscription-manager"):
        """
        Install a package.
        :param package_name: The package to be installed. Default is subscription-manager.
        :type package_name: str
        """
        command = f"yum install -y {package_name}"
        # rhn-client-tools package obsoletes subscription-manager on Oracle Linux
        # set the obsoletes option to 0 to be able to install the package
        if SystemInformationRelease.distribution == "oracle":
            command += " --setopt=obsoletes=0"

        return self.shell(command)

    def remove_package(self, package_name="subscription-manager*"):
        """
        Removes a package.
        :param package_name: The package to be installed. Default is subscription-manager*.
        :type package_name: str
        """
        command = f"yum remove -y {package_name}"
        return self.shell(command)

    def remove_client_tools_repo(self):
        """
        Remove the client tools repository file.
        """
        command = "rm -f /etc/yum.repos.d/client-tools-for-rhel*.repo"

        return self.shell(command)

    def remove_keys_and_certificates(self):
        """
        Remove the SSL certificate for accessing the CDN and the redhat RPM GPG key.
        """
        self.shell("rm -f /etc/rhsm/ca/redhat-uep.pem")
        self.shell("rm -f /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release")

    def unregister(self):
        """
        Remove potential leftover subscription, unregister the system.
        """
        # Remove potential leftover subscription
        self.shell("subscription-manager remove --all")
        # Remove potential leftover registration
        command = "subscription-manager unregister"

        return self.shell(command)

    def set_up_requirements(self, use_staging_cdn=False):
        """
        Usual full preparation workflow.
        Calls, where applicable:
            self.remove_package(package_name="rhn-client-tools") # only on Oracle Linux
            self.add_keys_and_certificates()
            self.add_client_tools_repo()
            self.install_package()
            self.set_up_to_stagecdn() # only when use_staging_cdn is True
        """
        if SystemInformationRelease.distribution == "oracle":
            self.remove_package(package_name="rhn-client-tools")
        self.add_keys_and_certificates()
        self.add_client_tools_repo()
        self.install_package()
        if use_staging_cdn:
            self.set_up_to_stagecdn()

    def set_up_to_stagecdn(self):
        # Point the server hostname to the staging environment,
        # so we don't need to pass it to convert2rhel explicitly
        # RHSM baseurl gets pointed to a stage cdn
        self.shell(
            "subscription-manager config --rhsm.baseurl=https://{0} --server.hostname={1}".format(
                TEST_VARS["RHSM_STAGECDN"], TEST_VARS["RHSM_SERVER_URL"]
            ),
            silent=True,
        )

    def clean_up(self):
        """
        Usual full teardown workflow.
        Calls where applicable:
            self.unregister()
            self.remove_package()
            self.remove_client_tools_repo()
            self.remove_keys_and_certificates()
        """
        self.unregister()
        self.remove_package()
        self.remove_client_tools_repo()
        self.remove_keys_and_certificates()
