# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastapi",
#     "uvicorn",
#     "opencv-python",
# ]
# ///
"""
远端多路摄像头 FastAPI 服务。

部署到 10.168.1.101，对外暴露：
    GET /cameras                  → 可用 camera_id 列表
    GET /snapshot/{camera_id}     → JPEG 单帧 (image/jpeg)
    GET /stream/{camera_id}       → MJPEG multipart 流

每路相机一个后台抓帧线程，避免 MJPEG 流阻塞 snapshot。

脚本头部使用 PEP 723 内联声明依赖，可直接用 `uv run --script` 跑，
不需要额外建 pyproject.toml 或手动 pip install。

-----------------------------------------------------------------------------
部署 (uv, 推荐)
-----------------------------------------------------------------------------
    # 把脚本拷到远端
    scp remote_camera_server.py create@10.168.1.101:/home/create/WorkSpace/micro_server/

    # 远端首次运行 (uv 会自动建 venv 并解析 PEP 723 依赖)
    ssh create@10.168.1.101
    cd /home/create/WorkSpace/micro_server
    uv run --script remote_camera_server.py \\
        --host 0.0.0.0 --port 8080 \\
        --camera head:4 \\
        --camera left_palm:0 \\
        --camera right_palm:2

-----------------------------------------------------------------------------
systemd unit (开机自启)
-----------------------------------------------------------------------------
在远端执行 (注意用 sudo tee 绕开 vim 权限问题，路径是 /etc/systemd/system/)：

    sudo tee /etc/systemd/system/camera-server.service > /dev/null <<'EOF'
    [Unit]
    Description=Smart Voice Robot Camera Server
    After=network.target

    [Service]
    Type=simple
    User=create
    WorkingDirectory=/home/create/WorkSpace/micro_server
    Environment=HOME=/home/create
    Environment=PATH=/home/create/.local/bin:/usr/local/bin:/usr/bin:/bin
    ExecStart=/home/create/.local/bin/uv run --script remote_camera_server.py --host 0.0.0.0 --port 8080 --camera head:4 --camera left_palm:0 --camera right_palm:2
    Restart=on-failure
    RestartSec=3

    [Install]
    WantedBy=multi-user.target
    EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now camera-server.service
    sudo systemctl status camera-server.service
    journalctl -u camera-server.service -f

注意:
    - 路径是 /etc/systemd/system/ (不是 /etc/system/)，前面必须 sudo。
    - uv 的绝对路径用 `which uv` 结果填，systemd 不继承 shell PATH。
    - Environment=HOME 不能省：uv 需要 $HOME/.cache/uv。
    - ExecStart 必须单行 (不要反斜杠换行)。
"""

from __future__ import annotations

import argparse
import platform
import threading
import time
from dataclasses import dataclass

import cv2
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse


# ============================================================================
# 相机 worker
# ============================================================================

@dataclass
class CameraConfig:
    camera_id: str
    index: int
    width: int = 640
    height: int = 480
    fps: float = 30.0


def _preferred_backend() -> int:
    if platform.system() == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


