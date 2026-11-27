import logging
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.datasets.sources import USER_AGENT

logger = logging.getLogger(__name__)

RETRIES = 6
TIMEOUT_SECONDS = 30


class FetchError(Exception):
    pass


def fetch(url: str, retries: int = RETRIES) -> bytes:
    """GET with exponential backoff on network errors, 429 and 5xx. 404 is raised immediately."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404 or (error.code < 500 and error.code != 429) or attempt == retries:
                raise FetchError(f"{error.code} for {url}") from error
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            delay = int(retry_after) if retry_after.isdigit() else 5 * 2 ** attempt
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == retries:
                raise FetchError(f"network error for {url}: {error}") from error
            delay = 2 ** attempt
        logger.warning("Retrying %s in %ss (attempt %s)", url, delay, attempt + 1)
        time.sleep(delay)
    raise FetchError(url)


def download(url: str, target: Path, expected_size: int | None = None, retries: int = RETRIES) -> Path:
    """Stream a large file to disk through a .part file. Skips the download when the file is already complete."""
    if target.is_file() and (expected_size is None or target.stat().st_size == expected_size):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1 << 20)
            if expected_size is not None and partial.stat().st_size != expected_size:
                raise FetchError(f"incomplete download of {url}: {partial.stat().st_size} of {expected_size} bytes")
            partial.replace(target)
            return target
        except (urllib.error.URLError, TimeoutError, ConnectionError, FetchError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code < 500 and error.code != 429:
                raise FetchError(f"{error.code} for {url}") from error
            if attempt == retries:
                raise FetchError(f"download failed for {url}: {error}") from error
            delay = 5 * 2 ** attempt
            logger.warning("Retrying download of %s in %ss (attempt %s)", url, delay, attempt + 1)
            time.sleep(delay)
    raise FetchError(url)
