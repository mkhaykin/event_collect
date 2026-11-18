from pydantic import BaseModel

from libs.models.types import TaskParamsType, TaskType


class TaskDescription(BaseModel):
    uid: str

    device_uid: str
    host_name: str
    host_ip: str

    task_uid: str
    type: TaskType
    interval_sec: int = 60 * 3

    params: TaskParamsType
