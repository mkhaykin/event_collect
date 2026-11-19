from pydantic import BaseModel, ConfigDict

from libs.models.types import TaskParamsType, TaskType


class TaskDescription(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str

    device_uid: str
    device_name: str
    host_name: str = ""
    host_ip: str

    task_uid: str
    task_name: str
    type: TaskType
    interval_sec: int = 60 * 3

    params: TaskParamsType
