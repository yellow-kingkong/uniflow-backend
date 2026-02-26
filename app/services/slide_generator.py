"""
slide_generator.py — GPT JSON → HTML → html2pdf.app API PDF 변환 (v3)
- weasyprint/pyppeteer 완전 제거 → html2pdf.app REST API 사용
- 외부 서버 기반 렌더링: Railway 환경 의존성 없음, 한국어 완벽 지원
- 슬라이드 크기: 1280×720px (16:9)
- 한국어: Noto Sans KR Google Fonts
"""

import json
import logging
import os
import re
import requests
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 스타일 accent color 매핑 ──────────────────────────────────────────────
STYLE_ACCENT = {
    "mckinsey": "#004F9F",
    "amazon":   "#FF9900",
    "ib":       "#C9A03C",
    "uniflow":  "#7C3AED",
}

BG_COLOR_MAP = {
    "white":     "#FFFFFF",
    "lightgray": "#F0F2F5",
    "dark":      "#0D1117",
    "navy":      "#0A1428",
    "cream":     "#FEF9EF",
}


def _is_dark(hex_color: str) -> bool:
    """배경색이 어두우면 True"""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) < 89
    except Exception:
        return False


def _darken(hex_color: str, amt: int = 40) -> str:
    """hex 색상을 amt만큼 어둡게"""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{max(0, r-amt):02X}{max(0, g-amt):02X}{max(0, b-amt):02X}"
    except Exception:
        return hex_color


# ─── 공통 CSS (WeasyPrint 호환) ───────────────────────────────────────────
def _common_css(accent: str, bg: str) -> str:
    is_dark = _is_dark(bg)
    text_color = "#FFFFFF" if is_dark else "#1A1A1A"
    sub_color  = "#AABBCC" if is_dark else "#555555"
    card_bg    = "#1E2A3A" if is_dark else "#F0F2F5"
    return f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Malgun Gothic', 'AppleGothic', 'Noto Sans KR', 'NanumGothic', sans-serif;
  background:{bg};
  color:{text_color};
  font-size:13pt;
}}
.slide-page {{
  width:297mm; height:167mm;
  page-break-after:always;
  overflow:hidden;
  position:relative;
  background:{bg};
}}
.slide-page:last-child {{ page-break-after:auto; }}
.slide {{
  width:100%; height:100%;
  position:relative;
  overflow:hidden;
  display:flex;
  flex-direction:column;
}}
.accent-bar {{ background:{accent}; }}
.accent-color {{ color:{accent}; }}
.accent-bg {{ background:{accent}; }}
.text-main {{ color:{text_color}; }}
.text-sub  {{ color:{sub_color}; }}
.card-bg   {{ background:{card_bg}; }}
.gm-box {{
  background:{accent}; color:#fff;
  padding:8pt 14pt; font-size:11pt; font-weight:700;
  font-style:italic; border-radius:3pt; margin:8pt 0;
  line-height:1.4;
}}
.slide-num-badge {{
  display:inline-block; text-align:center;
  width:26pt; height:26pt; line-height:26pt;
  background:{accent}; color:#fff;
  font-weight:700; font-size:11pt; border-radius:3pt;
  flex-shrink:0;
}}
.page-num {{
  position:absolute; bottom:6pt; right:14pt;
  font-size:9pt; color:{sub_color};
}}
"""


# ─── 슬라이드 타입별 HTML 생성 함수 ───────────────────────────────────────

def _html_cover(slide: dict, palette: dict, interview_data: dict, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#002050"
    sub      = "#AABBCC" if is_dark else "#666666"
    title    = slide.get("title") or interview_data.get("proposalTitle") or "제안서"
    subtitle = interview_data.get("proposalSubtitle") or slide.get("governing_message", "")
    proposer = interview_data.get("proposerInfo", "UNIFLOW")
    today    = date.today().strftime("%Y.%m")
    dark_acc = _darken(accent, 30)

    subtitle_html = f'<div style="font-size:13pt;color:{sub};margin-bottom:20pt;">{subtitle}</div>' if subtitle else ""

    return f"""
