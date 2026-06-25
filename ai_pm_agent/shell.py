"""Safe shell command execution (argument lists only, never shell=True)."""

import logging
import subprocess

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120


def run(cmd: list[str], cwd: str | None = None,
        timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    """Run a command. Returns (ok, output).

    ok is True when the process exits 0. Output is stdout+stderr combined.
    """
    logger.info("Running command: %s cwd=%s", cmd, cwd)
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        ok = result.returncode == 0
        if not ok:
            logger.error("Command failed (%s): %s", result.returncode, output)
        return ok, output
    except subprocess.TimeoutExpired:
        logger.error("Command timed out: %s", cmd)
        return False, f"Command timed out after {timeout}s"
