"""并发与调度行为验证（pytest 风格，可直接 python 运行）。

覆盖：
1. 多档位任务并行走 GPU：1×S + 1×M + 1×L 同时运行，8 卡全部占用
2. 队头阻塞消除：高优先级 XL 任务在队首等待整机空闲时，后续 S 任务仍能立即调度
3. XL 严格独占：有任务占卡时 XL 不启动，占卡任务全部结束后 XL 获得全部 8 卡
4. 取消排队任务立即落库 CANCELED，且不影响其他任务
5. 混合并发（6 个 S + 2 个 M）全部成功，GPU 无泄漏
"""
import asyncio
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.main import app


ENDPOINT_TASK_TYPE = {
    "text": "text-to-text",
    "text-to-image": "text-to-image",
    "text-to-video": "text-to-video",
    "image-edit": "image-to-image",
    "image-to-video": "image-to-video",
}


def submit(c, h, endpoint, prompt="test", profile="standard", priority=5):
    body = {
        "task_type": ENDPOINT_TASK_TYPE[endpoint],
        "prompt": prompt,
        "model_profile": profile,
        "priority": priority,
    }
    r = c.post(f"/api/v1/generate/{endpoint}", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def wait_terminal(c, h, tid, timeout=60):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = c.get(f"/api/v1/tasks/{tid}", headers=h).json()
        if t["status"] in ("SUCCEEDED", "FAILED", "CANCELED"):
            return t
        time.sleep(0.3)
    raise AssertionError(f"task {tid} timeout: {t}")


def test_all():
    with TestClient(app) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # --- 1. 多档位并行：S(1) + M(2) + L(4) = 7 卡同时占用 ---
        t_s = submit(c, h, "text", profile="fast")
        t_m = submit(c, h, "text-to-image", profile="standard")
        t_l = submit(c, h, "text-to-video", profile="standard")
        import time
        time.sleep(1.5)
        busy = c.get("/api/v1/monitor/gpus", headers=h).json()["busy"]
        assert len(busy) == 7, f"expect 7 busy GPUs, got {busy}"
        for t in (t_s, t_m, t_l):
            final = wait_terminal(c, h, t["id"])
            assert final["status"] == "SUCCEEDED", final
        free = c.get("/api/v1/monitor/gpus", headers=h).json()["free"]
        assert free == [0, 1, 2, 3, 4, 5, 6, 7], free
        print("PASS 1: S+M+L 并行 7 卡，全部成功，GPU 释放")

        # --- 2. 队头阻塞消除：先用 L 占 4 卡，队首 XL（高优先）等待整机空闲，
        #        低优先 S 任务仍能立即用剩余 4 卡运行 ---
        t_block = submit(c, h, "text-to-video", profile="standard", priority=5)  # L 占 4 卡
        time.sleep(0.8)
        t_xl = submit(c, h, "text-to-video", profile="high", priority=1)  # XL，队首等待
        time.sleep(0.2)
        t_small = submit(c, h, "text", profile="fast", priority=9)  # S，低优先
        time.sleep(1.2)
        small = c.get(f"/api/v1/tasks/{t_small['id']}", headers=h).json()
        xl = c.get(f"/api/v1/tasks/{t_xl['id']}", headers=h).json()
        assert small["status"] in ("RUNNING", "SUCCEEDED"), small
        assert xl["status"] in ("QUEUED", "ALLOCATING"), xl  # XL 等整机空闲，不抢占
        print("PASS 2: XL 队首等待，低优先 S 任务仍被调度（无队头阻塞）")

        # --- 3. 前序任务全部结束后 XL 独占 8 卡 ---
        for t in (t_block, t_small):
            final = wait_terminal(c, h, t["id"], timeout=90)
            assert final["status"] == "SUCCEEDED", final
        final_xl = wait_terminal(c, h, t_xl["id"], timeout=90)
        assert final_xl["status"] == "SUCCEEDED", final_xl
        assert len(final_xl["gpu_ids"].split(",")) == 8, final_xl["gpu_ids"]
        print("PASS 3: XL 独占 8 卡（gang scheduling）后成功")

        # --- 4. 取消排队任务 ---
        t_blocker = submit(c, h, "text-to-video", profile="standard", priority=1)  # L 占 4 卡
        t_wait = submit(c, h, "text-to-video", profile="standard", priority=2)  # L 排队
        t_cancel = submit(c, h, "text-to-video", profile="standard", priority=3)  # L 排队
        time.sleep(0.5)
        r = c.post(f"/api/v1/tasks/{t_cancel['id']}/cancel", headers=h)
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        canceled = c.get(f"/api/v1/tasks/{t_cancel['id']}", headers=h).json()
        assert canceled["status"] == "CANCELED", canceled
        for t in (t_blocker, t_wait):
            final = wait_terminal(c, h, t["id"], timeout=90)
            assert final["status"] == "SUCCEEDED", final
        print("PASS 4: 排队任务取消立即生效，其余任务不受影响")

        # --- 5. 混合并发：6×S + 2×M 全部成功 ---
        tasks = [submit(c, h, "text", profile="fast") for _ in range(6)]
        tasks += [submit(c, h, "text-to-image", profile="standard") for _ in range(2)]
        for t in tasks:
            final = wait_terminal(c, h, t["id"], timeout=90)
            assert final["status"] == "SUCCEEDED", final
        free = c.get("/api/v1/monitor/gpus", headers=h).json()["free"]
        assert free == [0, 1, 2, 3, 4, 5, 6, 7], f"GPU 泄漏: {free}"
        print("PASS 5: 6×S + 2×M 混合并发全部成功，GPU 无泄漏")

        # --- 6. 图生视频素材校验 ---
        r = c.post("/api/v1/generate/image-to-video",
                   json={"task_type": "image-to-video", "prompt": "move"}, headers=h)
        assert r.status_code == 422, r.text
        print("PASS 6: 图生视频无参考图返回 422")

    print("\nALL CONCURRENCY TESTS PASSED")


if __name__ == "__main__":
    import os
    if os.path.exists("aigc_platform.db"):
        os.remove("aigc_platform.db")
    test_all()
