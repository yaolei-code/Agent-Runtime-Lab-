# Frontend

The first-stage frontend is served directly by FastAPI from `backend/static`.

This directory is reserved for a future extracted frontend if the UI grows enough to justify a separate build toolchain. The current implementation intentionally avoids React/Vite because the app only needs a focused Agent Control Plane UI with Chat, Trace, Memory, Approvals, and Tools.
