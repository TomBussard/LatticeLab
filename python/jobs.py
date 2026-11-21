"""Keep one pricing worker so Excel calculations cannot overlap."""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from analyses import execute


JOBS = {}
LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=1)


def update_job(identifier: str, **values: object) -> None:
    """Publish one job update while holding the registry lock."""
    with LOCK:
        JOBS[identifier].update(values)


def run_job(identifier: str, payload: dict) -> None:
    """Publish progress and keep the result or error available for the browser."""
    update_job(identifier, state="running", progress="Preparing calculation")
    start = time.perf_counter()
    try:
        result = execute(payload, lambda message: update_job(identifier, progress=message))
        update_job(identifier, state="done", result=result, elapsed=time.perf_counter() - start)
    except Exception as error:
        update_job(identifier, state="error", error=str(error), elapsed=time.perf_counter() - start)


def enqueue(payload: dict) -> str:
    """Reserve a slot before handing the request to the single pricing worker."""
    if not isinstance(payload, dict) or not isinstance(payload.get("request"), dict):
        raise ValueError("The request is missing its calculation parameters")
    payload = public_parameters(payload)
    with LOCK:
        if sum(job["state"] in ("queued", "running") for job in JOBS.values()) >= 3:
            raise ValueError("Three calculations are already running or queued")
        finished = [key for key, job in JOBS.items() if job["state"] in ("done", "error")]
        for key in finished[:-20]:
            del JOBS[key]
        identifier = uuid.uuid4().hex
        JOBS[identifier] = {"id": identifier, "state": "queued", "progress": "Queued"}
        try:
            POOL.submit(run_job, identifier, payload)
        except RuntimeError:
            del JOBS[identifier]
            raise
    return identifier


def public_parameters(value: object) -> object:
    """Strip engine-only fields from a user-supplied request."""
    if isinstance(value, dict):
        return {
            key: public_parameters(item) for key, item in value.items() if not key.startswith("_")
        }
    if isinstance(value, list):
        return [public_parameters(item) for item in value]
    return value


def get_job(identifier):
    # The worker can finish while the HTTP response is being serialised.
    with LOCK:
        job = JOBS.get(identifier)
        return dict(job) if job is not None else None
