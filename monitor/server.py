"""监控后台服务 — FastAPI + WebSocket + Vue 前端"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import queue
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from config import save_config

# Vue build 产物目录（与本文件同级的 dist/）
_DIST_DIR = Path(__file__).parent / "dist"

# 允许通过 API 读取/修改的配置字段白名单（不暴露 API Key 等敏感字段）
_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "wake_mode", "asr_backend", "tts_backend", "use_llm_planner",
    "llm_provider", "llm_model", "llm_base_url", "llm_request_timeout",
    "llm_system_prompt", "llm_max_history",
    "tts_speed", "tts_volume", "dialog_timeout",
    "tick_interval", "log_level",
    "startup_sound_enabled", "onnx_provider",
})


class MonitorServer:
    """后台监控服务：FastAPI + WebSocket，在 daemon 线程中运行。

    主线程通过 state_queue 推送树快照；visitor 推入数据后调用 notify_new_state()
    通过 call_soon_threadsafe 立即唤醒 WebSocket handler，消除轮询滞后。
    conversation_log 由 SpeakResponse 节点直接 append，无需加锁（CPython GIL 保护）。
    audio_metrics 由外部（VoiceEngine）写入。
    """

    def __init__(self, port: int = 8765, config=None) -> None:
        self.port = port
        self._config = config          # RobotConfig 实例，可在启动后通过属性赋值
        self.state_queue: queue.Queue = queue.Queue(maxsize=8)
        self.conversation_log: list[dict] = []
        self.audio_metrics: dict = {}
        self._clients: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._new_state_event: asyncio.Event | None = None
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # 公共接口（供主线程调用）
    # ------------------------------------------------------------------

    def notify_new_state(self) -> None:
        """从主线程通知 WebSocket handler 有新数据（线程安全）"""
        if self._loop is not None and self._new_state_event is not None:
            self._loop.call_soon_threadsafe(self._new_state_event.set)

    def log_conversation(self, user_text: str, robot_text: str) -> None:
        """追加一轮对话记录（由 SpeakResponse 调用）"""
        if user_text:
            self.conversation_log.append({"role": "user",  "text": user_text})
        if robot_text:
            self.conversation_log.append({"role": "robot", "text": robot_text})
        # 只保留最近 60 条
        if len(self.conversation_log) > 60:
            self.conversation_log = self.conversation_log[-60:]

    def start_background(self) -> None:
        """在 daemon 线程中启动 uvicorn"""
        t = threading.Thread(
            target=uvicorn.run,
            args=(self._app,),
            kwargs={
                "host": "0.0.0.0",
                "port": self.port,
                "log_level": "error",
            },
            daemon=True,
            name="MonitorServer",
        )
        t.start()

    # ------------------------------------------------------------------
    # 私有：构建 FastAPI 应用
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        @contextlib.asynccontextmanager
        async def lifespan(_: FastAPI):
            self._loop = asyncio.get_event_loop()
            self._new_state_event = asyncio.Event()
            yield

        app = FastAPI(title="Robot Monitor", docs_url=None, redoc_url=None, lifespan=lifespan)

        # ── Config REST API ──────────────────────────────────────────

        @app.get("/api/config")
        async def get_config():
            if self._config is None:
                return JSONResponse({"error": "config not attached"}, status_code=503)
            raw = dataclasses.asdict(self._config)
            return {k: v for k, v in raw.items() if k in _EDITABLE_FIELDS}

        @app.patch("/api/config")
        async def patch_config(request: Request):
            if self._config is None:
                return JSONResponse({"error": "config not attached"}, status_code=503)
            updates: dict = await request.json()
            applied: dict = {}
            rejected: list[str] = []
            for key, value in updates.items():
                if key not in _EDITABLE_FIELDS:
                    rejected.append(key)
                    continue
                try:
                    setattr(self._config, key, value)
                    applied[key] = value
                except Exception as exc:
                    logger.warning(f"[Monitor] 配置更新失败 {key!r}: {exc}")
                    rejected.append(key)
            if applied:
                logger.info(f"[Monitor] 配置已更新: {list(applied.keys())}")
                try:
                    save_config(self._config)
                except Exception as exc:
                    logger.warning(f"[Monitor] 配置持久化失败: {exc}")
            return {"applied": applied, "rejected": rejected}

        # ── WebSocket ────────────────────────────────────────────────

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            self._clients.append(ws)
            try:
                while True:
                    # lifespan 未就绪时短暂等待（极少发生）
                    if self._new_state_event is None:
                        await asyncio.sleep(0.1)
                        continue

                    # 等待 notify_new_state() 通知，最多 2 秒后发 keepalive
                    try:
                        await asyncio.wait_for(
                            self._new_state_event.wait(), timeout=2.0
                        )
                        self._new_state_event.clear()
                    except asyncio.TimeoutError:
                        # keepalive ping，发送失败说明客户端已断开，静默退出
                        try:
                            await ws.send_json({"ping": True})
                        except Exception:
                            break
                        continue

                    # 取队列最新帧（丢弃积压的旧帧，只发最新一帧）
                    state = None
                    while not self.state_queue.empty():
                        try:
                            state = self.state_queue.get_nowait()
                        except queue.Empty:
                            break

                    if state is not None:
                        state["audio"] = dict(self.audio_metrics)
                        try:
                            await ws.send_json(state)
                        except Exception:
                            # 客户端已断开（正常情况），静默退出循环
                            break
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                logger.debug(f"[Monitor] WebSocket 异常断开: {exc}")
            finally:
                if ws in self._clients:
                    self._clients.remove(ws)

        # ── 静态文件（Vue 产物）──────────────────────────────────────
        # 必须在 /api/* 和 /ws 之后挂载，避免路由被覆盖

        if _DIST_DIR.exists():
            assets_dir = _DIST_DIR / "assets"
            if assets_dir.exists():
                app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

            # SPA 兜底：所有未匹配路由返回 index.html
            @app.get("/{full_path:path}")
            async def spa_fallback(full_path: str):
                return FileResponse(_DIST_DIR / "index.html")
        else:
            logger.warning(
                f"[Monitor] 前端产物目录不存在: {_DIST_DIR}，"
                "请先在 monitor/frontend/ 下执行 npm run build"
            )

            @app.get("/")
            async def no_frontend():
                return JSONResponse(
                    {"error": "前端未构建，请执行 npm run build", "dist": str(_DIST_DIR)},
                    status_code=503,
                )

        return app
