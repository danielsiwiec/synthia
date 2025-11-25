from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

import pytest

from synthia.agents.scheduler.service import SchedulerService
from synthia.helpers.pubsub import PubSub, pubsub
from synthia.service.models import TaskTrigger
from tests.helpers import await_until


@pytest.fixture
async def scheduler_service() -> AsyncGenerator[SchedulerService]:
    service = SchedulerService(postgres_url="")
    service.start()
    yield service
    service.shutdown()


async def test_scheduler_triggers_task(clean_pubsub: PubSub, scheduler_service: SchedulerService) -> None:
    task_triggers: list[TaskTrigger] = []

    def capture_trigger(trigger: TaskTrigger) -> None:
        task_triggers.append(trigger)

    pubsub.subscribe(TaskTrigger, capture_trigger)

    await pubsub.start()

    job_name: str = "test_job"
    task: str = "test task"
    start_date: datetime = datetime.now() + timedelta(seconds=1)

    scheduler_service.add_job(name=job_name, start_date=start_date, seconds=60, task=task)

    await await_until(lambda: len(task_triggers) >= 1, "TaskTrigger", timeout=5)

    assert len(task_triggers) == 1
    assert task_triggers[0].name == job_name
    assert task_triggers[0].task == task
