"""Agent Run 状态常量。

集中管理状态字符串，避免在 runtime/API/UI 扩展时到处散落魔法字符串。
当前仍保持字符串值不变，避免影响已有数据库记录和 API 响应。
"""

from enum import StrEnum


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
