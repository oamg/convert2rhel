from pathlib import Path

from envparse import env


REPO_ROOT = Path(__file__).parents[2]
env.read_envfile(REPO_ROOT / ".env")
