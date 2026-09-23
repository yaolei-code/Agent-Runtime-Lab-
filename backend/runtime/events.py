from enum import StrEnum


class TraceEventType(StrEnum):
    RUN_STARTED = "run_started"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_REQUESTED = "tool_requested"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_WRITTEN = "memory_written"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