<div style="position:relative;width:100%;height:167mm;background:{bg};overflow:hidden;">
  <!-- 우측 컬러 패널 -->
  <div style="position:absolute;top:0;right:0;width:100mm;height:167mm;background:{accent};"></div>
  <div style="position:absolute;top:0;right:99.5mm;width:1.5pt;height:167mm;background:{dark_acc};"></div>
  <!-- 상단 선 -->
  <div style="position:absolute;top:0;left:0;right:0;height:6pt;background:{accent};"></div>

  <!-- 좌측 콘텐츠 -->
  <div style="position:absolute;top:40pt;left:40pt;right:110mm;">
    <div style="font-size:28pt;font-weight:900;color:{text};line-height:1.25;margin-bottom:14pt;">{title}</div>
    {subtitle_html}
    <div style="width:180pt;height:2pt;background:{accent};margin-bottom:10pt;"></div>
    <div style="font-size:11pt;color:{sub};">{proposer}</div>
  </div>

  <!-- 우측 패널 내 정보 -->
  <div style="position:absolute;bottom:30pt;right:5mm;width:90mm;text-align:center;color:#fff;">
    <div style="font-size:15pt;font-weight:700;">{proposer.split('/')[-1].strip() if '/' in proposer else 'UNIFLOW'}</div>
    <div style="font-size:11pt;opacity:.7;margin-top:4pt;">{today}</div>
  </div>
</div>
"""


def _html_executive_summary(slide: dict, palette: dict, num: int, total: int) -> str:
    accent  = palette["accent"]
    bg      = palette["bg"]
    is_dark = _is_dark(bg)
    text    = "#FFFFFF" if is_dark else "#1A1A1A"
    card_bg = "#1E2A3A" if is_dark else "#F0F2F5"
    title   = slide.get("title", "핵심 요약")
    gm      = slide.get("governing_message", "")
    points  = slide.get("talking_points") or []
    if not points:
        body   = slide.get("body", "")
        points = [l.strip() for l in body.split("\n") if l.strip()][:3]
    if not points:
        points = ["핵심 내용 1", "핵심 내용 2", "핵심 내용 3"]
    points = points[:3]

    nums = ["①", "②", "③"]
    cards = ""
    for i, pt in enumerate(points):
        cards += f"""
        <div style="flex:1;background:{card_bg};border:1.5pt solid {accent};border-radius:6pt;padding:14pt 12pt;margin:0 4pt;">
          <div style="width:26pt;height:26pt;line-height:26pt;text-align:center;background:{accent};border-radius:50%;font-weight:700;font-size:13pt;color:#fff;margin-bottom:10pt;">{nums[i]}</div>
          <div style="font-size:11pt;color:{text};line-height:1.6;">{pt}</div>
        </div>"""

    gm_html = f'<div class="gm-box">{gm}</div>' if gm else ""

    return f"""
<div style="background:{bg};padding:26pt 36pt;height:167mm;position:relative;overflow:hidden;">
  <div style="display:flex;align-items:center;gap:8pt;margin-bottom:8pt;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:18pt;font-weight:800;color:{text};">{title}</div>
  </div>
  {gm_html}
  <div style="display:flex;margin-top:10pt;">{cards}</div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_content_slide(slide: dict, palette: dict, num: int, total: int) -> str:
    accent  = palette["accent"]
    bg      = palette["bg"]
    is_dark = _is_dark(bg)
    text    = "#FFFFFF" if is_dark else "#1A1A1A"
    sub     = "#AABBCC" if is_dark else "#555555"
    dark_acc = _darken(accent, 40)

    title  = slide.get("title", "")
    gm     = slide.get("governing_message", "")
    body   = slide.get("body", "")
    tp     = slide.get("talking_points") or []
    vs     = slide.get("visual_suggestion", "")

    body_lines = [l.strip() for l in body.split("\n") if l.strip()]
    bullets = "".join(
        f'<div style="margin-bottom:5pt;font-size:11pt;color:{text};line-height:1.6;">▸ {l}</div>'
        for l in body_lines[:8]
    )
    tags = "  ·  ".join(tp[:4]) if tp else ""
    tags_html = f'<div style="background:{dark_acc};padding:7pt 12pt;border-radius:4pt;font-size:10pt;color:#fff;margin-top:6pt;">{tags}</div>' if tags else ""
    gm_html = f'<div class="gm-box">{gm}</div>' if gm else f'<div style="height:3pt;background:{accent};border-radius:2pt;margin:3pt 0;"></div>'
    vs_html = f'<div style="position:absolute;bottom:16pt;right:4pt;font-size:10pt;color:rgba(255,255,255,0.65);font-style:italic;text-align:center;padding:0 6pt;">{vs[:50]}</div>' if vs else ""

    return f"""
<div style="background:{bg};display:flex;height:167mm;position:relative;overflow:hidden;">
  <!-- 좌측 65% -->
  <div style="width:65%;padding:26pt 28pt 26pt 36pt;display:flex;flex-direction:column;gap:7pt;overflow:hidden;">
    <div style="display:flex;align-items:center;gap:8pt;">
      <div class="slide-num-badge">{num}</div>
      <div style="font-size:17pt;font-weight:800;color:{text};">{title}</div>
    </div>
    {gm_html}
    <div style="overflow:hidden;">{bullets}</div>
    {tags_html}
  </div>
  <!-- 우측 35% 장식 -->
  <div style="width:35%;background:{accent};position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;">
    <div style="position:absolute;top:0;right:0;width:40%;height:100%;background:{dark_acc};"></div>
    <div style="font-size:80pt;font-weight:900;color:rgba(255,255,255,0.15);z-index:1;">{num:02d}</div>
    {vs_html}
  </div>
  <div class="page-num" style="color:rgba(255,255,255,0.6);">{num} / {total}</div>
</div>
"""


