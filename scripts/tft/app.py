import asyncio
import contextlib
import json
import pprint
import re
import sys

from asyncio import FIRST_EXCEPTION
from typing import AsyncContextManager, List, Tuple

import aiohttp
import git
import tmt
import yarl

from envparse import env
from giturlparse import parse as parse_git_url
from loguru import logger

from scripts.tft.models import Artifact, ArtifactType, CPUArch, Environment, Fmf, Os, Test, TFTRequest


assert sys.version_info > (3, 7), "Script can't be run with lower version of python"


# Mapping of tmt plans origin_vm_name provisioner definition to tft composes
VM2COMPOSES = {
    "c2r_centos7_template": "CentOS-7",
    "c2r_centos8_template": "CentOS-8",
    "c2r_oracle7_template": "Oracle-Linux-7.9",
    "c2r_oracle8_template": "Oracle-Linux-8.4",
}

VM2COPR_CHROOT = {
    "c2r_centos7_template": "epel-7-x86_64",
    "c2r_centos8_template": "epel-8-x86_64",
    "c2r_oracle7_template": "epel-7-x86_64",
    "c2r_oracle8_template": "epel-8-x86_64",
}

# interval at which the utility checks states of submitted jobs
WATCH_TEST_INTERVAL = 10
WATCH_COPR_BUILD_STATE_INTERVAL = 3

# tft api specific constants
API_URL: yarl.URL = yarl.URL(env.str("TFT_SERVICE_URL")) / f"v{env.str('TFT_API_VERSION')}"
API_REQUEST_URL: yarl.URL = API_URL / "requests"


def get_compose_from_provision_data(data: List[dict]) -> str:
    """Get compose name from the provisioning metadata of the libvirt provisoner.

    For local development a libvirt provisioner is used, however, TFT
    is replacing the provisioner with its own type, requiring to specify the
    compose type (OS name). This function computes the compose name from
    local metadata.
    """

    vm_name = get_vm_name(data)
    try:
        return VM2COMPOSES[vm_name]
    except KeyError:
        logger.critical(f"VM name {vm_name} is not registered in VM2COMPOSES variable.")
        raise


def get_vm_name(data: List[dict]) -> str:
    """Get Vm template name from the provisioning fmf metadata."""
    assert len(data) == 1, "Expecting only one dict with provisioning data."
    provision_data = data[0]
    assert provision_data["how"] == "libvirt", "Expecting here only libvirt provisioner."
    return provision_data["origin_vm_name"]


