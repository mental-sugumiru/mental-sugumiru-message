import os
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from google.cloud import firestore, secretmanager

from config import (
    DOCTOR_MAP,
    BOT_ID, ORGANIZATION_ID, MEDIBOT_BASE,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("medibot-tagger")

app = FastAPI()
db = firestore.Client(database="medibot-connect")
JST = timezone(timedelta(hours=9))

COLLECTION = "medibot_connect_processed_reservations"

class SessionExpired(Exception):
    pass

def get_session_cookie() -> str:
    project = os.environ["GCP_PROJECT"]
    secret_name = os.environ.get("SECRET_NAME", "medibot-session-cookie")
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    return client.access_secret_version(name=name).payload.data.decode().strip()

def medibot_client(cookie: str) -> httpx.Client:
    return httpx.Client(
        base_url=MEDIBOT_BASE,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
            "Origin": MEDIBOT_BASE,
            "Referer": f"{MEDIBOT_BASE}/schedule",
            "User-Agent": "MedibotDoctorTagger/1.0",
        },
        timeout=30.0,
    )

def fetch_events(client: httpx.Client, start: datetime, end: datetime) -> list[dict]:
    """スケジュールイベント配列を返す。多様なレスポンス構造に対応。"""
    r = client.post("/api/schedule", json={
        "botId": BOT_ID,
        "organizationId": ORGANIZATION_ID,
        "start": start.isoformat(),
        "end": end.isoformat(),
    })
    if r.status_code == 401:
        raise SessionExpired()
    r.raise_for_status()
    body = r.json()

    # 想定: {"status":"success","message":{"events":[...]}}
    # 念のため複数パターン対応
    if isinstance(body, list):
        return body
    msg = body.get("message", body) if isinstance(body, dict) else body
    if isinstance(msg, list):
        return msg
    if isinstance(msg, dict):
        return msg.get("events", [])
    return []

def add_tag(client: httpx.Client, friend_id: str, tag_id: str) -> None:
    """単一ユーザーに単一タグを付与する。

    ステップ配信の「タグ付与時」トリガーを発火させるため、
    `PUT /api/tags`（チャット画面と同じエンドポイント）を使用する。
    `POST /api/tags/bulk` は一括処理用でトリガーが発火しないため使用しない。
    """
    r = client.put("/api/tags", json={
        "botId": BOT_ID,
        "lineUserId": friend_id,
        "tagId": tag_id,
    })
    if r.status_code == 401:
        raise SessionExpired()
    r.raise_for_status()

def should_process(reservation_id: str, current_updated_at: str | None) -> bool:
    """この予約を今回処理すべきかどうかを判定する。

    - Firestore にレコードが無い: 新規予約 → 処理する
    - レコードがあり、保存済み updatedAt と現在の updatedAt が一致: 変更なし → スキップ
    - レコードはあるが保存済み updatedAt と異なる: 予約変更 → 再処理
    """
    snap = db.collection(COLLECTION).document(reservation_id).get()
    if not snap.exists:
        return True
    saved = snap.to_dict() or {}
    return saved.get("updatedAt") != current_updated_at

def mark_processed(
    reservation_id: str,
    friend_id: str,
    doctor: str,
    updated_at: str | None,
) -> None:
    db.collection(COLLECTION).document(reservation_id).set({
        "friendId": friend_id,
        "doctor": doctor,
        "updatedAt": updated_at,
        "processedAt": firestore.SERVER_TIMESTAMP,
    })

def notify_session_expired():
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if not webhook:
        return
    try:
        httpx.post(webhook, json={"text":
            "⚠️ Medibot のセッション Cookie が失効しました。"
            "Secret Manager の medibot-session-cookie を更新してください。"})
    except Exception:
        pass

def process_reservations() -> dict:
    cookie = get_session_cookie()
    now = datetime.now(JST)
    start = now - timedelta(hours=1)
    end = now + timedelta(days=14)

    summary = {"checked": 0, "tagged": 0, "skipped": 0, "errors": []}

    with medibot_client(cookie) as client:
        try:
            events = fetch_events(client, start, end)
        except SessionExpired:
            notify_session_expired()
            raise HTTPException(401, "Medibot session expired")
        except Exception as e:
            log.exception("fetch_events failed")
            raise HTTPException(500, f"fetch_events: {e}")

        log.info(f"fetched {len(events)} events")

        for ev in events:
            if not isinstance(ev, dict):
                continue
            # 自組織以外、ブロック枠、削除済みは除外
            if ev.get("organizationId") != ORGANIZATION_ID:
                continue
            if ev.get("eventType") == "block":
                continue
            if ev.get("isDeleted"):
                continue

            reservation_id = ev.get("id")
            friend_id = ev.get("friendId")
            resource_id = ev.get("resourceId")
            updated_at = ev.get("updatedAt")

            if not reservation_id or not friend_id or not resource_id:
                continue

            summary["checked"] += 1

            if not should_process(reservation_id, updated_at):
                summary["skipped"] += 1
                continue

            doctor = DOCTOR_MAP.get(resource_id)
            if not doctor:
                summary["errors"].append(
                    f"unknown resourceId={resource_id} for {reservation_id}")
                continue

            try:
                add_tag(client, friend_id, doctor["tag_id"])
                mark_processed(reservation_id, friend_id, doctor["name"], updated_at)
                summary["tagged"] += 1
                log.info(
                    f"Tagged {friend_id} as {doctor['name']} "
                    f"(reservation={reservation_id}, updatedAt={updated_at})")
            except SessionExpired:
                notify_session_expired()
                raise HTTPException(401, "Medibot session expired")
            except Exception as e:
                summary["errors"].append(f"{reservation_id}: {e}")
                log.exception("tag failed")

    return summary

# ---------- HTTP エンドポイント ----------
@app.get("/")
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/run")
async def run(request: Request):
    if request.headers.get("X-Trigger-Source") != "scheduler":
        raise HTTPException(403, "forbidden")
    return process_reservations()