import os

from dotenv import dotenv_values


TEST_VARS = dotenv_values("/var/tmp/.env")
SAT_REG_FILE = dotenv_values("/var/tmp/.env_sat_reg")
SYSTEM_RELEASE_ENV = os.environ["SYSTEM_RELEASE_ENV"]
