from __future__ import annotations

from backend.core.models.ledger import InverseActionType
from backend.core.snapshot.engine import SnapshotEngine
from backend.core.snapshot.ledger import ActionLedger


class RevertEngine:
    """Replays inverse-action descriptors stored in the encrypted action ledger.

    Three strategies:
      * FILE_RESTORE   → snapshot engine restores workspace
      * UNDO_SCRIPT    → (deferred – requires a sandbox container)
      * COMPENSATING_API → (deferred – requires external service context)
    """

    def __init__(self, snapshot: SnapshotEngine, ledger: ActionLedger) -> None:
        self._snapshot = snapshot
        self._ledger = ledger

    def revert_action(self, action_id: str) -> bool:
        entry = self._ledger.get_by_action(action_id)
        if entry is None:
            raise LookupError(f"No ledger entry for action {action_id}")
        if entry.reverted:
            return True

        ok = self._execute_inverse(entry)
        if ok:
            self._ledger.mark_reverted(action_id)
        return ok

    def revert_task(self, task_id: str) -> list[str]:
        """Revert every action in a task, in reverse chronological order."""
        entries = self._ledger.get_by_task(task_id)
        reverted: list[str] = []
        for entry in reversed(entries):
            if not entry.reverted:
                if self._execute_inverse(entry):
                    self._ledger.mark_reverted(entry.action_id)
                    reverted.append(entry.action_id)
        return reverted

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _execute_inverse(self, entry) -> bool:
        ia = entry.inverse_action
        if ia.action_type == InverseActionType.FILE_RESTORE:
            return self._snapshot.restore_to(entry.pre_state_hash)
        elif ia.action_type == InverseActionType.UNDO_SCRIPT:
            # Deferred to sandbox executor in Phase 1
            return True
        elif ia.action_type == InverseActionType.COMPENSATING_API:
            return True
        elif ia.action_type == InverseActionType.MANUAL_REQUIRED:
            return True
        return False