async def run_in_shell(cmd: str) -> Tuple[str, str]:
    """Simple async interface to subprocess shell."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode


async def succeeded_copr_build(
    copr_id: str,
    interval: int = WATCH_COPR_BUILD_STATE_INTERVAL,
) -> None:
    """Wait for copr build id to be built."""
    state, err, _ = await run_in_shell(f"copr-cli status {copr_id}")
    while state != "succeeded":
        if err:
            raise ValueError(err)
        logger.debug(f"Copr job {copr_id} state is {state}. Waiting {interval}s...")
        await asyncio.sleep(interval)
        state, err, _ = await run_in_shell(f"copr-cli status {copr_id}")
    logger.info(f"Copr job {copr_id} was finished successfully")


async def validate_copr_ids(*copr_ids: str) -> None:
    """Ensure the given copr build ids successfully built."""
    logger.info("Copr ids validation started started")

    async def check_build_state(copr_id):
        state, err, _ = await run_in_shell(f"copr-cli status {copr_id}")
        if state != "succeeded":
            raise ValueError(f"Job id {copr_id} is not succeeded. Can't use this rpm build.")
        if err:
            raise ValueError(err)

    done, pending = await asyncio.wait(
        [asyncio.create_task(check_build_state(copr_id)) for copr_id in copr_ids], return_when=FIRST_EXCEPTION
    )

    if pending:
        raise ValueError(
            f"Some of job ids {copr_ids} was not successfully built in copr. "
            f"Try to rebuild it (remove --copr-build-id options in cli command."
        )
    logger.info("Copr ids validation PASSED")


async def tft_health_check(session: aiohttp.ClientSession) -> None:
    """Check health of tft service.

    - Test that our composese mapping corresponding to existing composes
    """
    logger.info("TFT api health check started")
    logger.debug("Verifying available composes...")
    async with session.get(url=API_URL / "composes") as composes:
        composes = await composes.json()
        # TODO https://gitlab.com/testing-farm/general/-/issues/32
        # assert set(compose["name"] for compose in composes["composes"]).issuperset(set(VM2COMPOSES.values())), (
        #     f"Unknown composes specified in VM2COMPOSES. "
        #     f"Check for available composes at {self._api_url / 'composes'}."
        # )
    logger.info("TFT api health check PASSED")


async def repo_health_check(repo: git.Repo, remote: str) -> None:
    """Check the health of the repo.

    - Check if changes are committed
    - Check if all commits pushed to the remote (tft takes remote data)
    """
    logger.info("Repo health check started")
    logger.debug("Verifying repo not commited changes...")
    if repo.index.diff(None) or repo.index.diff("HEAD"):
        logger.warning(f"Some files contains not commited changes.")

    logger.debug("Verifying repo synced with the remote...")
    repo.remote(remote).fetch()
    try:
        # Check if there is at least one commit ahead in local branch
        next(
            repo.iter_commits(
                f"{remote}/{repo.active_branch.name}.." f"{repo.active_branch.name}",
            )
        )
    except StopIteration:
        # this means local and remote are in sync (no commits ahead)
        pass
    else:
        raise git.GitError(
            f"Local branch {repr(repo.active_branch.name)} is ahead of the remote. Changes needs to be pushed."
        )
    logger.info("Repo state check PASSED")


async def create_copr_builds():
    """Build rpms in copr using `make copr-build` command."""
    logger.info("Submitting job to copr...")
    stdout, stderr, rc = await run_in_shell("make copr-build")
    if rc:
        raise RuntimeError(f"`make copr-build` exited with {rc}. STDERR:\n{stderr}")
    build_urls = "\n".join(re.findall(r"Build was added to convert2rhel:\n  (.+)\n", stdout))
    build_ids = re.findall(r"Created builds: (.+)", stdout)
    logger.info(f"Builds are submitted to the copr under:\n{build_urls}\n" "Waiting the process to finish.")
    await asyncio.gather(*[asyncio.create_task(succeeded_copr_build(build_id)) for build_id in build_ids])
    return build_ids


async def submit_plan_to_tft(
    session: aiohttp.ClientSession,
    plan: tmt.Plan,
    repo_url: str,
    commit_hexsha: str,
    build_id: str,
    compose: str,
    chroot: str,
    arch: str,
    artifact_type: str,
) -> str:
    """Submit tft requiest for a given tmt plan."""
    api_payload = TFTRequest(
        test=Test(
            fmf=Fmf(
                url=repo_url,
                ref=commit_hexsha,
                name=plan.name,
            )
        ),
        environments=[
            Environment(
                arch=arch,
                os=Os(compose=compose),
                variables=plan.environment,
                artifacts=[
                    Artifact(id=f"{build_id}:{chroot}", type=artifact_type),
                ],
            )
        ],
    )
    logger.debug(f"Api called with:\n{pprint.pformat(api_payload.dict())}")
    async with session.post(
        url=API_REQUEST_URL,
        json=json.loads(api_payload.json()),
    ) as resp:
        logger.info(f"Plan {plan.name} submitted to TFT")
        if resp.status == 200:
            data = await resp.json()
        else:
            logger.warning(f"Plan {plan} failed to be submitted. Response status is: {resp.status}")
            logger.debug(repr(resp))
            raise aiohttp.ClientResponseError(
                code=resp.status,
                message=f"{resp.content}",
                request_info=resp.request_info,
                history=(resp,),
            )
        return data["id"]


async def watch_request_id(
    session: aiohttp.ClientSession,
    test_id: str,
    plan_name: str,
):
    """Watch for existing tft request id status.

    Return or raise on finishing the processing of the request by tft.
    """
    while True:
        async with session.get(API_REQUEST_URL / test_id) as resp:
            if resp.status == 200:
                data = await resp.json()
            else:
                logger.debug(resp)
                raise aiohttp.ClientError(f"Plan {plan_name} failed to fetch state. Response status is: {resp.status}")
            logger.debug(f"{plan_name} \t {test_id} \t {data['state']}")
            if data["state"] == "complete":
                logger.info(f"Plan {plan_name} successfully completed.")
                logger.debug(
                    f"Results available at:\n"
                    f"http://artifacts.osci.redhat.com/{test_id}/\n"
                    f"http://artifacts.osci.redhat.com/{test_id}/pipeline.log\n"
                )
                return
            if data["state"] == "error":
                raise aiohttp.ClientError(
                    f"Plan finished with error. Error details:"
                    f"{resp}.\n"
                    f"http://artifacts.osci.redhat.com/{test_id}/\n"
                    f"http://artifacts.osci.redhat.com/{test_id}/pipeline.log\n"
                )
        await asyncio.sleep(WATCH_TEST_INTERVAL)


@contextlib.asynccontextmanager
async def tft_runner(
    plans: List[str],
    remote: str = "origin",
    copr_build_ids: Tuple[str, ...] = (),
) -> AsyncContextManager[None]:
    """Async context manager to intereact with tft.

    Has 3 phases:
    - health check to verify state of the repo, tft service etc.
    - copr build to build rpms in copr
    - submit jobs to testing farm

    report errors if occured and usufull links.

    Automatically do a teardown at the end of execution.

    Example:
    >>> async with tft_runner(
    >>>     plans=[plan.strip() for plan in plans],
    >>>     remote=remote_name.strip(),
    >>>     copr_build_ids=copr_build_id,
    >>> ):
    >>>     pass

    """

    # initialization
    session = aiohttp.ClientSession()
    requests: List[asyncio.Task] = []
    repo: git.Repo = git.Repo()
    repo_url: str = parse_git_url(next(repo.remote(remote).urls)).url2https
    commit_hexsha: str = repo.commit().hexsha
    results = []

    try:
        # performing health checks
        logger.info("Health check phase started.")
        await tft_health_check(session)
        await repo_health_check(repo, remote)
        if copr_build_ids:
            await validate_copr_ids(*copr_build_ids)
        logger.info("Health check phase finished.")

        # TODO make copr builds more generic, now it is bound to
        #  Tuple[epel7_build, epel8_build]
        # creating copr builds
        if not copr_build_ids:
            logger.info("Copr build phase started.")
            epel7, epel8 = await create_copr_builds()
            logger.info("Copr build phase finished.")
        else:
            epel7, epel8 = copr_build_ids

        # submit tmt plans to be executed on tft and track their status
        logger.info("Submitting plans to tft started.")
        tmt_plans = tmt.Tree(".").plans(names=plans)
        assert tmt_plans, f"No plans found under {plans}. Consult `tmt plans ls`."
        for plan in tmt_plans:
            template_vm_name = get_vm_name(plan.provision.data)
            build_id = epel7 if VM2COPR_CHROOT[template_vm_name] == "epel-7-x86_64" else epel8
            chroot = VM2COPR_CHROOT[template_vm_name]
            try:
                plan_request_id = await submit_plan_to_tft(
                    session=session,
                    plan=plan,
                    repo_url=repo_url,
                    commit_hexsha=commit_hexsha,
                    build_id=build_id,
                    chroot=chroot,
                    arch=CPUArch.x86_64,
                    artifact_type=ArtifactType.fedora_copr_build,
                    compose=get_compose_from_provision_data(plan.provision.data),
                )
            except aiohttp.ClientResponseError as ex:
                logger.warning(f"tmt plan {plan.name} can't be submitted to tft.")
                logger.debug(ex)
            else:
                requests.append(
                    asyncio.create_task(
                        watch_request_id(
                            session=session,
                            test_id=plan_request_id,
                            plan_name=plan.name,
                        )
                    )
                )
        results = await asyncio.gather(
            *requests,
            return_exceptions=True,
        )

        logger.info("Submitting plans to tft finished.")
        yield results
    finally:
        logger.debug("Doing a teardown...")
        await session.close()

        # report exceptions if present
        exc = None
        for exc in filter(lambda res: isinstance(res, Exception), results):
            logger.critical(str(exc))
        if exc:
            raise exc
        logger.debug("Teardown completed")
        await asyncio.sleep(1)
