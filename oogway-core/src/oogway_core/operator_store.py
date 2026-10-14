from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class OperatorAction:
    id: str
    action_type: str
    risk_level: str
    status: str
    arguments: dict[str, Any]
    reason: str
    requested_by: str
    requested_via: str
    result: dict[str, Any]
    error: str | None
    created_at: str


@dataclass(frozen=True)
class OperatorStore:
    dsn: str

    @staticmethod
    def _action(row: dict[str, Any]) -> OperatorAction:
        return OperatorAction(
            id=str(row["id"]),
            action_type=str(row["action_type"]),
            risk_level=str(row["risk_level"]),
            status=str(row["status"]),
            arguments=dict(row["arguments"] or {}),
            reason=str(row["reason"]),
            requested_by=str(row["requested_by"]),
            requested_via=str(row["requested_via"]),
            result=dict(row["result"] or {}),
            error=row["error"],
            created_at=row["created_at"].isoformat(),
        )

    def propose(
        self,
        *,
        action_type: str,
        risk_level: str,
        arguments: dict[str, Any],
        reason: str,
        requested_by: str,
        requested_via: str,
    ) -> OperatorAction:
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                INSERT INTO tokenspace_v2.operator_actions(
                    action_type, risk_level, arguments, reason,
                    requested_by, requested_via
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    action_type,
                    risk_level,
                    Jsonb(arguments),
                    reason,
                    requested_by,
                    requested_via,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("operator proposal returned no action")
        return self._action(row)

    def get(self, action_id: str) -> OperatorAction | None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT * FROM tokenspace_v2.operator_actions WHERE id = %s",
                (action_id,),
            ).fetchone()
        return None if row is None else self._action(row)

    def list(self, *, status: str | None = None, limit: int = 50) -> list[OperatorAction]:
        query = "SELECT * FROM tokenspace_v2.operator_actions"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = %s"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(min(max(limit, 1), 200))
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._action(row) for row in rows]

    def transition(
        self,
        action_id: str,
        *,
        from_status: str,
        to_status: str,
        actor: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        approval = ""
        params: list[Any] = [to_status]
        if to_status in {"approved", "rejected"}:
            approval = ", approved_by = %s, approved_at = now()"
            params.append(actor or "local-admin")
        timing = ""
        if to_status == "running":
            timing = ", started_at = now()"
        elif to_status in {"complete", "failed", "rejected", "cancelled"}:
            timing = ", completed_at = now()"
        extra = ""
        if result is not None:
            extra += ", result = %s"
            params.append(Jsonb(result))
        if error is not None:
            extra += ", error = %s"
            params.append(error[:8000])
        params.extend([action_id, from_status])
        with psycopg.connect(self.dsn) as connection:
            cursor = connection.execute(
                f"""
                UPDATE tokenspace_v2.operator_actions
                SET status = %s, updated_at = now(){approval}{timing}{extra}
                WHERE id = %s AND status = %s
                """,
                tuple(params),
            )
            return cursor.rowcount == 1

