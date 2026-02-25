"""
slide_generator.py — GPT JSON → HTML → Puppeteer PDF 변환
- slde_number, type, title, governing_message, body, talking_points, visual_suggestion
- 슬라이드 크기: 1280×720px (16:9)
- 한국어: Noto Sans KR → 맑은고딕 폴백
- 차트: Chart.js CDN (데이터 없으면 샘플)
- pyppeteer로 HTML → PDF 변환
"""

import asyncio
import io
import json
import logging
import os
import re
import tempfile
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
        return (0.299 * r + 0.587 * g + 0.114 * b) < 89  # 0~255 기준 89 ≈ 0.35 * 255
    except Exception:
        return False


# ─── 공통 CSS ─────────────────────────────────────────────────────────────
def _common_css(accent: str, bg: str) -> str:
    is_dark = _is_dark(bg)
    text_color   = "#FFFFFF" if is_dark else "#1A1A1A"
    sub_color    = "#AABBCC" if is_dark else "#555555"
    card_bg      = "#1E2A3A" if is_dark else "#F0F2F5"
    gm_color     = "#FFFFFF"
    return f"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width:1280px; height:720px; overflow:hidden;
  font-family: 'Noto Sans KR', 'Malgun Gothic', '맑은 고딕', sans-serif;
  background:{bg};
  color:{text_color};
}}
.slide {{
  width:1280px; height:720px; position:relative; overflow:hidden;
  display:flex; flex-direction:column;
}}
.accent-bar {{ background:{accent}; }}
.accent-color {{ color:{accent}; }}
.accent-bg {{ background:{accent}; }}
.text-main {{ color:{text_color}; }}
.text-sub  {{ color:{sub_color}; }}
.card-bg   {{ background:{card_bg}; }}
.gm-box {{
  background:{accent}; color:{gm_color};
  padding:10px 18px; font-size:15px; font-weight:700;
  font-style:italic; border-radius:4px; margin:10px 0;
  line-height:1.4;
}}
.slide-num-badge {{
  display:inline-flex; align-items:center; justify-content:center;
  width:34px; height:34px; background:{accent}; color:#fff;
  font-weight:700; font-size:13px; border-radius:4px;
  flex-shrink:0;
}}
.page-num {{
  position:absolute; bottom:10px; right:20px;
  font-size:11px; color:{sub_color};
}}
"""


# ─── 슬라이드 타입별 HTML 생성 함수 ───────────────────────────────────────

def _html_cover(slide: dict, palette: dict, interview_data: dict, total: int) -> str:
    accent = palette["accent"]
    bg     = palette["bg"]
    is_dark = _is_dark(bg)
    text   = "#FFFFFF" if is_dark else "#002050"
    sub    = "#AABBCC" if is_dark else "#666666"
    title  = slide.get("title") or interview_data.get("proposalTitle") or "제안서"
    subtitle = interview_data.get("proposalSubtitle") or slide.get("governing_message","")
    proposer = interview_data.get("proposerInfo","UNIFLOW")
    today  = date.today().strftime("%Y.%m")

    # accent accent hex → slightly darker
    def darken(h: str, amt=30) -> str:
        try:
            h = h.lstrip("#")
            r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"#{max(0,r-amt):02X}{max(0,g-amt):02X}{max(0,b-amt):02X}"
        except Exception:
            return h
    dark_accent = darken(accent)

    return f"""
