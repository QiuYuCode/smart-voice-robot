"""通过 systemctl 重启 smart-voice-robot 系统服务。"""
from __future__ import annotations

import subprocess
import threading
import time

from loguru import logger


def restart_systemd_unit(unit: str, use_sudo: bool = True) -> tuple[bool, str]:
    """执行 systemctl restart。

    Args:
        unit: 单元名，如 smart-voice-robot.service。
        use_sudo: 是否使用 sudo -n（需配置 NOPASSWD）。

    Returns:
        (成功与否, 说明信息)
    """
    unit = unit.strip()
    if not unit:
        return False, "未配置 systemd 单元名"

    cmd = ["systemctl", "restart", unit]
    if use_sudo:
        cmd = ["sudo", "-n", *cmd]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return False, "未找到 systemctl 或 sudo 命令"
    except subprocess.TimeoutExpired:
        return False, "systemctl 执行超时"

    if proc.returncode == 0:
        return True, f"已执行: {' '.join(cmd)}"

    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = f"退出码 {proc.returncode}"
    return False, detail


def schedule_systemd_restart(
    unit: str,
    use_sudo: bool = True,
    delay_s: float = 0.8,
) -> None:
    """延迟在后台线程执行 restart，便于 HTTP 响应先返回客户端。"""

    def _worker() -> None:
        time.sleep(delay_s)
        ok, msg = restart_systemd_unit(unit, use_sudo=use_sudo)
        if ok:
            logger.info(f"[Monitor] {msg}")
        else:
            logger.error(f"[Monitor] systemctl restart 失败: {msg}")

    threading.Thread(
        target=_worker,
        daemon=True,
        name="MonitorSystemdRestart",
    ).start()


def fetch_unit_journal(
    unit: str,
    lines: int = 200,
    since: str | None = None,
    use_sudo: bool = True,
) -> tuple[bool, str, str]:
    """读取 systemd 单元 journal 日志。

    Returns:
        (成功与否, 日志正文, 错误信息)
    """
    unit = unit.strip()
    if not unit:
        return False, "", "未配置 systemd 单元名"

    lines = max(10, min(int(lines), 2000))
    cmd = [
        "journalctl",
        "-u",
        unit,
        "-n",
        str(lines),
        "--no-pager",
        "-o",
        "short-iso",
    ]
    if since:
        cmd.extend(["--since", since.strip()])

    attempts: list[list[str]] = [cmd]
    if use_sudo:
        attempts.append(["sudo", "-n", *cmd])

    last_err = ""
    for run_cmd in attempts:
        try:
            proc = subprocess.run(
                run_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return False, "", "未找到 journalctl 命令"
        except subprocess.TimeoutExpired:
            return False, "", "journalctl 执行超时"

        if proc.returncode == 0:
            text = (proc.stdout or "").strip()
            if not text:
                text = "(暂无日志输出)"
            return True, text + "\n", ""

        last_err = (proc.stderr or proc.stdout or "").strip() or f"退出码 {proc.returncode}"
        # 无 sudo 权限时再尝试 sudo
        if run_cmd is cmd and use_sudo:
            continue
        break

    return False, "", last_err or "读取日志失败"
