from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from app.models import User
from app.utils.mailer import send_email
from app.database import SessionLocal

logger = logging.getLogger(__name__)

def check_subscriptions():
    """매일 자정 실행되는 구독/체험 만료 체크 및 자동 갱신 서비스"""
    db = SessionLocal()
    try:
        now = datetime.now()
        
        # 1. 체험판 만료 체크 (FREE)
        # 만료 2일 전 알림
        two_days_later = now + timedelta(days=2)
        expiring_soon_2d = db.query(User).filter(
            User.tier == "free",
            User.subscription_status == "trial",
            User.trial_end_date <= two_days_later,
            User.notification_sent_2days == False
        ).all()
        
        for agent in expiring_soon_2d:
            send_expiry_email(agent, days_left=2)
            agent.notification_sent_2days = True
            
        # 만료 당일 알림
        expiring_today = db.query(User).filter(
            User.tier == "free",
            User.subscription_status == "trial",
            User.trial_end_date <= now,
            User.notification_sent_today == False
        ).all()
        
        for agent in expiring_today:
            send_expiry_email(agent, days_left=0)
            agent.notification_sent_today = True
            agent.subscription_status = "expired"
            agent.grace_period_end_date = now + timedelta(days=7) # 7일 유예
            
        # 2. 유료 구독 리마인드 및 만료 처리 (Monthly/Yearly)
        # 만료 7일 전 리마인드
        seven_days_later = now + timedelta(days=7)
        remind_renewal = db.query(User).filter(
            User.tier.in_(["monthly", "yearly"]),
            User.subscription_status == "active",
            User.subscription_end_date <= seven_days_later,
            User.subscription_end_date > now
        ).all()
        
        for agent in remind_renewal:
            # 중복 발송 방지 로직 필요시 추가 (여선 생략)
            send_renewal_remind_email(agent)

        # 유료 구독 자동 갱신 시도
        to_renew = db.query(User).filter(
            User.tier.in_(["monthly", "yearly"]),
            User.subscription_status == "active",
            User.subscription_end_date <= now,
            User.billing_key != None
        ).all()
        
        for agent in to_renew:
            process_auto_renewal(agent, db)

        # 3. 결제 실패 상태 처리 (3일 유예 후 expired 전환)
        payment_failed_expired = db.query(User).filter(
            User.subscription_status == "payment_failed",
            User.grace_period_end_date <= now
        ).all()
        
        for agent in payment_failed_expired:
            agent.subscription_status = "expired"
            agent.grace_period_end_date = now + timedelta(days=7) # 다시 7일 읽기전용 부여
            logger.info(f"Agent {agent.email} transitioned from payment_failed to expired")

        # 4. 유예 기간 종료 체크 -> 블록 처리
        blocked_agents = db.query(User).filter(
            User.subscription_status == "expired",
            User.grace_period_end_date <= now
        ).all()
        
        for agent in blocked_agents:
            agent.subscription_status = "blocked"
            logger.info(f"Agent {agent.email} blocked due to grace period expiry")

        db.commit()
        logger.info("Subscription check completed successfully")
        
    except Exception as e:
        logger.error(f"Error during subscription check: {str(e)}")
        db.rollback()
    finally:
        db.close()

def send_expiry_email(agent, days_left):
    """체험 만료 메일 발송"""
    subject = f"[UNIFLOW] 무료 체험이 {'오늘' if days_left == 0 else f' {days_left}일 후'} 종료됩니다"
    
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">{agent.name}님, 안녕하세요!</h2>
        <p>UNIFLOW 무료 체험이 {'오늘' if days_left == 0 else f'<b>{days_left}일 후</b>'} 종료될 예정입니다.</p>
        <p>현재까지 관리 중인 <b>VIP {agent.vip_current_count}명</b>의 데이터는 계속 유지되지만, 기간 만료 후에는 신규 등록 및 수정이 제한될 수 있습니다.</p>
        
        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 25px 0;">
            <p style="margin-top: 0;"><b>유료 플랜으로 업그레이드 하세요:</b></p>
            <ul style="padding-left: 20px;">
                <li>Monthly Plan: ₩99,000 / 월 (VIP 50명)</li>
                <li>Yearly Plan: ₩950,000 / 년 (21% 할인 효과!)</li>
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <a href="https://uniflow.ai.kr/subscribe" style="background-color: #000; color: #fff; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">플랜 선택 및 업그레이드</a>
        </div>
        
        <p style="color: #999; font-size: 12px; margin-top: 30px;">※ 만료 후 7일간은 읽기 전용 모드로 이용 가능하며, 그 이후에는 계정이 차단될 수 있습니다.</p>
    </div>
    """
    send_email(agent.email, subject, body)

def process_auto_renewal(agent, db):
    """실제 카드 결제 요청 (토스 빌링 API 연동 가정)"""
    try:
        # 가상 결제 성공 처리 (실제 구현 시 토스 API 호출)
        logger.info(f"Attempting auto-renewal for {agent.email} using billing_key")
        
        # 성공 가정
        agent.last_payment_date = datetime.now()
        if agent.tier == "monthly":
            agent.subscription_end_date = agent.subscription_end_date + timedelta(days=30)
        else:
            agent.subscription_end_date = agent.subscription_end_date + timedelta(days=365)
            
        logger.info(f"Successfully renewed subscription for {agent.email}")
        
    except Exception as e:
        logger.error(f"Auto-renewal failed for {agent.email}: {str(e)}")
        agent.subscription_status = "payment_failed"
        agent.grace_period_end_date = datetime.now() + timedelta(days=3)
        # 결제 실패 안내 메일 발송 로직 추가 가능

def send_renewal_remind_email(agent):
    """결제 예정 7일 전 안내 메일"""
    subject = f"[UNIFLOW] 구독 정기 결제 예정 안내 (7일 후)"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">안녕하세요, {agent.name}님!</h2>
        <p>항상 UNIFLOW와 함께해 주셔서 감사합니다.</p>
        <p>7일 후인 <b>{agent.subscription_end_date.strftime('%Y-%m-%d')}</b>에 등록된 결제 수단으로 정기 결제가 진행될 예정입니다.</p>
        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 25px 0;">
            <p style="margin: 5px 0;"><b>구독 플랜:</b> {agent.tier.capitalize()} Plan</p>
            <p style="margin: 5px 0;"><b>결제 예정 금액:</b> ₩{99000 if agent.tier == 'monthly' else 950000:,}</p>
        </div>
        <p style="color: #666; font-size: 13px;">결제 수단 변경이 필요하시다면 미리 마이페이지에서 업데이트해 주세요.</p>
    </div>
    """
    send_email(agent.email, subject, body)