<div class="slide" style="background:{bg};">
  <!-- 우측 컬러 패널 -->
  <div style="position:absolute;top:0;right:0;width:420px;height:720px;background:{accent};"></div>
  <div style="position:absolute;top:0;right:418px;width:3px;height:720px;background:{dark_accent};"></div>
  <!-- 상단 선 -->
  <div style="position:absolute;top:0;left:0;right:0;height:8px;background:{accent};"></div>

  <!-- 좌측 메인 콘텐츠 -->
  <div style="position:absolute;top:60px;left:60px;right:440px;">
    <div style="font-size:40px;font-weight:900;color:{text};line-height:1.25;margin-bottom:20px;">{title}</div>
    {f'<div style="font-size:17px;color:{sub};margin-bottom:30px;">{subtitle}</div>' if subtitle else ''}
    <div style="width:260px;height:2px;background:{accent};margin-bottom:16px;"></div>
    <div style="font-size:14px;color:{sub};">{proposer}</div>
  </div>

  <!-- 우측 패널 내 날짜·회사 -->
  <div style="position:absolute;bottom:40px;right:20px;width:380px;text-align:center;color:#fff;">
    <div style="font-size:20px;font-weight:700;">{proposer.split('/')[-1].strip() if '/' in proposer else 'UNIFLOW'}</div>
    <div style="font-size:13px;opacity:.7;margin-top:6px;">{today}</div>
  </div>
</div>
"""


def _html_executive_summary(slide: dict, palette: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    card_bg  = "#1E2A3A" if is_dark else "#F0F2F5"
    title    = slide.get("title","핵심 요약")
    gm       = slide.get("governing_message","")
    points   = slide.get("talking_points") or []
    if not points:
        body  = slide.get("body","")
        points = [l.strip() for l in body.split("\n") if l.strip()][:3]
    if not points:
        points = ["핵심 내용 1","핵심 내용 2","핵심 내용 3"]
    points = points[:3]

    cards_html = ""
    nums = ["①","②","③"]
    for i, pt in enumerate(points):
        cards_html += f"""
        <div style="flex:1;background:{card_bg};border:1.5px solid {accent};border-radius:10px;padding:22px 18px;display:flex;flex-direction:column;gap:14px;">
          <div style="width:36px;height:36px;background:{accent};border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#fff;">{nums[i]}</div>
          <div style="font-size:13px;color:{text};line-height:1.6;">{pt}</div>
        </div>"""

    return f"""
