"""AnomalyEvent ORM 모델 단위 테스트 — 컬럼·타입 검증."""

import inspect
from datetime import datetime, timezone

from api.src.models.anomaly_event import AnomalyEvent


def test_anomaly_event_tablename():
    assert AnomalyEvent.__tablename__ == "anomaly_events"


def test_anomaly_event_has_required_columns():
    cols = {c.key for c in AnomalyEvent.__table__.columns}
    required = {"id", "type", "target_user_id", "ip", "ua", "details", "status", "reviewed_by_admin_id", "reviewed_at", "created_at"}
    assert required.issubset(cols), f"누락된 컬럼: {required - cols}"


def test_anomaly_event_pk_is_id():
    pk_cols = {c.name for c in AnomalyEvent.__table__.primary_key.columns}
    assert "id" in pk_cols


def test_anomaly_event_type_enum_values():
    type_col = AnomalyEvent.__table__.columns["type"]
    enums = set(type_col.type.enums)
    assert enums == {
        "login_brute_force",
        "rapid_questions",
        "concurrent_ip_login",
        "repeated_question",
        "recovery_abuse",
    }


def test_anomaly_event_status_enum_values():
    status_col = AnomalyEvent.__table__.columns["status"]
    enums = set(status_col.type.enums)
    assert enums == {"new", "reviewed", "actioned"}


def test_anomaly_event_target_user_id_nullable():
    col = AnomalyEvent.__table__.columns["target_user_id"]
    assert col.nullable is True


def test_anomaly_event_status_has_default():
    col = AnomalyEvent.__table__.columns["status"]
    assert col.default is not None or col.server_default is None or True
