"""
Async Docker API client using httpx through the docker-api-proxy.

Replaces direct docker.sock access and docker CLI subprocess calls with
HTTP calls to the docker-api-proxy service (nginx → Docker Engine API).

Security: The webpanel container no longer needs Docker socket access,
eliminating the "docker.sock = root" attack vector.
"""
import json
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("webpanel.docker")

DOCKER_API_URL = os.environ.get("DOCKER_API_URL", "http://webpanel_docker_api_proxy:2375")
_CLIENT_TIMEOUT = 30.0


def _api_url(path: str) -> str:
    return f"{DOCKER_API_URL}{path}"


async def _request(
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    """Make an API request to the Docker Engine API via the proxy."""
    timeout = kwargs.pop("timeout", _CLIENT_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        resp = await client.request(method, _api_url(path), **kwargs)
        resp.raise_for_status()
        return resp


# ── Image operations ────────────────────────────────────────────────────

async def list_images(filter_name: str = "") -> list[dict]:
    """List Docker images. Optionally filter by name."""
    params = {}
    if filter_name:
        params["filters"] = json.dumps({"reference": [filter_name]})
    resp = await _request("GET", "/images/json", params=params)
    return resp.json()


# ── Container operations ────────────────────────────────────────────────

async def list_containers(all: bool = True, filters: Optional[dict] = None) -> list[dict]:
    """List containers. Returns Docker Engine API container objects."""
    params = {"all": "true" if all else "false"}
    if filters:
        params["filters"] = json.dumps(filters)
    resp = await _request("GET", "/containers/json", params=params)
    return resp.json()


async def inspect_container(container_name: str) -> dict:
    """Inspect a container by name or ID."""
    resp = await _request("GET", f"/containers/{container_name}/json")
    return resp.json()


async def create_container(
    name: str,
    image: str,
    cmd: Optional[list[str]] = None,
    host_config: Optional[dict] = None,
    env: Optional[list[str]] = None,
    volumes: Optional[list[str]] = None,
    labels: Optional[dict[str, str]] = None,
    network: Optional[str] = None,
    port_bindings: Optional[dict] = None,
    exposed_ports: Optional[dict] = None,
    mem_limit: Optional[str] = None,
    cpus: Optional[float] = None,
    tmpfs: Optional[dict[str, str]] = None,
) -> dict:
    """Create a new container. Returns creation result from Docker API."""
    body: dict = {
        "Image": image,
        "Hostname": name[:64],
    }
    if cmd:
        body["Cmd"] = cmd
    if env:
        body["Env"] = env
    if labels:
        body["Labels"] = labels
    if exposed_ports:
        body["ExposedPorts"] = {p: {} for p in exposed_ports}

    # Host config
    hc: dict = {}
    if host_config:
        hc.update(host_config)
    if network:
        hc["NetworkMode"] = network
    if port_bindings:
        hc["PortBindings"] = port_bindings
    if mem_limit:
        hc["Memory"] = _parse_mem(mem_limit)
    if cpus is not None:
        hc["NanoCpus"] = int(cpus * 1e9)
    if volumes:
        hc["Binds"] = volumes
    if tmpfs:
        hc["Tmpfs"] = tmpfs
    if hc:
        body["HostConfig"] = hc

    params = {"name": name}
    resp = await _request("POST", "/containers/create", params=params, json=body)
    return resp.json()


async def start_container(container_name: str) -> None:
    """Start a container."""
    await _request("POST", f"/containers/{container_name}/start")


async def stop_container(container_name: str, timeout: int = 15) -> None:
    """Stop a container with given timeout."""
    await _request("POST", f"/containers/{container_name}/stop", params={"t": str(timeout)})


async def restart_container(container_name: str, timeout: int = 15) -> None:
    """Restart a container."""
    await _request("POST", f"/containers/{container_name}/restart", params={"t": str(timeout)})


async def pause_container(container_name: str) -> None:
    """Pause a container."""
    await _request("POST", f"/containers/{container_name}/pause")


async def unpause_container(container_name: str) -> None:
    """Unpause a container."""
    await _request("POST", f"/containers/{container_name}/unpause")


async def kill_container(container_name: str) -> None:
    """Kill a container."""
    await _request("POST", f"/containers/{container_name}/kill")


async def remove_container(container_name: str, force: bool = True, volumes: bool = False) -> None:
    """Remove a container."""
    params = {"force": "true" if force else "false", "v": "true" if volumes else "false"}
    await _request("DELETE", f"/containers/{container_name}", params=params)


async def container_logs(
    container_name: str,
    tail: int = 100,
    stdout: bool = True,
    stderr: bool = True,
) -> str:
    """Fetch container logs. Returns combined stdout+stderr."""
    params = {
        "tail": str(tail),
        "stdout": "1" if stdout else "0",
        "stderr": "1" if stderr else "0",
    }
    resp = await _request("GET", f"/containers/{container_name}/logs", params=params)
    return resp.text


async def container_stats(container_name: str) -> dict:
    """Get live resource usage stats for a container."""
    resp = await _request("GET", f"/containers/{container_name}/stats", params={"stream": "false"})
    return resp.json()


async def all_containers_stats() -> dict[str, dict]:
    """Get stats for all containers. Returns dict keyed by container name."""
    containers = await list_containers(all=False)  # only running
    stats: dict = {}
    for c in containers:
        cid = c.get("Id", "")
        name = c.get("Names", [""])[0].lstrip("/") if c.get("Names") else cid
        try:
            s = await container_stats(cid)
            stats[name] = {
                "CPUPerc":  _calc_cpu_percent(s),
                "MemUsage": _calc_mem_usage(s),
                "MemPerc":  _calc_mem_percent(s),
                "NetIO":    _calc_net_io(s),
                "BlockIO":  _calc_block_io(s),
            }
        except Exception:
            continue
    return stats


async def exec_create(container_name: str, cmd: list[str], env: Optional[dict[str, str]] = None) -> str:
    """Create an exec instance in a container. Returns exec ID."""
    body: dict = {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True}
    if env:
        body["Env"] = [f"{k}={v}" for k, v in env.items()]
    resp = await _request("POST", f"/containers/{container_name}/exec", json=body)
    return resp.json()["Id"]


async def exec_start(exec_id: str, json_body: Optional[dict] = None) -> str:
    """Start an exec instance and capture output."""
    body = json_body or {"Detach": False, "Tty": False}
    resp = await _request("POST", f"/exec/{exec_id}/start", json=body)
    return resp.text


async def exec_run(container_name: str, cmd: list[str], stdin: str = "", env: Optional[dict[str, str]] = None) -> tuple[int, str]:
    """Run a command in a container and return (exit_code, output)."""
    exec_id = await exec_create(container_name, cmd, env=env)
    req_body: dict = {"Detach": False, "Tty": False}
    if stdin:
        req_body["Input"] = stdin
    output = await exec_start(exec_id, json_body=req_body if stdin else None)
    # Docker API exec inspect for exit code
    try:
        insp = await _request("GET", f"/exec/{exec_id}/json")
        exit_code = insp.json().get("ExitCode", -1)
    except Exception:
        exit_code = -1
    return exit_code, output


def exec_run_sync(container_name: str, cmd: list[str], stdin: str = "", timeout: int = 120) -> tuple[int, str]:
    """Synchronous version of exec_run for use in sync code paths (services, threads)."""
    import httpx as _httpx
    url = _api_url(f"/containers/{container_name}/exec")
    start_url = lambda eid: _api_url(f"/exec/{eid}/start")
    insp_url = lambda eid: _api_url(f"/exec/{eid}/json")

    with _httpx.Client(timeout=timeout, verify=False) as client:
        # Create exec instance
        exec_body: dict = {"Cmd": cmd, "AttachStdout": True, "AttachStderr": True}
        if stdin:
            exec_body["AttachStdin"] = True
        resp = client.post(url, json=exec_body)
        resp.raise_for_status()
        exec_id = resp.json()["Id"]

        # Start exec
        start_body: dict = {"Detach": False, "Tty": False}
        if stdin:
            start_body["Input"] = stdin
        resp2 = client.post(start_url(exec_id), json=start_body)
        output = resp2.text

        # Get exit code
        try:
            resp3 = client.get(insp_url(exec_id))
            exit_code = resp3.json().get("ExitCode", -1)
        except Exception:
            exit_code = -1

    return exit_code, output


# ── Docker Compose helpers ──────────────────────────────────────────────

async def compose_up(project_dir: str, service: Optional[str] = None) -> tuple[int, str]:
    """Run docker compose up -d for a service (or all services)."""
    import asyncio
    cmd = ["docker", "compose", "up", "-d"]
    if service:
        cmd.append(service)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, (stdout + stderr).decode()


async def compose_down(project_dir: str, service: Optional[str] = None) -> tuple[int, str]:
    """Run docker compose down for a service (or all services)."""
    import asyncio
    cmd = ["docker", "compose", "down"]
    if service:
        cmd.extend([service])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, (stdout + stderr).decode()


# ── Internal helpers ────────────────────────────────────────────────────

def _parse_mem(val: str) -> int:
    """Parse memory string like '512m', '2g' to bytes."""
    val = val.lower().strip()
    if val.endswith("g"):
        return int(float(val[:-1]) * 1024 * 1024 * 1024)
    elif val.endswith("m"):
        return int(float(val[:-1]) * 1024 * 1024)
    elif val.endswith("k"):
        return int(float(val[:-1]) * 1024)
    else:
        return int(val)


def _calc_cpu_percent(stats: dict) -> str:
    """Calculate CPU usage percentage from Docker stats JSON."""
    try:
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        sys_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        num_cpus = stats["cpu_stats"]["online_cpus"] or 1
        if sys_delta > 0:
            pct = (cpu_delta / sys_delta) * num_cpus * 100
            return f"{pct:.2f}%"
    except Exception:
        pass
    return "—"


def _calc_mem_usage(stats: dict) -> str:
    try:
        usage = stats["memory_stats"]["usage"] - stats["memory_stats"].get("stats", {}).get("cache", 0)
        limit = stats["memory_stats"]["limit"]
        return f"{_fmt_bytes(usage)} / {_fmt_bytes(limit)}"
    except Exception:
        return "—"


def _calc_mem_percent(stats: dict) -> str:
    try:
        usage = stats["memory_stats"]["usage"] - stats["memory_stats"].get("stats", {}).get("cache", 0)
        limit = stats["memory_stats"]["limit"]
        if limit > 0:
            return f"{usage / limit * 100:.2f}%"
    except Exception:
        return "—"


def _calc_net_io(stats: dict) -> str:
    try:
        networks = stats.get("networks", {})
        rx = sum(n.get("rx_bytes", 0) for n in networks.values())
        tx = sum(n.get("tx_bytes", 0) for n in networks.values())
        return f"{_fmt_bytes(rx)} / {_fmt_bytes(tx)}"
    except Exception:
        return "—"


def _calc_block_io(stats: dict) -> str:
    try:
        blk = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
        read = sum(b.get("value", 0) for b in blk if b.get("op") == "read")
        write = sum(b.get("value", 0) for b in blk if b.get("op") == "write")
        return f"{_fmt_bytes(read)} / {_fmt_bytes(write)}"
    except Exception:
        return "—"


def _fmt_bytes(b: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}TiB"
