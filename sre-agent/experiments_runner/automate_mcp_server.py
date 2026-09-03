# 仅当 MCP server 使用 HTTP streamable 协议时使用此脚本

import os
import re
import sys
import time
import signal
import logging
from pathlib import Path

import pexpect


_MCP_CHILD = None  # Global handle to the spawned MCP server (pexpect.spawn)


logger = logging.getLogger(__name__)


def _detect_ready_patterns(child, timeout=60):
    """
    Wait for common HTTP server readiness signals printed by FastMCP/uvicorn.

    返回：
        tuple[bool, str|None]: (ready, detected_url)
    """
    # 选择这些模式以覆盖常见的 uvicorn 和通用 HTTP 服务启动日志
    patterns = [
        r"Uvicorn running on (http[s]?://[^\s]+)",
        r"Application startup complete",
        r"Running on (http[s]?://[^\s]+)",
        r"listening on (http[s]?://[^\s]+)",
        r"http[s]?://[^\s]+",
    ]

    try:
        idx = child.expect(patterns, timeout=timeout)
        # 如果可能，尝试提取 URL
        m = re.search(r"http[s]?://[^\s]+", child.after or "")
        return True, m.group(0) if m else None
    except pexpect.TIMEOUT:
        return False, None


def start_mcp_server(
    python_executable: str | None = None,
    server_path: str | Path | None = None,
    cwd: str | Path | None = None,
    ready_timeout: int = 60,
    silence_on_ready: bool = True,
    stream_output: bool = False,
):
    """
    Start the MCP server as a background process, wait until it's listening,
    then optionally silence its output so the experiment can continue cleanly.

    参数：
        python_executable: Absolute path to Python interpreter. Defaults to current interpreter.
        server_path: Path to MCP server script (mcp_server.py). Defaults to repo's MCP-server/mcp_server.py.
        cwd: Working directory to run from. Defaults to repo root.
        ready_timeout: Seconds to wait for readiness logs.
    silence_on_ready: If True, stop streaming server output once ready.
    stream_output: If True, stream server stdout to this process until ready.

    返回：
        tuple[pexpect.spawn, str|None]: (child process handle, detected server URL if any)

    Raises:
        RuntimeError: If the server fails to start within timeout.
    """
    global _MCP_CHILD

    repo_root = Path(__file__).resolve().parents[2]  # .../k8s-datagraph-rca
    if cwd is None:
        cwd = repo_root
    else:
        cwd = Path(cwd).resolve()

    if server_path is None:
        server_path = repo_root / "MCP-server" / "mcp_server.py"
    else:
        server_path = Path(server_path).resolve()

    if python_executable is None:
        python_executable = sys.executable

    if not server_path.exists():
        raise FileNotFoundError(f"MCP server script not found at: {server_path}")

    cmd = f"{python_executable} {server_path}"

    logger.info("正在启动 MCP 服务")
    logger.info("工作目录：%s", cwd)
    logger.info("命令：%s", cmd)

    # 通过 PTY 启动进程，便于读取日志并在后续静音输出
    child = pexpect.spawn(
        cmd,
        encoding="utf-8",
        timeout=ready_timeout,
        cwd=str(cwd),
    )

    if stream_output:
        child.logfile_read = sys.stdout

    ready, url = _detect_ready_patterns(child, timeout=ready_timeout)
    if not ready:
        # 输出尾部缓冲内容，便于诊断
        tail = (child.before or "").splitlines()[-5:]
        try:
            child.close(force=True)
        except Exception:
            pass
        if tail:
            logger.error("MCP server failed to start. Last lines before timeout:\n%s", "\n".join(tail))
        else:
            logger.error("MCP server failed to start and produced no output")
        raise RuntimeError(
            "MCP 服务在超时时间内未就绪。\n" +
            ("Last lines:\n" + "\n".join(tail) if tail else "No output captured.")
        )

    if silence_on_ready:
        # 停止向控制台持续输出，但保持进程在后台运行
        child.logfile_read = None

    _MCP_CHILD = child

    logger.info("MCP server is listening%s", f" at {url}" if url else "")
    if silence_on_ready and stream_output:
        logger.info("Output silenced; continuing your experiment...")

    return child, url


def cleanup_mcp_server(grace_period: float = 5.0) -> bool:
    """
    Terminate the MCP server process and its terminal.

    参数：
        grace_period: Seconds to wait after SIGTERM before forcing SIGKILL.

    返回：
        bool: True if the process is no longer alive, False otherwise.
    """
    global _MCP_CHILD

    if _MCP_CHILD is None:
        # 无需清理
        return True

    child = _MCP_CHILD
    _MCP_CHILD = None

    logger.info("正在停止 MCP 服务")

    try:
        # 先尝试优雅终止
        pid = getattr(child, "pid", None)
        if isinstance(pid, int):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        # 稍作等待，给优雅退出留出时间
        t0 = time.time()
        while time.time() - t0 < grace_period:
            if not child.isalive():
                break
            time.sleep(0.2)

        if child.isalive():
            # 若进程仍存活，则强制终止
            pid = getattr(child, "pid", None)
            if isinstance(pid, int):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

        # 确保 PTY 已关闭
        try:
            child.close(force=True)
        except Exception:
            pass

        alive = child.isalive() if hasattr(child, "isalive") else False
        if not alive:
            logger.info("MCP server terminated")
            return True
        else:
            logger.warning("MCP server may still be running")
            return False

    except Exception as e:
        logger.exception("停止 MCP 服务时出错：%s", e)
        return False


if __name__ == "__main__":
    # 简单的手动测试辅助入口
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    try:
        _, url = start_mcp_server(ready_timeout=90, stream_output=True)
        logger.info("MCP server ready: %s", url or "(url not detected)")
        logger.info("Sleeping for 5 seconds before cleanup...")
        time.sleep(5)
    finally:
        cleanup_mcp_server()