<div class="slide" style="background:{bg};padding:36px 50px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:24px;font-weight:800;color:{text};">{title}</div>
  </div>
  {f'<div class="gm-box">{gm}</div>' if gm else ''}
  <div style="display:flex;gap:16px;margin-top:16px;flex:1;">{cards_html}</div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_content_slide(slide: dict, palette: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    sub      = "#AABBCC" if is_dark else "#555555"
    def darken(h,a=40):
        try:
            h2=h.lstrip("#"); r,g,b=int(h2[0:2],16),int(h2[2:4],16),int(h2[4:6],16)
            return f"#{max(0,r-a):02X}{max(0,g-a):02X}{max(0,b-a):02X}"
        except: return h
    title    = slide.get("title","")
    gm       = slide.get("governing_message","")
    body     = slide.get("body","")
    tp       = slide.get("talking_points") or []
    vs       = slide.get("visual_suggestion","")
    body_lines = [l.strip() for l in body.split("\n") if l.strip()]
    bullets  = "".join(f'<li style="margin-bottom:8px;font-size:13px;color:{text};line-height:1.6;">▸ {l}</li>' for l in body_lines[:8])
    tags     = "  ·  ".join(tp[:4]) if tp else ""

    return f"""
<div class="slide" style="background:{bg};display:flex;">
  <!-- 좌측 65% -->
  <div style="width:65%;padding:36px 40px 36px 50px;display:flex;flex-direction:column;gap:10px;">
    <div style="display:flex;align-items:center;gap:12px;">
      <div class="slide-num-badge">{num}</div>
      <div style="font-size:22px;font-weight:800;color:{text};">{title}</div>
    </div>
    {f'<div class="gm-box">{gm}</div>' if gm else f'<div style="height:4px;background:{accent};border-radius:2px;margin:4px 0;"></div>'}
    <ul style="list-style:none;flex:1;overflow:hidden;">{bullets}</ul>
    {f'<div style="background:{darken(accent,10)};padding:10px 16px;border-radius:6px;font-size:12px;color:#fff;margin-top:6px;">{tags}</div>' if tags else ''}
  </div>
  <!-- 우측 35% 장식 -->
  <div style="width:35%;background:{accent};position:relative;display:flex;align-items:center;justify-content:center;">
    <div style="position:absolute;top:0;right:0;width:40%;height:100%;background:{darken(accent,40)};"></div>
    <div style="font-size:100px;font-weight:900;color:rgba(255,255,255,0.15);z-index:1;">{num:02d}</div>
    {f'<div style="position:absolute;bottom:20px;left:10px;right:0;font-size:11px;color:rgba(255,255,255,0.6);font-style:italic;text-align:center;padding:0 8px;">{vs[:50]}</div>' if vs else ''}
  </div>
  <div class="page-num" style="color:rgba(255,255,255,0.6);">{num} / {total}</div>
</div>
"""


def _html_data_chart(slide: dict, palette: dict, num: int, total: int) -> str:
    accent  = palette["accent"]
    bg      = palette["bg"]
    is_dark = _is_dark(bg)
    text    = "#FFFFFF" if is_dark else "#1A1A1A"
    title   = slide.get("title","데이터 분석")
    gm      = slide.get("governing_message","")
    body    = slide.get("body","")
    tp      = slide.get("talking_points") or []

    # 차트 데이터 추출
    numbers = re.findall(r"(\d+(?:\.\d+)?)\s*%?", body)
    nums_f  = [float(n) for n in numbers[:5]]
    if len(nums_f) >= 2:
        labels = [f"지표{i+1}" for i in range(len(nums_f))]
        data   = nums_f
    else:
        labels = ["도입 전","1개월 후","3개월 후","6개월 후","1년 후"]
        data   = [100, 112, 128, 145, 168]

    labels_js = json.dumps(labels, ensure_ascii=False)
    data_js   = json.dumps(data)
    interp    = tp[0] if tp else ""

    return f"""
<div class="slide" style="background:{bg};padding:36px 50px;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:22px;font-weight:800;color:{text};">{title}</div>
  </div>
  {f'<div class="gm-box">{gm}</div>' if gm else ''}
  <div style="flex:1;position:relative;margin:10px 0;">
    <canvas id="chart{num}" style="max-height:380px;"></canvas>
  </div>
  {f'<div style="background:{accent};padding:12px 18px;border-radius:6px;font-size:13px;color:#fff;margin-top:8px;">📌 {interp}</div>' if interp else ''}
  <div class="page-num">{num} / {total}</div>
</div>
<script>
(function(){{
  var ctx = document.getElementById('chart{num}').getContext('2d');
  new Chart(ctx, {{
    type:'bar',
    data:{{
      labels:{labels_js},
      datasets:[{{
        label:'성과 지표',
        data:{data_js},
        backgroundColor:'{accent}CC',
        borderColor:'{accent}',
        borderWidth:2,
        borderRadius:6,
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{y:{{beginAtZero:true}}}}
    }}
  }});
}})();
</script>
"""


def _html_timeline(slide: dict, palette: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    sub      = "#AABBCC" if is_dark else "#555555"
    title    = slide.get("title","실행 계획")
    gm       = slide.get("governing_message","")
    points   = slide.get("talking_points") or []
    if not points:
        body   = slide.get("body","")
        points = [l.strip() for l in body.split("\n") if l.strip()][:5]
    if not points:
        points = ["Phase 1","Phase 2","Phase 3"]
    points = points[:5]
    n = len(points)
    step_w = 100 / n

    steps_html = ""
    for i, pt in enumerate(points):
        above = i % 2 == 0
        steps_html += f"""
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;position:relative;">
          {f'<div style="font-size:12px;color:{text};text-align:center;margin-bottom:10px;max-width:150px;">{pt[:60]}</div>' if above else '<div style="height:50px;"></div>'}
          <div style="width:36px;height:36px;background:{accent};border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;color:#fff;z-index:2;flex-shrink:0;">{i+1}</div>
          {f'<div style="height:50px;"></div>' if above else f'<div style="font-size:12px;color:{text};text-align:center;margin-top:10px;max-width:150px;">{pt[:60]}</div>'}
        </div>"""

    return f"""
<div class="slide" style="background:{bg};padding:36px 50px;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:22px;font-weight:800;color:{text};">{title}</div>
  </div>
  {f'<div class="gm-box">{gm}</div>' if gm else ''}
  <div style="flex:1;display:flex;align-items:center;position:relative;margin-top:20px;">
    <!-- 가로 라인 -->
    <div style="position:absolute;top:50%;left:0;right:0;height:4px;background:{accent};transform:translateY(-50%);z-index:1;"></div>
    <div style="display:flex;width:100%;position:relative;z-index:2;">{steps_html}</div>
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
    title    = slide.get("title","비교 분석")
    gm       = slide.get("governing_message","")
    body     = slide.get("body","")
    lines    = [l.strip() for l in body.split("\n") if l.strip()]
    mid      = len(lines) // 2
    left_l   = lines[:mid] if lines else ["기존 문제점들"]
    right_l  = lines[mid:] if lines else ["개선된 결과들"]

    left_items  = "".join(f'<li style="margin-bottom:8px;font-size:13px;color:{text};list-style:none;">▸ {l}</li>' for l in left_l[:5])
    right_items = "".join(f'<li style="margin-bottom:8px;font-size:13px;color:#fff;list-style:none;">✓ {l}</li>' for l in right_l[:5])

    return f"""
<div class="slide" style="background:{bg};padding:36px 50px;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:22px;font-weight:800;color:{text};">{title}</div>
  </div>
  {f'<div class="gm-box">{gm}</div>' if gm else ''}
  <div style="display:flex;gap:16px;flex:1;margin-top:12px;">
    <div style="flex:1;background:{other_bg};border-radius:10px;padding:20px 24px;">
      <div style="font-size:16px;font-weight:700;color:{text};margin-bottom:14px;">기존 방식</div>
      <ul>{left_items}</ul>
    </div>
    <div style="flex:1;background:{accent};border-radius:10px;padding:20px 24px;">
      <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">UNIFLOW 적용 후 ✓</div>
      <ul>{right_items}</ul>
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
    title    = slide.get("title","주요 수치")
    gm       = slide.get("governing_message","")
    tp       = slide.get("talking_points") or []
    body     = slide.get("body","")

    # 수치 추출
    numbers_info = []
    sources = tp[:4] if tp else [body]
    for src in sources[:4]:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(%|배|배율|점|만|억|천만|%p)?", src)
        if m:
            val   = m.group(1) + (m.group(2) or "")
            label = src.replace(m.group(0),"").strip("·: ") or src
            numbers_info.append((val, label[:20]))
        else:
            numbers_info.append(("—", src[:25]))
    if not numbers_info:
        numbers_info = [("15%","수익률 향상"),("70%","시간 절감"),("95%","고객 만족")]

    n = min(len(numbers_info), 4)
    cards = ""
    for i, (val, label) in enumerate(numbers_info[:4]):
        cbg = accent if i == 0 else other_bg
        ctc = "#fff" if i == 0 or is_dark else accent
        clc = "#fff" if i == 0 or is_dark else text
        cards += f"""
        <div style="flex:1;background:{cbg};border-radius:10px;padding:24px 16px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;">
          <div style="font-size:54px;font-weight:900;color:{ctc};line-height:1;">{val}</div>
          <div style="height:2px;width:60%;background:{ctc};opacity:.5;"></div>
          <div style="font-size:13px;color:{clc};text-align:center;">{label}</div>
        </div>"""

    return f"""
<div class="slide" style="background:{bg};padding:36px 50px;display:flex;flex-direction:column;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
    <div class="slide-num-badge">{num}</div>
    <div style="font-size:22px;font-weight:800;color:{text};">{title}</div>
  </div>
  {f'<div class="gm-box">{gm}</div>' if gm else ''}
  <div style="display:flex;gap:16px;flex:1;margin-top:14px;">{cards}</div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


def _html_closing(slide: dict, palette: dict, interview_data: dict, num: int, total: int) -> str:
    accent   = palette["accent"]
    bg       = palette["bg"]
    is_dark  = _is_dark(bg)
    text     = "#FFFFFF" if is_dark else "#1A1A1A"
    sub      = "#AABBCC" if is_dark else "#666666"
    def darken(h,a=40):
        try:
            h2=h.lstrip("#"); r,g,b=int(h2[0:2],16),int(h2[2:4],16),int(h2[4:6],16)
            return f"#{max(0,r-a):02X}{max(0,g-a):02X}{max(0,b-a):02X}"
        except: return h
    closing_title = slide.get("title") or "감사합니다"
    gm    = slide.get("governing_message") or slide.get("body","")
    proposer = interview_data.get("proposerInfo","UNIFLOW")
    today = date.today().strftime("%Y.%m")

    return f"""
<div class="slide" style="background:{bg};display:flex;">
  <!-- 좌측 컬러 패널 -->
  <div style="width:380px;background:{accent};display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;position:relative;">
    <div style="position:absolute;top:0;right:0;width:3px;height:100%;background:{darken(accent)};"></div>
    <div style="font-size:34px;font-weight:900;color:#fff;text-align:center;padding:0 20px;">{closing_title}</div>
    <div style="height:2px;width:120px;background:rgba(255,255,255,0.5);"></div>
    <div style="font-size:13px;color:rgba(255,255,255,0.7);">{today}</div>
  </div>
  <!-- 우측 콘텐츠 -->
  <div style="flex:1;padding:50px 50px 50px 50px;display:flex;flex-direction:column;gap:20px;">
    <div>
      <div style="font-size:20px;font-weight:700;color:{text};margin-bottom:8px;">다음 단계</div>
      <div style="height:3px;background:{accent};border-radius:2px;margin-bottom:12px;"></div>
      <div style="font-size:14px;color:{text};line-height:1.7;">{gm or "다음 단계를 함께 논의해 보시겠습니까?"}</div>
    </div>
    <div style="margin-top:auto;">
      <div style="font-size:14px;font-weight:700;color:{accent};margin-bottom:6px;">📌 연락처</div>
      <div style="font-size:14px;color:{text};line-height:1.7;">{proposer}</div>
    </div>
  </div>
  <div class="page-num">{num} / {total}</div>
</div>
"""


# ─── 슬라이드 타입 디스패처 ─────────────────────────────────────────────────
def _dispatch_slide_html(slide: dict, palette: dict, interview_data: dict, num: int, total: int) -> str:
    t = str(slide.get("type","")).lower()
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
            slides_html += f"""
            <div class="slide-page">
              {_dispatch_slide_html(slide_data, palette, interview_data, num, total)}
            </div>"""
        except Exception as e:
            logger.error(f"[PDF] 슬라이드 {num} HTML 생성 오류: {e}")
            slides_html += f"""
            <div class="slide-page">
              <div class="slide" style="background:{palette['bg']};padding:40px 50px;">
                <div style="font-size:20px;font-weight:700;">{slide_data.get('title','슬라이드')}</div>
                <div style="font-size:13px;margin-top:10px;">{slide_data.get('body','')}</div>
              </div>
            </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
{css}
.slide-page {{
  width:1280px; height:720px; page-break-after:always; overflow:hidden;
  position:relative;
}}
.slide-page:last-child {{ page-break-after:auto; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
{slides_html}
</body>
</html>"""


# ─── Puppeteer(pyppeteer) PDF 변환 ──────────────────────────────────────────
async def _html_to_pdf_async(html_content: str) -> bytes:
    """pyppeteer로 HTML → PDF 변환 (비동기)

    수정 내역:
    - launch args: --single-process 방식으로 Railway 안정화
    - setContent 사용 (파일 URL 불필요 → 경로 이슈 제거)
    - page.pdf(): width/height 직접 지정 1280×720px (landscape 옵션 제거)
    - asyncio.wait_for: 30초 타임아웃으로 무한 로딩 방지
    """
    try:
        from pyppeteer import launch
    except ImportError:
        raise RuntimeError("pyppeteer가 설치되지 않았습니다. pip install pyppeteer")

    async def _run() -> bytes:
        browser = await launch({
            "executablePath": os.environ.get(
                "PUPPETEER_EXECUTABLE_PATH", "/usr/bin/chromium"),
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-zygote",
                "--single-process",       # Railway 컨테이너 안정화 핵심
                "--disable-extensions",
            ],
        })
        try:
            page = await browser.newPage()
            await page.setViewport({"width": 1280, "height": 720})
            # setContent: 파일 URL 대신 HTML 직접 주입 (경로 이슈 없음)
            await page.setContent(html_content, {
                "waitUntil": "domcontentloaded",
                "timeout": 30000,
            })
            # Chart.js 등 JS 렌더링 최소 대기
            await asyncio.sleep(0.5)

            # ──── PDF 출력: 1280×720 고정 (16:9), landscape 옵션 제거 ────
            pdf_bytes = await page.pdf({
                "width": "1280px",
                "height": "720px",
                "printBackground": True,
                "margin": {
                    "top": "0", "bottom": "0",
                    "left": "0", "right": "0",
                },
            })
            return pdf_bytes
        finally:
            await browser.close()

    # 30초 타임아웃: 초과 시 즉시 TimeoutError → caller에서 failed 처리
    try:
        return await asyncio.wait_for(_run(), timeout=30)
    except asyncio.TimeoutError:
        logger.error("[PDF] 30초 타임아웃 — PDF 생성 실패")
        raise RuntimeError("PDF 생성 타임아웃 (30초 초과)")



def html_to_pdf(html_content: str) -> bytes:
    """
    동기 래퍼: _html_to_pdf_async → 동기 결과 반환.

    ⚠️ flow_deck.py에서 run_in_executor()로 별도 스레드에 실행됨.
    스레드 내부에는 실행 중인 이벤트 루프가 없으므로 asyncio.run() 직접 사용.
    (nest_asyncio 필요 없음. 이전 nest_asyncio 방식은 uvicorn 루프와 충돌 가능)
    """
    return asyncio.run(_html_to_pdf_async(html_content))


# ─── 메인 함수 ─────────────────────────────────────────────────────────────
def generate_pdf(interview_data: dict, ai_summary: Optional[str] = None) -> bytes:
    """
    interview_data + proposalJson → PDF bytes 반환.
    interview_data 키:
        proposalJson  : AI 생성 JSON 전체 (dict)
        style, bgColor, accentColor, font, proposalTitle, proposerInfo
    """
    # ── 팔레트 구성 ──────────────────────────────────────────────────────
    style_key = str(interview_data.get("style","mckinsey")).lower()
    style_accent = STYLE_ACCENT.get(style_key, "#1E6FD9")

    accent_raw = str(interview_data.get("accentColor","")).strip()
    accent = accent_raw if re.match(r"^#[0-9A-Fa-f]{6}$", accent_raw) else style_accent

    bg_raw = str(interview_data.get("bgColor","white")).strip()
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
        # 레거시 폴백 (최소 구조)
        logger.warning("[PDF] proposalJson 없음, 기본 슬라이드 생성")
        proposal = {
            "title": interview_data.get("proposalTitle","제안서"),
            "slides": [
                {"slide_number":1,"type":"cover","title":interview_data.get("proposalTitle","제안서")},
                {"slide_number":2,"type":"content","title":"핵심 내용","body":interview_data.get("coreContent","")},
                {"slide_number":3,"type":"closing","title":"감사합니다","body":""},
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
