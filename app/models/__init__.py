from sqlalchemy import Column, Integer, String, JSON, DateTime, Text, Boolean, Numeric, ForeignKey, Date
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Survey(Base):
    """설문 응답 모델"""
    __tablename__ = "surveys"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 사용자 정보
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True)
    
    # 비즈니스 정보
    business_type = Column(String(50), nullable=False)  # 대표/프리랜서/자영업
    industry = Column(String(100), nullable=False)
    years_in_business = Column(Integer, nullable=False)
    revenue_range = Column(String(50), nullable=False)
    team_size = Column(Integer, nullable=False)
    
    # 설문 응답 (JSON 형태로 저장)
    responses = Column(JSON, nullable=False)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class User(Base):
    """사용자 모델 (통합)"""
    __tablename__ = "users"
    
    id = Column(String(100), primary_key=True)  # Supabase UUID
    name = Column(String(100), nullable=False)
    phone = Column(String(50), unique=True, nullable=True)
    email = Column(String(100), unique=True, nullable=True, index=True)
    
    # 어드민 관련 필드
    # 구독 및 등급 관리
    tier = Column(String(50), default="free")  # free, monthly, yearly, core_member
    subscription_status = Column(String(50), default="trial")  # trial, active, expired, lifetime, payment_failed, blocked
    trial_start_date = Column(DateTime(timezone=True), nullable=True)
    trial_end_date = Column(DateTime(timezone=True), nullable=True)
    subscription_start_date = Column(DateTime(timezone=True), nullable=True)
    subscription_end_date = Column(DateTime(timezone=True), nullable=True)
    
    # VIP 관리 및 한도
    vip_limit = Column(Integer, default=5)
    vip_current_count = Column(Integer, default=0)
    
    # 유예 기간 및 알림 추적
    grace_period_end_date = Column(DateTime(timezone=True), nullable=True)
    notification_sent_2days = Column(Boolean, default=False)
    notification_sent_today = Column(Boolean, default=False)
    
    # 결제 및 정기 과금
    last_payment_date = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(50), nullable=True)  # tosspayments
    billing_key = Column(String(100), nullable=True)
    
    # 관리 및 기록용 필드
    memo = Column(Text, nullable=True)
    id_status = Column(String(50), name="status", default="active") # 기존 status 컬럼 유지하되 내부명 status로 매핑 (필요시)
    invitation_sent_at = Column(DateTime(timezone=True), nullable=True)
    auth_id = Column(String(100), nullable=True)  # Supabase Auth user.id
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(100), ForeignKey("users.id"), nullable=True)  # 초대한 에이전트
    onboarding_completed = Column(Boolean, default=False)
    
    # 프로필 확장 필드
    company_name = Column(String(100), nullable=True)
    job_title = Column(String(100), nullable=True)
    website = Column(String(200), nullable=True)
    specialty = Column(String(100), nullable=True)
    intro = Column(Text, nullable=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    address = Column(String(200), nullable=True)
    bank_name = Column(String(50), nullable=True)
    account_number = Column(String(100), nullable=True)
    account_holder = Column(String(50), nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AdminAction(Base):
    """관리자 활동 로그 모델"""
    __tablename__ = "admin_actions"
    
    id = Column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_id = Column(String(100), ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False) # tier_change, status_change, extend, bulk_extend, profile_update
    target_agent_id = Column(String(100), ForeignKey("users.id"), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    """리포트 모델"""
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    agent_id = Column(String(100), ForeignKey("users.id"), nullable=True)
    
    # 리포트 기본 정보 (수동 리포트용)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    template = Column(String(100), nullable=True)
    
    # 페르소나 분류
    persona_type = Column(String(50), nullable=False)  # 5가지 페르소나 중 하나
    
    # AI 분석 결과 (JSON)
    bottlenecks = Column(JSON, nullable=False)  # 병목 포인트 분석
    insights = Column(JSON, nullable=False)  # 핵심 인사이트
    recommendations = Column(JSON, nullable=False)  # 추천 사항
    
    # 리포트 내러티브 (감성 텍스트)
    narrative_text = Column(Text, nullable=False)
    
    # 정량적 데이터
    monthly_time_loss = Column(Integer, nullable=False)  # 시간 (시간 단위)
    monthly_cost_loss = Column(Integer, nullable=False)  # 비용 (원 단위)
    growth_delay_months = Column(Integer, nullable=False)  # 성장 지연 (개월)
    urgency_score = Column(Integer, nullable=False)  # 긴급도 (1-10)
    
    # 리포트 파일
    html_url = Column(String(500), nullable=True)
    pdf_url = Column(String(500), nullable=True)
    
    # 카카오톡 발송 여부
    kakao_sent = Column(Integer, default=0)  # 0: 미발송, 1: 발송 완료
    kakao_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Notification(Base):
    """공지사항/알림 모델"""
    __tablename__ = "notifications"
    
    id = Column(String(100), primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    target = Column(String(20), nullable=True)  # all, agent, vip
    created_by = Column(String(100), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentNote(Base):
    """에이전트 상담 메모 모델"""
    __tablename__ = "agent_notes"
    
    id = Column(String(100), primary_key=True)
    agent_id = Column(String(100), ForeignKey("users.id"))
    vip_id = Column(String(100), ForeignKey("users.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserNotification(Base):
    """사용자별 알림 읽음 상태"""
    __tablename__ = "user_notifications"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    notification_id = Column(String(100), ForeignKey("notifications.id"))
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentApplication(Base):
    """에이전트 신청 모델"""
    __tablename__ = "agent_applications"
    
    id = Column(String(100), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    experience = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SolutionRequest(Base):
    """VIP 솔루션 요청 모델"""
    __tablename__ = "solution_requests"
    
    id = Column(String(100), primary_key=True)
    vip_id = Column(String(100), ForeignKey("users.id"))
    agent_id = Column(String(100), ForeignKey("users.id"))
    service_type = Column(String(100), nullable=True)
    content = Column(Text, nullable=True)
    preferred_time = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")
    processing_memo = Column(Text, nullable=True)
    processing_type = Column(String(50), nullable=True) # direct, expert
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SolutionHistory(Base):
    """솔루션 요청 상태 변경 이력"""
    __tablename__ = "solution_histories"
    
    id = Column(String(100), primary_key=True)
    request_id = Column(String(100), ForeignKey("solution_requests.id"))
    status = Column(String(50), nullable=False)
    memo = Column(Text, nullable=True)
    created_by = Column(String(100), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SynergyService(Base):
    """시너지 서비스 모델"""
    __tablename__ = "synergy_services"
    
    id = Column(String(100), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    """에이전트 초대 모델"""
    __tablename__ = "invitations"
    
    id = Column(String(100), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    token = Column(String(100), unique=True, nullable=False)
    role = Column(String(20), default="agent")
    invited_by = Column(String(100), ForeignKey("users.id"))
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SynergyApplication(Base):
    """시너지 신청 내역 모델"""
    __tablename__ = "synergy_applications"
    
    id = Column(String(100), primary_key=True)
    service_id = Column(String(100), ForeignKey("synergy_services.id"))
    agent_id = Column(String(100), ForeignKey("users.id"))
    vip_id = Column(String(100), ForeignKey("users.id"))
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LoungePost(Base):
    """라운지 게시글 모델"""
    __tablename__ = "lounge_posts"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # lounge, sos, insight
    is_hidden = Column(Boolean, default=False)
    report_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReferralReward(Base):
    """추천 보상 모델"""
    __tablename__ = "referral_rewards"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    referred_user_id = Column(String(100), ForeignKey("users.id"))
    points = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WithdrawalRequest(Base):
    """출금 신청 모델"""
    __tablename__ = "withdrawal_requests"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    amount = Column(Integer, nullable=False)
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(100), nullable=True)
    account_holder = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")
    memo = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Quest(Base):
    """성장 미션 모델"""
    __tablename__ = "quests"
    
    id = Column(String(100), primary_key=True)
    vip_id = Column(String(100), ForeignKey("users.id"))
    agent_id = Column(String(100), ForeignKey("users.id"))
    title = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 고급 퀘스트 시스템 필드
    quest_order = Column(Integer, default=1)
    is_locked = Column(Boolean, default=True)
    ai_questions = Column(JSON, nullable=True)  # {intro, subtitle, checklist, minChecks}
    user_answers = Column(JSON, nullable=True)   # [checked_indices]
    ai_evaluation = Column(JSON, nullable=True)  # {passed, score, message, nextStep}
    checked_count = Column(Integer, default=0)


class HealthIndex(Base):
    """건강 지표 모델"""
    __tablename__ = "health_index"
    
    id = Column(String(100), primary_key=True)
    vip_id = Column(String(100), ForeignKey("users.id"))
    agent_id = Column(String(100), ForeignKey("users.id"))
    asset_stability = Column(Integer, default=50)
    time_independence = Column(Integer, default=50)
    physical_condition = Column(Integer, default=50)
    emotional_balance = Column(Integer, default=50)
    network_power = Column(Integer, default=50)
    system_leverage = Column(Integer, default=50)
    overall_score = Column(Integer, default=50)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PointTransaction(Base):
    """포인트 변동 이력 모델"""
    __tablename__ = "point_transactions"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    amount = Column(Integer, nullable=False)
    type = Column(String(20), nullable=False)  # add, deduct
    reason = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommunityComment(Base):
    """커뮤니티 댓글 모델"""
    __tablename__ = "community_comments"
    
    id = Column(String(100), primary_key=True)
    post_id = Column(String(100), ForeignKey("lounge_posts.id"))
    user_id = Column(String(100), ForeignKey("users.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SessionPayment(Base):
    """비회원 세션 결제 모델"""
    __tablename__ = "session_payments"
    
    id = Column(String(100), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=False)
    payment_amount = Column(Integer, default=0)
    payment_status = Column(String(20), default="pending")  # pending, completed, cancelled
    session_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvitationToken(Base):
    """에이전트 초대 토큰 모델 (신규 통합 프로세스용)"""
    __tablename__ = "invitation_tokens"
    
    id = Column(String(100), primary_key=True)
    token = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), ForeignKey("users.id"))
    email = Column(String(100), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    expired = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


