from typing import Literal

CheckType = Literal["icmp", "port"]  # TODO port удаляем наверное ...

TaskType = Literal["win_events",]

TaskParamsType = dict[str, str | int | float | bool | None]
