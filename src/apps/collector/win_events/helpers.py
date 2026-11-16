import asyncio
import json
from typing import Any, AsyncGenerator, Generator

from pypsrp.powershell import PowerShell, PSInvocationState, RunspacePool
from pypsrp.wsman import WSMan

# маркер конца потока (Sentinel)
_STREAM_END = object()


def _get_next_chunk_safe(iterator: Any) -> Any:
    """Безопасно извлекает следующий кусок в потоке, глуша StopIteration."""
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_END


def _sync_powershell_stream(wsman_params: dict, ps_script: str) -> Generator[str, None, None]:
    """Синхронный внутренний генератор (выполняется строго в отдельном потоке)."""
    wsman = WSMan(**wsman_params)

    with RunspacePool(wsman) as pool:
        ps = PowerShell(pool)
        ps.add_script(ps_script)
        ps.begin_invoke()

        while ps.state == PSInvocationState.RUNNING:
            ps.poll_invoke()
            yield from ps.output
            ps.clear_streams()

        ps.end_invoke()
        yield from ps.output
        ps.clear_streams()


async def stream_powershell_output(
    windows_host: str,
    windows_port: int,
    powershell_script: str,
    username: str,
    password: str,
) -> AsyncGenerator[str, None]:
    """Асинхронный генератор, который не блокирует Event Loop при сетевом WinRM I/O."""
    params = {
        "server": windows_host,
        "port": windows_port,
        "username": username,
        "password": password,
        "ssl": False,
    }

    loop = asyncio.get_running_loop()
    iterator = _sync_powershell_stream(params, powershell_script)

    while True:
        chunk = await loop.run_in_executor(None, _get_next_chunk_safe, iterator)
        # TODO стоит переделать на None наверное
        if chunk is _STREAM_END:
            break

        yield chunk


async def parse_json_stream(
    raw_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[dict, None]:
    decoder = json.JSONDecoder()
    buffer = ""
    async for chunk in raw_stream:
        buffer += chunk
        pos = 0

        while True:
            while pos < len(buffer) and buffer[pos].isspace():
                pos += 1

            if pos >= len(buffer):
                buffer = ""
                break

            try:
                obj, pos = decoder.raw_decode(buffer, pos)
                yield obj
            except json.JSONDecodeError:
                buffer = buffer[pos:]
                break
