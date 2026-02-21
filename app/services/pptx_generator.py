"""
PPTX 생성 서비스 (python-pptx 기반)
- 인터뷰 데이터를 받아 전문 제안서 PPTX를 생성
- 스타일: mckinsey(맥킨지), amazon(아마존), ib(IB 투자은행), uniflow(기본)
"""
import io
import os
from typing import Optional
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


# ─── 스타일 팔레트 정의 ───────────────────────────────────────────────────────
STYLE_CONFIG = {
    "mckinsey": {
        "name": "McKinsey Style",
        "bg_color": RGBColor(0xFF, 0xFF, 0xFF),       # 흰 배경
        "title_color": RGBColor(0x00, 0x30, 0x5E),    # 맥킨지 진청색
        "accent_color": RGBColor(0x00, 0x6A, 0xA7),   # 밝은 파랑
        "text_color": RGBColor(0x1A, 0x1A, 0x1A),
        "title_font": "Calibri",
        "body_font": "Calibri",
        "title_size": Pt(28),
        "body_size": Pt(14),
    },
    "amazon": {
        "name": "Amazon Style",
        "bg_color": RGBColor(0xFF, 0xFF, 0xFF),
        "title_color": RGBColor(0xFF, 0x99, 0x00),    # 아마존 오렌지
        "accent_color": RGBColor(0x14, 0x6E, 0xB4),
        "text_color": RGBColor(0x0F, 0x1F, 0x2E),
        "title_font": "Arial",
        "body_font": "Arial",
        "title_size": Pt(26),
        "body_size": Pt(13),
    },
    "ib": {
        "name": "IB Style",
        "bg_color": RGBColor(0x0A, 0x14, 0x28),       # 다크 네이비
        "title_color": RGBColor(0xFF, 0xFF, 0xFF),
        "accent_color": RGBColor(0xC9, 0xA0, 0x3C),   # 골드
        "text_color": RGBColor(0xE8, 0xE8, 0xE8),
        "title_font": "Times New Roman",
        "body_font": "Arial",
        "title_size": Pt(28),
        "body_size": Pt(13),
    },
    "uniflow": {
        "name": "UNIFLOW Style",
        "bg_color": RGBColor(0x0D, 0x11, 0x17),       # 다크 배경
        "title_color": RGBColor(0x7C, 0x3A, 0xED),    # 보라 primary
        "accent_color": RGBColor(0x06, 0xB6, 0xD4),   # 시안
        "text_color": RGBColor(0xF1, 0xF5, 0xF9),
        "title_font": "Arial",
        "body_font": "Arial",
        "title_size": Pt(28),
        "body_size": Pt(13),
    },
}


def _add_text_box(slide, text: str, left, top, width, height,
                  font_name: str, font_size, bold: bool,
                  color: RGBColor, align=PP_ALIGN.LEFT, word_wrap: bool = True):
    """텍스트 박스를 슬라이드에 추가하는 헬퍼 함수"""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = word_wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = font_size
    run.font.bold = bold
    run.font.color.rgb = color
    return txBox


def _add_bg_rect(slide, prs, color: RGBColor):
    """슬라이드 전체 배경색을 채우는 사각형 추가"""
    from pptx.util import Pt
    width = prs.slide_width
    height = prs.slide_height
    bg = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        0, 0, width, height
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    # 배경을 맨 뒤로
    slide.shapes._spTree.remove(bg._element)
    slide.shapes._spTree.insert(2, bg._element)


