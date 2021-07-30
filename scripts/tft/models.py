from enum import Enum
from typing import Dict, List

from envparse import env
from pydantic import BaseModel, SecretStr


class Fmf(BaseModel):
    url: str
    ref: str
    name: str


class Test(BaseModel):
    fmf: Fmf


class CPUArch(Enum):
    x86_64: str = "x86_64"


class Os(BaseModel):
    compose: str


class ArtifactType(Enum):
    fedora_copr_build: str = "fedora-copr-build"


class Artifact(BaseModel):
    id: str
    type: ArtifactType


class Environment(BaseModel):
    arch: CPUArch
    os: Os
    variables: Dict[str, SecretStr]
    artifacts: List[Artifact]


class TFTRequest(BaseModel):
    api_key: SecretStr = SecretStr(env.str("TFT_API_KEY"))
    test: Test
    environments: List[Environment]

    class Config:
        json_encoders = {
            SecretStr: lambda v: v.get_secret_value() if v else "",
        }