class CameraWorker:
    """后台线程持续抓帧；snapshot / stream 共用缓存。"""

    def __init__(self, cfg: CameraConfig):
        self.cfg = cfg
        self._cap: cv2.VideoCapture | None = None
        self._latest: bytes | None = None          # 缓存 JPEG bytes
        self._latest_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._open()
        self._thread = threading.Thread(
            target=self._loop, name=f"cam-{self.cfg.camera_id}", daemon=True,
        )
        self._thread.start()

    def _open(self) -> None:
        cap = cv2.VideoCapture(self.cfg.index, _preferred_backend())
        if not cap.isOpened():
            raise RuntimeError(
                f"无法打开相机 {self.cfg.camera_id} (index={self.cfg.index})"
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        print(f"[{self.cfg.camera_id}] opened /dev/video{self.cfg.index} "
              f"{self.cfg.width}x{self.cfg.height}")

    def _loop(self) -> None:
        period = 1.0 / max(1.0, self.cfg.fps)
        while not self._stop.is_set():
            t0 = time.monotonic()
            if self._cap is None:
                time.sleep(0.5)
                try:
                    self._open()
                except Exception as e:
                    print(f"[{self.cfg.camera_id}] reopen 失败: {e}")
                    continue
            ok, frame = self._cap.read()
            if not ok or frame is None:
                print(f"[{self.cfg.camera_id}] read 失败，尝试重连")
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
                time.sleep(0.2)
                continue
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                with self._latest_lock:
                    self._latest = buf.tobytes()
            dt = time.monotonic() - t0
            if dt < period:
                time.sleep(period - dt)

    def snapshot(self) -> bytes:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with self._latest_lock:
                if self._latest is not None:
                    return self._latest
            time.sleep(0.02)
        raise HTTPException(
            status_code=503,
            detail=f"相机 {self.cfg.camera_id} 尚未产生有效帧",
        )

    def stream_iter(self, boundary: str = "frame"):
        last_bytes: bytes | None = None
        # 以 fps 节奏推送；相机侧帧率固定，这里适度快一点避免阻塞
        interval = 1.0 / max(5.0, self.cfg.fps)
        while not self._stop.is_set():
            with self._latest_lock:
                data = self._latest
            if data is not None and data is not last_bytes:
                last_bytes = data
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n"
                    + data + b"\r\n"
                )
            time.sleep(interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


# ============================================================================
# 启动参数解析
# ============================================================================

def _parse_camera_arg(s: str) -> CameraConfig:
    """
    解析 --camera 参数：
        'head:4'                → id=head, index=4
        'left_palm:0:640x480'   → +分辨率
        'head:4:640x480@30'     → +fps
    """
    parts = s.split(":")
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            f"--camera 参数格式: id:index[:WxH[@fps]]，收到 {s!r}"
        )
    cam_id, index_str = parts[0], parts[1]
    width, height, fps = 640, 480, 30.0
    if len(parts) >= 3:
        res = parts[2]
        if "@" in res:
            res, fps_str = res.split("@", 1)
            fps = float(fps_str)
        if "x" in res:
            w, h = res.split("x", 1)
            width, height = int(w), int(h)
    return CameraConfig(
        camera_id=cam_id,
        index=int(index_str),
        width=width,
        height=height,
        fps=fps,
    )


# ============================================================================
# FastAPI 应用
# ============================================================================

def create_app(cameras: dict[str, CameraWorker]) -> FastAPI:
    app = FastAPI(title="smart-voice-robot remote camera server")

    @app.get("/cameras")
    def list_cameras():
        return {
            "cameras": [
                {
                    "id": w.cfg.camera_id,
                    "index": w.cfg.index,
                    "width": w.cfg.width,
                    "height": w.cfg.height,
                    "fps": w.cfg.fps,
                }
                for w in cameras.values()
            ]
        }

    @app.get("/snapshot/{camera_id}")
    def snapshot(camera_id: str):
        w = cameras.get(camera_id)
        if w is None:
            raise HTTPException(status_code=404, detail=f"未知相机: {camera_id}")
        data = w.snapshot()
        return Response(content=data, media_type="image/jpeg")

    @app.get("/stream/{camera_id}")
    def stream(camera_id: str):
        w = cameras.get(camera_id)
        if w is None:
            raise HTTPException(status_code=404, detail=f"未知相机: {camera_id}")
        boundary = "frame"
        return StreamingResponse(
            w.stream_iter(boundary),
            media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        )

    return app


# ============================================================================
# 入口
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--camera", action="append", type=_parse_camera_arg, default=None,
        help="可多次指定，格式 id:index[:WxH[@fps]]",
    )
    args = parser.parse_args()

    cam_cfgs = args.camera or [
        CameraConfig("head", 4),
        CameraConfig("left_palm", 0),
        CameraConfig("right_palm", 2),
    ]

    workers: dict[str, CameraWorker] = {}
    for cfg in cam_cfgs:
        try:
            w = CameraWorker(cfg)
            w.start()
            workers[cfg.camera_id] = w
        except Exception as e:
            print(f"[warn] 启动 {cfg.camera_id} 失败: {e}")

    if not workers:
        raise SystemExit("没有可用相机，退出。")

    app = create_app(workers)
    import uvicorn
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        for w in workers.values():
            w.stop()


if __name__ == "__main__":
    main()
