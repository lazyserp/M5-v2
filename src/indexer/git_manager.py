import os
import re
import subprocess
from typing import Tuple, Optional

class GitRepoManager:
    """
    Manages fast shallow git cloning, pulling, and repository URL normalization.
    """
    def __init__(self, base_storage_dir: str = "./storage/repos"):
        self.base_storage_dir = base_storage_dir
        os.makedirs(self.base_storage_dir, exist_ok=True)

    @staticmethod
    def parse_repo_url(repo_url: str) -> Tuple[str, str]:
        """
        Extracts (org_id, repo_id) from GitHub, GitLab, or Bitbucket URLs.
        Examples:
          https://github.com/psf/requests.git -> ('psf', 'requests')
          git@github.com:facebook/react.git -> ('facebook', 'react')
        """
        clean_url = repo_url.strip()
        if clean_url.endswith(".git"):
            clean_url = clean_url[:-4]

        # Match HTTPS or SSH git URL patterns
        match = re.search(r"[:/]([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)$", clean_url)
        if match:
            org_id = re.sub(r"[^a-zA-Z0-9_]", "_", match.group(1).lower())
            repo_id = re.sub(r"[^a-zA-Z0-9_]", "_", match.group(2).lower())
            return org_id, repo_id

        # Fallback to generic naming if pattern doesn't match
        return "external_org", "git_repo"

    @staticmethod
    def detect_default_branch(target_url: str) -> Optional[str]:
        """
        Auto-detects the remote repository's default branch (e.g. master, main, develop)
        using git ls-remote so callers don't have to guess.
        """
        try:
            res = subprocess.run(
                ["git", "ls-remote", "--symref", target_url, "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.startswith("ref: refs/heads/"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1].replace("refs/heads/", "")
                    return parts[0].replace("ref: refs/heads/", "")
        except Exception:
            pass
        return None

    def clone_or_pull(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Performs a fast shallow clone (--depth 1) or fast-forward pull.
        Returns: (local_repo_path, org_id, repo_id)
        """
        org_id, repo_id = self.parse_repo_url(repo_url)
        dest_folder = os.path.join(self.base_storage_dir, f"{org_id}_{repo_id}").replace("\\", "/")

        # Format authenticated URL if token provided
        target_url = repo_url
        if access_token and repo_url.startswith("https://"):
            target_url = repo_url.replace("https://", f"https://{access_token}@")

        if os.path.exists(dest_folder) and os.path.exists(os.path.join(dest_folder, ".git")):
            # Repo already exists -> pull latest changes
            try:
                cmd = ["git", "pull", "--depth", "1"]
                subprocess.run(cmd, cwd=dest_folder, check=True, capture_output=True, text=True)
            except Exception:
                pass
        else:
            # Auto-detect default branch if not explicitly specified
            effective_branch = branch
            if not effective_branch:
                effective_branch = self.detect_default_branch(target_url)

            # Shallow clone
            cmd = ["git", "clone", "--depth", "1"]
            if effective_branch:
                cmd.extend(["-b", effective_branch])
            cmd.extend([target_url, dest_folder])

            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                err_msg = e.stderr or str(e)
                raise RuntimeError(f"Git clone failed for '{repo_url}': {err_msg}")

        return dest_folder, org_id, repo_id

git_manager = GitRepoManager()
