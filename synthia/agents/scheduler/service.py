from datetime import datetime
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from synthia.helpers.pubsub import pubsub
from synthia.service.models import TaskTrigger


async def _publish_task_trigger(task: str, name: str, silent: bool = False) -> None:
    await pubsub.publish(TaskTrigger(task=task, name=name, silent=silent))


class SchedulerService:
    def __init__(self, postgres_url: str):
        url = postgres_url.replace("postgresql://", "postgresql+psycopg://")
        jobstores = {"default": SQLAlchemyJobStore(url=url)}
        self._scheduler = AsyncIOScheduler(jobstores=jobstores)

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown()
        logger.info("Scheduler shut down")

    def add_job(
        self, name: str, start_date: datetime | str, seconds: int | float, task: str, silent: bool = False
    ) -> dict[str, Any]:
        trigger = IntervalTrigger(seconds=seconds, start_date=start_date)

        self._scheduler.add_job(
            "synthia.agents.scheduler.service:_publish_task_trigger",
            trigger=trigger,
            id=name,
            replace_existing=True,
            args=[task, name, silent],
        )
        logger.info(f"Added job '{name}' with start_date '{start_date}' and interval {seconds} seconds")
        return {"name": name, "start_date": str(start_date), "seconds": seconds, "task": task}

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []
        for job in self._scheduler.get_jobs():
            trigger = job.trigger
            interval_seconds = None
            start_date = None
            if isinstance(trigger, IntervalTrigger):
                interval_seconds = trigger.interval_length
                start_date = str(trigger.start_date) if trigger.start_date else None
            jobs.append(
                {
                    "name": job.id,
                    "interval_seconds": interval_seconds,
                    "start_date": start_date,
                    "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                }
            )
        return jobs

    def delete_job(self, name: str) -> bool:
        job = self._scheduler.get_job(name)
        if job:
            self._scheduler.remove_job(name)
            logger.info(f"Deleted job '{name}'")
            return True
        logger.warning(f"Job '{name}' not found")
        return False

    async def trigger_job(self, name: str) -> bool:
        job = self._scheduler.get_job(name)
        if job and job.args:
            task, job_name = job.args
            await pubsub.publish(TaskTrigger(task=task, name=job_name))
            logger.info(f"Triggered job '{name}' for immediate execution")
            return True
        logger.warning(f"Job '{name}' not found")
        return False

    async def delete_all_jobs(self) -> None:
        self._scheduler.remove_all_jobs()
        logger.info("Deleted all jobs")
