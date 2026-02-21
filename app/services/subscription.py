"""
구독 만료 / 자동갱신 스케줄러
매일 자정 실행: 체험 만료 → 유료 리마인드 → 자동갱신 → 유예 기간 처리

토스 빌링 API 연동 준비 완료 상태.
실제 API 호출은 TOSS_SECRET_KEY 환경 변수 설정 후 자동 활성화.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
import os
import base64
import httpx

from app.models import User
from app.utils.mailer import send_email
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────
TOSS_API_BASE   = "https://api.tosspayments.com/v1"
GRACE_DAYS      = 7    # 만료 후 읽기전용 유예 기간
PAYMENT_FAIL_GRACE = 3 # 결제 실패 후 재시도 유예 기간

# 요금제별 결제 금액 (billing_cycle → 가격)
TIER_PRICE_MAP: dict[str, dict[str, int]] = {
    "flow_one": {"monthly": 33000,  "yearly": 330000},
    "flow_pro": {"monthly": 55000,  "yearly": 550000},
    "flow_max": {"monthly": 99000,  "yearly": 950000},
}

# 툴킷 할인율 (tier → %)
TOOLKIT_DISCOUNT: dict[str, int] = {
    "first_flow": 0,
    "flow_one":   0,
    "flow_pro":  10,
    "flow_max":  20,
}

PLAN_CYCLE_DAYS = {"monthly": 30, "yearly": 365}
FIRST_FLOW_TRIAL_DAYS = 7  # 퍼스트 FLOW 무료 체험 기간


def _toss_auth_header() -> str | None:
    """토스페이먼츠 Basic Auth 헤더. 키 미설정 시 None 반환."""
    secret_key = os.environ.get("TOSS_SECRET_KEY", "")
    if not secret_key:
        return None
    token = base64.b64encode(f"{secret_key}:".encode()).decode()
    return f"Basic {token}"


# ── 메인 스케줄러 ─────────────────────────────────────────────

def check_subscriptions():
    """매일 자정 실행: 체험/유료 구독 상태 일괄 점검"""
    db = SessionLocal()
    try:
        now = datetime.now()
        _check_trial_expiry(db, now)
        _check_paid_renewal(db, now)
        _check_payment_failed(db, now)
        _check_grace_period(db, now)
        db.commit()
        logger.info("[Scheduler] 구독 점검 완료")
    except Exception as e:
        logger.error(f"[Scheduler] 오류: {e}")
        db.rollback()
    finally:
        db.close()


# ── 단계별 함수 ───────────────────────────────────────────────

def _check_trial_expiry(db: Session, now: datetime):
    """퍼스트 FLOW(7일 무료 체험) + 유료 trial 상태 만료 알림 및 전환"""

    # 퍼스트 FLOW: trial_end_date 기준 7일 체험 만료 체크
    for agent in db.query(User).filter(
        User.tier == "first_flow",
        User.subscription_status == "active",
        User.trial_end_date <= now,
    ).all():
        agent.subscription_status   = "expired"
        agent.grace_period_end_date = now + timedelta(days=GRACE_DAYS)
        logger.info(f"[스케줄러] 퍼스트FLOW 체험 만료: {agent.email}")
        # 만료 안내 메일
        _send_trial_expiry_email(agent, days_left=0)

    # D-2 알림
    two_days_later = now + timedelta(days=2)
    for agent in db.query(User).filter(
        User.subscription_status == "trial",
        User.trial_end_date <= two_days_later,
        User.trial_end_date > now,
        User.notification_sent_2days == False,
    ).all():
        _send_trial_expiry_email(agent, days_left=2)
        agent.notification_sent_2days = True
        logger.info(f"[스케줄러] D-2 알림 발송: {agent.email}")

    # 당일 만료 → expired + 유예 7일
    for agent in db.query(User).filter(
        User.subscription_status == "trial",
        User.trial_end_date <= now,
        User.notification_sent_today == False,
    ).all():
        _send_trial_expiry_email(agent, days_left=0)
        agent.notification_sent_today = True
        agent.subscription_status     = "expired"
        agent.grace_period_end_date   = now + timedelta(days=GRACE_DAYS)
        logger.info(f"[스케줄러] 체험 만료 처리: {agent.email}")


def _check_paid_renewal(db: Session, now: datetime):
    """유료 구독 갱신 리마인드 + 자동갱신 처리"""

    # D-7 리마인드
    seven_days_later = now + timedelta(days=7)
    for agent in db.query(User).filter(
        User.subscription_status == "active",
        User.tier.in_(TIER_PRICE_MAP.keys()),
        User.subscription_end_date <= seven_days_later,
        User.subscription_end_date > now,
    ).all():
        _send_renewal_remind_email(agent)
        logger.info(f"[Scheduler] 갱신 리마인드 발송: {agent.email}")

    # 만료일 도달 → 자동갱신 시도
    for agent in db.query(User).filter(
        User.subscription_status == "active",
        User.tier.in_(TIER_PRICE_MAP.keys()),
        User.subscription_end_date <= now,
    ).all():
        _process_auto_renewal(agent, db)


def _check_payment_failed(db: Session, now: datetime):
    """결제 실패 유예 종료 → expired 전환"""
    for agent in db.query(User).filter(
        User.subscription_status == "payment_failed",
        User.grace_period_end_date <= now,
    ).all():
        agent.subscription_status   = "expired"
        agent.grace_period_end_date = now + timedelta(days=GRACE_DAYS)
        logger.info(f"[Scheduler] 결제실패 → expired: {agent.email}")


def _check_grace_period(db: Session, now: datetime):
    """유예 기간 종료 → blocked 전환"""
    for agent in db.query(User).filter(
        User.subscription_status == "expired",
        User.grace_period_end_date <= now,
    ).all():
        agent.subscription_status = "blocked"
        logger.info(f"[Scheduler] 유예 종료 → blocked: {agent.email}")


# ── 자동갱신 핵심 로직 ────────────────────────────────────────

def _process_auto_renewal(agent: User, db: Session):
    """
    토스 빌링 API로 실제 자동 결제 요청.
    TOSS_SECRET_KEY 미설정 시 로그만 남기고 스킵.
    """
    auth_header = _toss_auth_header()

    # 빌링키 없거나 키 미설정 → 갱신 불가
    if not agent.billing_key or not auth_header:
        logger.warning(
            f"[AutoRenew] 갱신 불가 — billing_key 또는 TOSS_SECRET_KEY 없음: {agent.email}"
        )
        agent.subscription_status   = "payment_failed"
        agent.grace_period_end_date = datetime.now() + timedelta(days=PAYMENT_FAIL_GRACE)
        return

    # billing_cycle 판별 (기존 subscription_type 또는 새 tier cycle 필드 참조)
    billing_cycle = _infer_billing_cycle(agent)
    amount        = TIER_PRICE_MAP.get(agent.tier, {}).get(billing_cycle, 99000)

    # special_discount 적용
    discount = getattr(agent, "special_discount", 0) or 0
    amount   = int(amount * (1 - discount / 100))

    import uuid
    order_id   = str(uuid.uuid4())
    order_name = f"UNIFLOW {agent.tier} ({billing_cycle}) 자동갱신"

    try:
        import httpx, asyncio, json

        async def _call_toss():
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{TOSS_API_BASE}/billing/{agent.billing_key}",
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                    json={
                        "customerKey": agent.id,
                        "amount":      amount,
                        "orderId":     order_id,
                        "orderName":   order_name,
                        "metadata": {
                            "agentId":      agent.id,
                            "tier":         agent.tier,
                            "billing_cycle": billing_cycle,
                        },
                    },
                    timeout=15.0,
                )

        resp = asyncio.run(_call_toss())

        if resp.status_code == 200:
            now = datetime.now()
            days = PLAN_CYCLE_DAYS.get(billing_cycle, 30)
            agent.subscription_end_date   = agent.subscription_end_date + timedelta(days=days)
            agent.subscription_expires_at = agent.subscription_end_date
            agent.last_payment_date       = now
            agent.subscription_status     = "active"
            logger.info(f"[AutoRenew] 갱신 성공: {agent.email} / {amount:,}원")
        else:
            err = resp.json()
            logger.error(f"[AutoRenew] 갱신 실패: {agent.email} — {err}")
            _handle_renewal_failure(agent)

    except Exception as e:
        logger.error(f"[AutoRenew] 예외 발생: {agent.email} — {e}")
        _handle_renewal_failure(agent)


def _handle_renewal_failure(agent: User):
    """갱신 실패 시 payment_failed 상태로 전환 + 유예 부여"""
    agent.subscription_status   = "payment_failed"
    agent.grace_period_end_date = datetime.now() + timedelta(days=PAYMENT_FAIL_GRACE)
    _send_payment_failed_email(agent)


def _infer_billing_cycle(agent: User) -> str:
    """기존 데이터에서 monthly/yearly 추론"""
    # 새 컬럼이 있으면 우선
    if hasattr(agent, "billing_cycle") and agent.billing_cycle:
        return agent.billing_cycle
    # subscription_type이 yearly면 yearly 추론
    if getattr(agent, "subscription_type", "") == "yearly":
        return "yearly"
    return "monthly"


# ── 이메일 템플릿 ─────────────────────────────────────────────

def _send_trial_expiry_email(agent: User, days_left: int):
    subject = (
        f"[UNIFLOW] 무료 체험이 오늘 종료됩니다"
        if days_left == 0
        else f"[UNIFLOW] 무료 체험이 {days_left}일 후 종료됩니다"
    )
    timing = "오늘" if days_left == 0 else f"<b>{days_left}일 후</b>"
    body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;border:1px solid #eee;border-radius:10px;">
        <h2 style="color:#333;">{agent.name}님, 안녕하세요!</h2>
        <p>UNIFLOW 무료 체험이 {timing} 종료됩니다.</p>
        <p>현재 관리 중인 VIP <b>{getattr(agent,'vip_current_count',0)}명</b>의 데이터는 유지되지만,
        만료 후에는 신규 등록 및 수정이 제한됩니다.</p>

        <div style="background:#f9f9f9;padding:20px;border-radius:5px;margin:25px 0;">
            <p style="margin-top:0;"><b>유료 플랜으로 업그레이드 하세요:</b></p>
            <ul style="padding-left:20px;">
                <li>Flow One:  ₩99,000/월</li>
                <li>Flow Pro:  ₩199,000/월</li>
                <li>Flow Max:  ₩350,000/월</li>
            </ul>
        </div>
        <div style="text-align:center;margin-top:30px;">
            <a href="https://uniflow.ai.kr/subscribe"
               style="background:#000;color:#fff;padding:15px 25px;text-decoration:none;border-radius:5px;font-weight:bold;">
               플랜 선택 및 업그레이드
            </a>
        </div>
        <p style="color:#999;font-size:12px;margin-top:30px;">
            ※ 만료 후 {GRACE_DAYS}일간 읽기 전용 이용 가능, 이후 계정 차단될 수 있습니다.
        </p>
    </div>
    """
    send_email(agent.email, subject, body)