def _add_accent_line(slide, prs, color: RGBColor, top_offset=Inches(1.5)):
    """타이틀 아래 강조선 추가"""
    line = slide.shapes.add_shape(
        1,
        Inches(0.5), top_offset,
        prs.slide_width - Inches(1.0), Pt(3)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = color
    line.line.fill.background()


def _slide_cover(prs: Presentation, interview_data: dict, style: dict) -> None:
    """표지 슬라이드 생성"""
    slide_layout = prs.slide_layouts[6]  # 빈 레이아웃
    slide = prs.slides.add_slide(slide_layout)
    _add_bg_rect(slide, prs, style["bg_color"])

    title_text = interview_data.get("proposalTitle") or interview_data.get("title") or "AI 전략 제안서"
    recipient = interview_data.get("recipient", "")
    purpose = interview_data.get("purpose", "")

    W = prs.slide_width
    H = prs.slide_height

    # 상단 강조선
    _add_accent_line(slide, prs, style["accent_color"], top_offset=Inches(0.4))

    # 메인 타이틀
    _add_text_box(
        slide, title_text,
        Inches(0.6), Inches(1.2), W - Inches(1.2), Inches(2.0),
        style["title_font"], style["title_size"] + Pt(8), True,
        style["title_color"], PP_ALIGN.LEFT
    )

    # 수신자 / 목적 서브타이틀
    if recipient or purpose:
        sub = f"수신: {recipient}" if recipient else ""
        if purpose:
            sub += f"\n목적: {purpose}" if sub else f"목적: {purpose}"
        _add_text_box(
            slide, sub,
            Inches(0.6), Inches(3.6), W - Inches(1.2), Inches(1.5),
            style["body_font"], style["body_size"], False,
            style["text_color"], PP_ALIGN.LEFT
        )

    # 하단 날짜 / 브랜드
    from datetime import date
    footer = f"UNIFLOW  ·  {date.today().strftime('%Y.%m')}"
    _add_text_box(
        slide, footer,
        Inches(0.6), H - Inches(0.8), W - Inches(1.2), Inches(0.5),
        style["body_font"], Pt(10), False,
        style["accent_color"], PP_ALIGN.LEFT
    )


def _slide_agenda(prs: Presentation, sections: list[str], style: dict) -> None:
    """목차 슬라이드"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg_rect(slide, prs, style["bg_color"])

    W = prs.slide_width

    _add_text_box(
        slide, "목 차 (AGENDA)",
        Inches(0.6), Inches(0.4), W - Inches(1.2), Inches(0.8),
        style["title_font"], style["title_size"], True,
        style["title_color"], PP_ALIGN.LEFT
    )
    _add_accent_line(slide, prs, style["accent_color"], top_offset=Inches(1.25))

    # 섹션별 번호 + 항목
    for i, section in enumerate(sections, 1):
        _add_text_box(
            slide, f"{i:02d}.  {section}",
            Inches(0.8), Inches(1.4 + i * 0.75), W - Inches(1.6), Inches(0.65),
            style["body_font"], style["body_size"] + Pt(1), False,
            style["text_color"], PP_ALIGN.LEFT
        )


def _slide_content(prs: Presentation, title: str, bullets: list[str], style: dict) -> None:
    """일반 콘텐츠 슬라이드 (제목 + 불릿 리스트)"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg_rect(slide, prs, style["bg_color"])

    W = prs.slide_width

    _add_text_box(
        slide, title,
        Inches(0.6), Inches(0.35), W - Inches(1.2), Inches(0.9),
        style["title_font"], style["title_size"], True,
        style["title_color"], PP_ALIGN.LEFT
    )
    _add_accent_line(slide, prs, style["accent_color"], top_offset=Inches(1.2))

    # 불릿
    txBox = slide.shapes.add_textbox(Inches(0.6), Inches(1.4), W - Inches(1.2), Inches(4.5))
    tf = txBox.text_frame
    tf.word_wrap = True

    for i, bullet in enumerate(bullets):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.space_before = Pt(6)
        run = p.add_run()
        run.text = f"▸  {bullet}"
        run.font.name = style["body_font"]
        run.font.size = style["body_size"]
        run.font.color.rgb = style["text_color"]


def _slide_closing(prs: Presentation, interview_data: dict, style: dict) -> None:
    """마무리 슬라이드"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg_rect(slide, prs, style["bg_color"])

    W = prs.slide_width
    H = prs.slide_height

    proposer = interview_data.get("proposerInfo", "")
    if not proposer:
        proposer = "제안사: UNIFLOW"

    _add_accent_line(slide, prs, style["accent_color"], top_offset=Inches(2.6))

    _add_text_box(
        slide, "감사합니다",
        Inches(0.6), Inches(1.5), W - Inches(1.2), Inches(1.0),
        style["title_font"], style["title_size"] + Pt(10), True,
        style["title_color"], PP_ALIGN.CENTER
    )
    _add_text_box(
        slide, proposer,
        Inches(0.6), Inches(3.0), W - Inches(1.2), Inches(1.0),
        style["body_font"], style["body_size"], False,
        style["text_color"], PP_ALIGN.CENTER
    )

    from datetime import date
    _add_text_box(
        slide, f"UNIFLOW  ·  {date.today().strftime('%Y.%m')}",
        Inches(0.6), H - Inches(0.8), W - Inches(1.2), Inches(0.5),
        style["body_font"], Pt(10), False,
        style["accent_color"], PP_ALIGN.CENTER
    )


# ─── 메인 생성 함수 ───────────────────────────────────────────────────────────
def generate_pptx(interview_data: dict, ai_summary: Optional[str] = None) -> bytes:
    """
    인터뷰 데이터로 PPTX 파일을 생성하고 bytes 반환.
    
    Args:
        interview_data: FlowDeckSession에서 수집한 인터뷰 데이터
        ai_summary: AI가 생성한 제안서 요약 텍스트 (있으면 슬라이드에 반영)
    
    Returns:
        PPTX 바이너리 데이터
    """
    # 스타일 결정
    style_key = str(interview_data.get("style", "uniflow")).lower()
    style = STYLE_CONFIG.get(style_key, STYLE_CONFIG["uniflow"])

    # 판형(레이아웃) 결정
    layout_key = str(interview_data.get("layout", "widescreen")).lower()
    prs = Presentation()
    if layout_key == "a4":
        # A4 세로 (210×297mm)
        prs.slide_width  = Inches(8.27)
        prs.slide_height = Inches(11.69)
    elif layout_key == "square":
        prs.slide_width  = Inches(7.5)
        prs.slide_height = Inches(7.5)
    else:  # widescreen (16:9 기본)
        prs.slide_width  = Inches(13.33)
        prs.slide_height = Inches(7.5)

    # ── 1. 표지 ──────────────────────────────────────────────────────────────
    _slide_cover(prs, interview_data, style)

    # ── 2. 목차 ──────────────────────────────────────────────────────────────
    sections = [
        "제안 배경 및 목적",
        "시장 분석 및 기회",
        "핵심 전략 제안",
        "실행 계획 및 타임라인",
        "기대 효과 및 결론",
    ]
    _slide_agenda(prs, sections, style)

    # ── 3. 섹션 슬라이드 ─────────────────────────────────────────────────────
    purpose = interview_data.get("purpose", "")
    core_content = interview_data.get("coreContent", "")
    market_data = interview_data.get("marketData", "")

    # 슬라이드 3: 제안 배경 및 목적
    bg_bullets = [
        purpose or "본 제안서는 비즈니스 성장 기회를 포착하기 위해 작성되었습니다.",
        "시장 환경 변화에 대응하는 선제적 전략을 수립합니다.",
        "데이터 기반 의사결정으로 리스크를 최소화합니다.",
    ]
    _slide_content(prs, sections[0], bg_bullets, style)

    # 슬라이드 4: 시장 분석
    market_bullets = [
        market_data or "글로벌 시장 규모 및 성장률 분석 데이터를 기반으로 합니다.",
        "경쟁사 대비 차별화 포인트를 명확히 제시합니다.",
        "핵심 타겟 고객군과 세그먼트를 정의합니다.",
    ]
    _slide_content(prs, sections[1], market_bullets, style)

    # 슬라이드 5: 핵심 전략
    strategy_bullets = []
    if core_content:
        # 줄바꿈 기준으로 분할
        raw_lines = [l.strip() for l in core_content.split("\n") if l.strip()]
        strategy_bullets = raw_lines[:5] if raw_lines else [core_content]
    if not strategy_bullets:
        strategy_bullets = [
            "차별화된 핵심 가치를 중심으로 전략을 구성합니다.",
            "단계적 실행으로 리스크를 분산합니다.",
            "KPI 설정과 모니터링 체계를 구축합니다.",
        ]
    _slide_content(prs, sections[2], strategy_bullets, style)

    # 슬라이드 6: 실행 계획
    timeline_bullets = [
        "Phase 1 (1–3개월): 기반 구축 및 초기 실행",
        "Phase 2 (4–6개월): 본격 확장 및 성과 측정",
        "Phase 3 (7–12개월): 최적화 및 스케일업",
        "분기별 리뷰를 통한 전략 조정 프로세스 운영",
    ]
    _slide_content(prs, sections[3], timeline_bullets, style)

    # 슬라이드 7: 기대 효과 (+ AI 요약 반영)
    if ai_summary:
        summary_lines = [l.strip("·-•▸ ") for l in ai_summary.split("\n") if l.strip()]
        effect_bullets = summary_lines[:5] if summary_lines else []
    else:
        effect_bullets = []
    if not effect_bullets:
        effect_bullets = [
            "비용 절감 및 운영 효율화로 수익성 개선",
            "브랜드 인지도 향상 및 고객 신뢰도 강화",
            "데이터 기반 의사결정 체계 확립",
            "지속 가능한 성장 기반 마련",
        ]
    _slide_content(prs, sections[4], effect_bullets, style)

    # ── 4. 마무리 ─────────────────────────────────────────────────────────────
    _slide_closing(prs, interview_data, style)

    # ── bytes 반환 ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()
