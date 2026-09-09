import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
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
    env_file: Annotated[UploadFile, File()] = None,
    compose_file: Annotated[UploadFile, File()] = None,
):
    if credentials.credentials != DEPLOY_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorised")

    deploy_dir = Path(tempfile.mkdtemp(prefix="nene-deploy-"))

    env_path = deploy_dir / ".env"
    compose_path = deploy_dir / "compose.yml"

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

        await run_migration(compose)
        await deploy(compose)

    except Exception as e:
        print(e)

    finally:
        shutil.rmtree(deploy_dir)

    return {"status": "deployed"}


async def run_migration(compose_prefix: list[str]):

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
    )

    if migration.returncode != 0:
        print("Migration failed")
        print(migration.stdout)
        print(migration.stderr)

        raise HTTPException(status_code=500, detail="Database migration failed")


async def deploy(compose_prefix: list[str]):
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
    )

    if deployment.returncode != 0:
        print("Deployment failed:")
        print(deployment.stdout)
        print(deployment.stderr)

        raise HTTPException(
            status_code=500,
            detail="Docker deployment failed",
        )
