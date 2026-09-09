import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI()

DEPLOY_TOKEN = os.environ["DEPLOY_TOKEN"]

security = HTTPBearer()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/deploy")
async def deploy(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    env_file: Annotated[UploadFile, File()],
    compose_file: Annotated[UploadFile, File()],
    image_tag: Annotated[str, Form()],
):
    if credentials.credentials != DEPLOY_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorised")

    deploy_dir = Path(tempfile.mkdtemp(prefix="nene-deploy-"))

    env_path = deploy_dir / ".env"
    compose_path = deploy_dir / "compose.yml"

    compose_env = os.environ.copy()
    compose_env["IMAGE_TAG"] = image_tag

    try:
        with env_path.open("wb") as f:
            shutil.copyfileobj(env_file.file, f)

        with compose_path.open("wb") as f:
            shutil.copyfileobj(compose_file.file, f)

        compose = [
            "docker",
            "compose",
            "-f",
            str(compose_path),
            "--env-file",
            str(env_path),
        ]

        await run_migration(compose_prefix=compose, compose_env=compose_env)
        await deploy_docker(compose_prefix=compose, compose_env=compose_env)

    except Exception as e:
        print(e)
        raise e

    finally:
        shutil.rmtree(deploy_dir)

    return {"status": "deployed"}


async def run_migration(compose_prefix: list[str], compose_env: dict[str, str]):

    migration = subprocess.run(
        [
            *compose_prefix,
            "run",
            "--rm",
            "nene",
            "uv",
            "run",
            "alembic",
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=compose_env,
    )

    if migration.returncode != 0:
        detail = migration.stderr.strip() or migration.stdout.strip()
        raise HTTPException(
            status_code=500, detail=f"Failed during migration:\n{detail}"
        )


async def deploy_docker(compose_prefix: list[str], compose_env: dict[str, str]):
    # 2. Deploy only after migration succeeds
    deployment = subprocess.run(
        [
            *compose_prefix,
            "up",
            "-d",
            "--remove-orphans",
        ],
        capture_output=True,
        text=True,
        env=compose_env,
    )

    if deployment.returncode != 0:
        detail = deployment.stderr.strip() or deployment.stdout.strip()

        raise HTTPException(
            status_code=500,
            detail=f"Failed during deployment:\n{detail}",
        )