def _html_data_chart(slide: dict, palette: dict, num: int, total: int) -> str:
    """
    차트: CSS 막대 차트 (Chart.js 불필요, weasyprint 완전 호환)
    """
    accent  = palette["accent"]
    bg      = palette["bg"]
    is_dark = _is_dark(bg)
    text    = "#FFFFFF" if is_dark else "#1A1A1A"
    card_bg = "#1E2A3A" if is_dark else "#F0F2F5"

    title   = slide.get("title", "데이터 분석")
    gm      = slide.get("governing_message", "")
    body    = slide.get("body", "")
    tp      = slide.get("talking_points") or []

    # 수치 추출
    numbers = re.findall(r"(\d+(?:\.\d+)?)\s*%?", body)
    nums_f  = [float(n) for n in numbers[:5]]
    if len(nums_f) >= 2:
        labels = [f"지표{i+1}" for i in range(len(nums_f))]
        data   = nums_f
    else:
        labels = ["도입 전", "1개월", "3개월", "6개월", "1년"]
        data   = [100.0, 112.0, 128.0, 145.0, 168.0]

    max_val = max(data) if data else 1
    bar_w   = 100 // len(data)

    bars = ""
    for i, (label, val) in enumerate(zip(labels, data)):
        pct = int(val / max_val * 100)
        bars += f"""
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4pt;margin:0 3pt;">
          <div style="font-size:10pt;font-weight:700;color:{text};">{val:.0f}</div>
          <div style="width:100%;background:{accent};height:{max(pct, 5)}pt;border-radius:3pt 3pt 0 0;min-height:4pt;"></div>
          <div style="font-size:9pt;color:{text};text-align:center;">{label}</div>
        </div>"""

    interp    = tp[0] if tp else ""
    gm_html   = f'<div class="gm-box">{gm}</div>' if gm else ""
    interp_html = f'<div style="background:{accent};padding:9pt 14pt;border-radius:4pt;font-size:11pt;color:#fff;margin-top:8pt;">📌 {interp}</div>' if interp else ""

    return f"""
<div style="background:{bg};padding:26pt 36pt;height:167mm;position:relative;overflow:hidden;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:8pt;margin-bottom:7pt;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:17pt;font-weight:800;color:{text};">{title}</div>
  </div>
  {gm_html}
  <!-- CSS 막대 차트 -->
  <div style="flex:1;display:flex;align-items:flex-end;background:{card_bg};border-radius:6pt;padding:14pt 10pt 8pt;margin-top:8pt;">{bars}</div>
  {interp_html}
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_timeline(slide: dict, palette: dict, num: int, total: int) -> str:
    accent  = palette["accent"]
    bg      = palette["bg"]
    is_dark = _is_dark(bg)
    text    = "#FFFFFF" if is_dark else "#1A1A1A"
    title   = slide.get("title", "실행 계획")
    gm      = slide.get("governing_message", "")
    points  = slide.get("talking_points") or []
    if not points:
        body   = slide.get("body", "")
        points = [l.strip() for l in body.split("\n") if l.strip()][:5]
    if not points:
        points = ["Phase 1", "Phase 2", "Phase 3"]
    points = points[:5]

    steps = ""
    for i, pt in enumerate(points):
        above = i % 2 == 0
        pt_html = f'<div style="font-size:10pt;color:{text};text-align:center;margin-bottom:6pt;max-width:100pt;">{pt[:60]}</div>'
        steps += f"""
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;">
          {pt_html if above else '<div style="height:36pt;"></div>'}
          <div style="width:30pt;height:30pt;line-height:30pt;text-align:center;background:{accent};border-radius:50%;font-weight:700;font-size:12pt;color:#fff;flex-shrink:0;">{i+1}</div>
          {('<div style="height:36pt;"></div>' if above else pt_html)}
        </div>"""

    gm_html = f'<div class="gm-box">{gm}</div>' if gm else ""

    return f"""