def _send_renewal_remind_email(agent: User):
    billing_cycle = _infer_billing_cycle(agent)
    amount        = TIER_PRICE_MAP.get(agent.tier, {}).get(billing_cycle, 99000)
    discount      = getattr(agent, "special_discount", 0) or 0
    final_amount  = int(amount * (1 - discount / 100))
    exp_date      = getattr(agent, "subscription_end_date", None)
    exp_str       = exp_date.strftime("%Y-%m-%d") if exp_date else "-"

    subject = "[UNIFLOW] 구독 정기 결제 예정 안내 (7일 후)"
    body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;border:1px solid #eee;border-radius:10px;">
        <h2 style="color:#333;">안녕하세요, {agent.name}님!</h2>
        <p>7일 후인 <b>{exp_str}</b>에 정기 결제가 진행될 예정입니다.</p>
        <div style="background:#f9f9f9;padding:20px;border-radius:5px;margin:25px 0;">
            <p style="margin:5px 0;"><b>플랜:</b> {agent.tier} ({billing_cycle})</p>
            <p style="margin:5px 0;"><b>결제 예정 금액:</b> ₩{final_amount:,}</p>
            {"<p style='margin:5px 0;color:#e44;'><b>특별 할인 " + str(discount) + "% 적용</b></p>" if discount else ""}
        </div>
        <p style="color:#666;font-size:13px;">결제 수단 변경이 필요하시면 미리 마이페이지에서 업데이트해 주세요.</p>
    </div>
    """
    send_email(agent.email, subject, body)


def _send_payment_failed_email(agent: User):
    subject = "[UNIFLOW] 자동 결제가 실패했습니다"
    body = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;border:1px solid #eee;border-radius:10px;">
        <h2 style="color:#e44;">{agent.name}님, 결제에 실패했습니다.</h2>
        <p>{PAYMENT_FAIL_GRACE}일 이내에 결제 수단을 업데이트하지 않으면 구독이 만료됩니다.</p>
        <div style="text-align:center;margin-top:30px;">
            <a href="https://uniflow.ai.kr/subscribe"
               style="background:#e44;color:#fff;padding:15px 25px;text-decoration:none;border-radius:5px;font-weight:bold;">
               결제 수단 업데이트
            </a>
        </div>
    </div>
    """
    send_email(agent.email, subject, body)
