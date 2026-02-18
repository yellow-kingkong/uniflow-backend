import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from app.config import get_settings

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

def send_email(to_email: str, subject: str, body: str):
    """
    Gmail SMTP를 이용해 이메일을 발송합니다.
    """
    if not settings.smtp_password:
        logger.error("SMTP_PASSWORD가 설정되지 않았습니다.")
        return False

    try:
        # 메시지 구성
        msg = MIMEMultipart()
        msg['From'] = f"UNIFLOW <{settings.sender_email}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        # SMTP 서버 연결
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        server.starttls() # TLS 보안 시작
        
        # 로그인 및 발송
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"이메일 발송 성공: {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"이메일 발송 실패 ({to_email}): {str(e)}")
        return False

def send_vip_invite(to_email: str, vip_name: str, invite_link: str):
    """VIP 초대 메일 발송"""
    subject = f"[UNIFLOW] {vip_name}님, 유니플로우에 초대되었습니다."
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">안녕하세요, {vip_name}님!</h2>
        <p>비즈니스 성장 파트너 <b>UNIFLOW</b>에 초대되셨습니다.</p>
        <p>아래 버튼을 클릭하여 회원가입을 완료하고 리포트를 확인해 보세요.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{invite_link}" style="background-color: #000; color: #fff; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">초대 수락 및 가입하기</a>
        </div>
        <p style="color: #666; font-size: 13px;">본 초대장은 발송 후 7일간 유효합니다.</p>
    </div>
    """
    return send_email(to_email, subject, body)

def send_payment_success_email(to_email: str, user_name: str, plan_name: str, amount: int, next_date: str):
    """결제 성공 알림 메일"""
    subject = f"[UNIFLOW] 구독 결제가 완료되었습니다"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">결제가 완료되었습니다!</h2>
        <p>{user_name}님, 안녕하세요. UNIFLOW <b>{plan_name}</b> 구독이 시작(또는 갱신) 되었습니다.</p>
        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px; margin: 25px 0;">
            <p style="margin: 5px 0;"><b>결제 금액:</b> ₩{amount:,}</p>
            <p style="margin: 5px 0;"><b>다음 결제 예정일:</b> {next_date}</p>
        </div>
        <p style="color: #666; font-size: 13px;">항상 UNIFLOW를 이용해 주셔서 감사합니다.</p>
    </div>
    """
    return send_email(to_email, subject, body)

def send_payment_failed_email(to_email: str, user_name: str, reason: str):
    """결제 실패 알림 메일"""
    subject = f"[UNIFLOW] 정기 결제 실패 안내"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #d32f2f;">결제 처리 중 오류가 발생했습니다</h2>
        <p>{user_name}님, 안녕하세요. UNIFLOW 정기 구독 결제가 실패했습니다.</p>
        <p style="color: #f44336;"><b>실패 사유: {reason}</b></p>
        <p>3일 이내에 결제 수단을 업데이트하지 않으시면 서비스 이용이 제한될 수 있습니다.</p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="https://uniflow.ai.kr/payment/update" style="background-color: #000; color: #fff; padding: 12px 20px; text-decoration: none; border-radius: 5px;">결제 수단 업데이트</a>
        </div>
    </div>
    """
    return send_email(to_email, subject, body)