<div style="background:{bg};padding:26pt 36pt;height:167mm;position:relative;overflow:hidden;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:8pt;margin-bottom:7pt;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:17pt;font-weight:800;color:{text};">{title}</div>
  </div>
  {gm_html}
  <div style="flex:1;display:flex;align-items:center;position:relative;margin-top:14pt;">
    <!-- 타임라인 가로선 -->
    <div style="position:absolute;top:50%;left:0;right:0;height:3pt;background:{accent};"></div>
    <div style="display:flex;width:100%;position:relative;">{steps}</div>
  </div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_comparison(slide: dict, palette: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    other_bg = "#222C3A" if is_dark else "#F0F2F5"
    title    = slide.get("title", "비교 분석")
    gm       = slide.get("governing_message", "")
    body     = slide.get("body", "")
    lines    = [l.strip() for l in body.split("\n") if l.strip()]
    mid      = len(lines) // 2
    left_l   = lines[:mid] if lines else ["기존 문제점들"]
    right_l  = lines[mid:] if lines else ["개선된 결과들"]

    left_items  = "".join(f'<div style="margin-bottom:5pt;font-size:11pt;color:{text};">▸ {l}</div>' for l in left_l[:5])
    right_items = "".join(f'<div style="margin-bottom:5pt;font-size:11pt;color:#fff;">✓ {l}</div>' for l in right_l[:5])
    gm_html = f'<div class="gm-box">{gm}</div>' if gm else ""

    return f"""
<div style="background:{bg};padding:26pt 36pt;height:167mm;position:relative;overflow:hidden;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:8pt;margin-bottom:7pt;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:17pt;font-weight:800;color:{text};">{title}</div>
  </div>
  {gm_html}
  <div style="display:flex;gap:12pt;flex:1;margin-top:8pt;">
    <div style="flex:1;background:{other_bg};border-radius:7pt;padding:14pt 18pt;">
      <div style="font-size:13pt;font-weight:700;color:{text};margin-bottom:10pt;">기존 방식</div>
      {left_items}
    </div>
    <div style="flex:1;background:{accent};border-radius:7pt;padding:14pt 18pt;">
      <div style="font-size:13pt;font-weight:700;color:#fff;margin-bottom:10pt;">UNIFLOW 적용 후 ✓</div>
      {right_items}
    </div>
  </div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_infographic(slide: dict, palette: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    other_bg = "#222C3A" if is_dark else "#F0F2F5"
    title    = slide.get("title", "주요 수치")
    gm       = slide.get("governing_message", "")
    tp       = slide.get("talking_points") or []
    body     = slide.get("body", "")

    numbers_info = []
    sources = tp[:4] if tp else [body]
    for src in sources[:4]:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(%|배|배율|점|만|억|천만|%p)?", src)
        if m:
            val   = m.group(1) + (m.group(2) or "")
            label = src.replace(m.group(0), "").strip("·: ") or src
            numbers_info.append((val, label[:20]))
        else:
            numbers_info.append(("—", src[:25]))
    if not numbers_info:
        numbers_info = [("15%", "수익률 향상"), ("70%", "시간 절감"), ("95%", "고객 만족")]

    cards = ""
    for i, (val, label) in enumerate(numbers_info[:4]):
        cbg = accent if i == 0 else other_bg
        ctc = "#fff" if i == 0 or is_dark else accent
        clc = "#fff" if i == 0 or is_dark else text
        cards += f"""
        <div style="flex:1;background:{cbg};border-radius:7pt;padding:18pt 12pt;text-align:center;margin:0 3pt;">
          <div style="font-size:42pt;font-weight:900;color:{ctc};line-height:1;">{val}</div>
          <div style="height:1.5pt;width:60%;background:{ctc};opacity:.5;margin:8pt auto;"></div>
          <div style="font-size:11pt;color:{clc};">{label}</div>
        </div>"""

    gm_html = f'<div class="gm-box">{gm}</div>' if gm else ""

    return f"""
<div style="background:{bg};padding:26pt 36pt;height:167mm;position:relative;overflow:hidden;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:8pt;margin-bottom:7pt;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:17pt;font-weight:800;color:{text};">{title}</div>
  </div>
  {gm_html}
  <div style="display:flex;flex:1;margin-top:10pt;">{cards}</div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_closing(slide: dict, palette: dict, interview_data: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    sub      = "#AABBCC" if is_dark else "#666666"
    dark_acc = _darken(accent, 40)

    closing_title = slide.get("title") or "감사합니다"
    gm       = slide.get("governing_message") or slide.get("body", "")
    proposer = interview_data.get("proposerInfo", "UNIFLOW")
    today    = date.today().strftime("%Y.%m")

    return f"""
<div style="background:{bg};display:flex;height:167mm;position:relative;overflow:hidden;">
  <!-- 좌측 컬러 패널 -->
  <div style="width:90mm;background:{accent};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12pt;position:relative;">
    <div style="position:absolute;top:0;right:0;width:2pt;height:100%;background:{dark_acc};"></div>
    <div style="font-size:26pt;font-weight:900;color:#fff;text-align:center;padding:0 14pt;">{closing_title}</div>
    <div style="height:2pt;width:80pt;background:rgba(255,255,255,.5);"></div>
    <div style="font-size:11pt;color:rgba(255,255,255,.7);">{today}</div>
  </div>
  <!-- 우측 콘텐츠 -->
  <div style="flex:1;padding:38pt 38pt 38pt 38pt;display:flex;flex-direction:column;gap:14pt;">
    <div>
      <div style="font-size:16pt;font-weight:700;color:{text};margin-bottom:6pt;">다음 단계</div>
      <div style="height:2pt;background:{accent};border-radius:2pt;margin-bottom:8pt;"></div>
      <div style="font-size:12pt;color:{text};line-height:1.7;">{gm or "다음 단계를 함께 논의해 보시겠습니까?"}</div>
    </div>
    <div style="margin-top:auto;">
      <div style="font-size:12pt;font-weight:700;color:{accent};margin-bottom:4pt;">📌 연락처</div>
      <div style="font-size:12pt;color:{text};line-height:1.7;">{proposer}</div>
    </div>
  </div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


# ─── 슬라이드 타입 디스패처 ─────────────────────────────────────────────────
def _dispatch_slide_html(slide: dict, palette: dict, interview_data: dict, num: int, total: int) -> str:
    t = str(slide.get("type", "")).lower()
    if t == "cover":
        return _html_cover(slide, palette, interview_data, total)
    elif t == "executive_summary":
        return _html_executive_summary(slide, palette, num, total)
    elif t == "data_chart":
        return _html_data_chart(slide, palette, num, total)
    elif t == "timeline":
        return _html_timeline(slide, palette, num, total)
    elif t == "comparison":
        return _html_comparison(slide, palette, num, total)
    elif t == "infographic":
        return _html_infographic(slide, palette, num, total)
    elif t == "closing":
        return _html_closing(slide, palette, interview_data, num, total)
    else:
        return _html_content_slide(slide, palette, num, total)


# ─── 전체 HTML 문서 빌드 ──────────────────────────────────────────────────
def _build_html(proposal: dict, interview_data: dict, palette: dict) -> str:
    slides = proposal.get("slides", [])
    total  = len(slides)
    css    = _common_css(palette["accent"], palette["bg"])

    slides_html = ""
    for slide_data in slides:
        num = int(slide_data.get("slide_number", 0))
        try:
            slides_html += f'<div class="slide-page">{_dispatch_slide_html(slide_data, palette, interview_data, num, total)}</div>'
        except Exception as e:
            logger.error(f"[PDF] 슬라이드 {num} HTML 생성 오류: {e}")
            slides_html += f"""
<div class="slide-page">
  <div style="background:{palette['bg']};padding:30pt 36pt;height:167mm;">
    <div style="font-size:16pt;font-weight:700;">{slide_data.get('title','슬라이드')}</div>
    <div style="font-size:11pt;margin-top:7pt;">{slide_data.get('body','')}</div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
{css}
@page {{
  size: 297mm 167mm;
  margin: 0;
}}
</style>
</head>
<body>
{slides_html}
</body>
</html>"""


# ─── html2pdf.app API PDF 변환 ───────────────────────────────────────────
def html_to_pdf(html_content: str) -> bytes:
    """
    html2pdf.app REST API로 HTML → PDF 변환.
    외부 렌더링 서버 사용 → Railway 환경 의존성 없음.
    환경변수 HTML2PDF_API_KEY 필요.
    """
    api_key = os.environ.get("HTML2PDF_API_KEY", "")
    if not api_key:
        logger.warning("[PDF] HTML2PDF_API_KEY 미설정 — PDF 생성 불가")
        raise RuntimeError("HTML2PDF_API_KEY 환경변수가 설정되지 않았습니다.")

    logger.info("[PDF] html2pdf.app API 호출 중...")
    response = requests.post(
        "https://api.html2pdf.app/v1/generate",
        json={
            "html": html_content,
            "apiKey": api_key,
            "landscape": True,
            "width": 1280,
            "height": 720,
            "margin": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            "printBackground": True,
        },
        timeout=60,  # 60초 타임아웃
    )
    response.raise_for_status()
    pdf_bytes = response.content
    logger.info(f"[PDF] html2pdf.app 변환 완료: {len(pdf_bytes)} bytes")
    return pdf_bytes


# ─── 메인 함수 ─────────────────────────────────────────────────────────────
def generate_pdf(interview_data: dict, ai_summary: Optional[str] = None) -> bytes:
    """
    interview_data + proposalJson → PDF bytes 반환.
    interview_data 키:
        proposalJson  : AI 생성 JSON 전체 (dict)
        style, bgColor, accentColor, font, proposalTitle, proposerInfo
    """
    # ── 팔레트 구성 ──────────────────────────────────────────────────────
    style_key    = str(interview_data.get("style", "mckinsey")).lower()
    style_accent = STYLE_ACCENT.get(style_key, "#1E6FD9")

    accent_raw = str(interview_data.get("accentColor", "")).strip()
    accent = accent_raw if re.match(r"^#[0-9A-Fa-f]{6}$", accent_raw) else style_accent

    bg_raw = str(interview_data.get("bgColor", "white")).strip()
    bg = BG_COLOR_MAP.get(bg_raw.lower(), "#FFFFFF")
    if bg_raw.startswith("#"):
        bg = bg_raw

    palette = {"accent": accent, "bg": bg}

    # ── proposalJson 추출 ─────────────────────────────────────────────
    proposal = interview_data.get("proposalJson")
    if proposal is None and ai_summary:
        try:
            m = re.search(r"\{[\s\S]*\}", ai_summary)
            if m:
                proposal = json.loads(m.group(0))
        except Exception:
            pass

    if not (proposal and isinstance(proposal.get("slides"), list) and proposal["slides"]):
        logger.warning("[PDF] proposalJson 없음, 기본 슬라이드 생성")
        proposal = {
            "title": interview_data.get("proposalTitle", "제안서"),
            "slides": [
                {"slide_number": 1, "type": "cover",   "title": interview_data.get("proposalTitle", "제안서")},
                {"slide_number": 2, "type": "content",  "title": "핵심 내용", "body": interview_data.get("coreContent", "")},
                {"slide_number": 3, "type": "closing",  "title": "감사합니다", "body": ""},
            ]
        }

    # proposalTitle 동기화
    if proposal.get("title") and not interview_data.get("proposalTitle"):
        interview_data["proposalTitle"] = proposal["title"]
    if proposal.get("subtitle"):
        interview_data["proposalSubtitle"] = proposal["subtitle"]

    # ── HTML 빌드 → PDF ─────────────────────────────────────────────────
    html_content = _build_html(proposal, interview_data, palette)
    logger.info(f"[PDF] HTML 생성 완료, 슬라이드 {len(proposal['slides'])}장")
    return html_to_pdf(html_content)
