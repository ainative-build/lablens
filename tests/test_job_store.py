"""Tests for in-memory job store."""

from lablens.orchestration.job_store import JobStatus, JobStore


def test_create_and_get():
    store = JobStore()
    job_id = store.create()
    job = store.get(job_id)
    assert job is not None
    assert job.status == JobStatus.QUEUED


def test_update_status():
    store = JobStore()
    job_id = store.create()
    store.update(job_id, JobStatus.COMPLETED, result={"test": True})
    job = store.get(job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"test": True}


def test_update_failed():
    store = JobStore()
    job_id = store.create()
    store.update(job_id, JobStatus.FAILED, error="Something broke")
    job = store.get(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error == "Something broke"


def test_unknown_job():
    store = JobStore()
    assert store.get("nonexistent") is None


def test_update_nonexistent():
    store = JobStore()
    store.update("nonexistent", JobStatus.COMPLETED)  # Should not raise


def test_multiple_jobs():
    store = JobStore()
    ids = [store.create() for _ in range(5)]
    assert len(set(ids)) == 5
    for job_id in ids:
        assert store.get(job_id) is not None
