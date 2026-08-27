import os
import hmac
import hashlib
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from src.logger import setup_m5_logger
from src.indexer.progressive_indexer import progressive_indexer

logger = setup_m5_logger("m5.webhook")
webhook_router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

class WebhookSyncResponse(BaseModel):
    status: str
    event: str
    repository: str
    commits_processed: int
    message: str

def verify_github_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Verifies HMAC SHA-256 signature from GitHub."""
    if not WEBHOOK_SECRET:
        return True # Secret optional in development
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    
    expected_sig = signature_header.split("sha256=")[1]
    computed_sig = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, computed_sig)

@webhook_router.post("/github", status_code=status.HTTP_202_ACCEPTED, response_model=WebhookSyncResponse)
async def github_webhook_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default="push"),
    x_hub_signature_256: str | None = Header(default=None)
):
    payload_bytes = await request.body()

    # 1. Verify Webhook Signature
    if not verify_github_signature(payload_bytes, x_hub_signature_256):
        logger.error("GitHub Webhook rejected: Invalid HMAC SHA-256 signature")
        raise HTTPException(status_code=403, detail="Invalid HMAC webhook signature.")

    # 2. Ignore non-push events (e.g. ping, star)
    if x_github_event != "push":
        logger.info(f"Received GitHub webhook event '{x_github_event}' (ignored)")
        return WebhookSyncResponse(
            status="ignored",
            event=x_github_event,
            repository="unknown",
            commits_processed=0,
            message=f"Event '{x_github_event}' does not require codebase delta re-indexing."
        )

    payload = await request.json()
    repo_data = payload.get("repository", {})
    repo_name = repo_data.get("name", "default_repo")
    org_name = repo_data.get("owner", {}).get("name") or repo_data.get("owner", {}).get("login") or "default_org"

    # 3. Extract Added, Modified, and Removed Files from commits
    added_files: List[str] = []
    modified_files: List[str] = []
    removed_files: List[str] = []

    for commit in payload.get("commits", []):
        added_files.extend(commit.get("added", []))
        modified_files.extend(commit.get("modified", []))
        removed_files.extend(commit.get("removed", []))

    added_clean = list(set(added_files))
    modified_clean = list(set(modified_files))
    removed_clean = list(set(removed_files))

    logger.info(
        f"GitHub Push Webhook received for '{org_name}/{repo_name}': "
        f"{len(added_clean)} added, {len(modified_clean)} modified, {len(removed_clean)} removed files. Queueing delta sync..."
    )

    # 4. Offload Delta Synchronization to Background Task
    background_tasks.add_task(
        progressive_indexer.process_git_delta,
        added=added_clean,
        modified=modified_clean,
        removed=removed_clean,
        workspace_root=".",
        org_id=org_name,
        dept_id="engineering",
        repo_id=repo_name
    )

    return WebhookSyncResponse(
        status="accepted",
        event=x_github_event,
        repository=f"{org_name}/{repo_name}",
        commits_processed=len(payload.get("commits", [])),
        message=f"Queued delta sync for {len(added_clean)} added, {len(modified_clean)} modified, and {len(removed_clean)} removed files."
    )

