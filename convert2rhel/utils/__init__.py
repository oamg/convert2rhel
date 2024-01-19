# A string we're using to replace sensitive information (like an RHSM password) in logs, terminal output, etc.
import os


OBFUSCATION_STRING = "*" * 5


# Absolute path of a directory holding data for this tool
DATA_DIR = "/usr/share/convert2rhel/"
# Directory for temporary data to be stored during runtime
TMP_DIR = "/var/lib/convert2rhel/"
BACKUP_DIR = os.path.join(TMP_DIR, "backup")
