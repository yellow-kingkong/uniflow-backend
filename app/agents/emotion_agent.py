"""
Emotion Agent: 감성 톤 조절 (위급성 + 위안)
"""
from typing import Dict, Any
from openai import OpenAI
from app.config import get_settings

settings = get_settings()


class EmotionAgent:
    """감성 톤 조절 에이전트"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def generate_narrative(
        self,
        bottlenecks: Dict[str, Any],
        persona: Dict[str, Any],
        user_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        '혈관이 막힌 거인' 메타포를 활용한 감성적 내러티브 생성
        
        Args:
            bottlenecks: 병목 포인트 분석 결과
            persona: 페르소나 분류 결과
            user_data: 사용자 기본 정보
        
        Returns:
            각 페이지별 내러티브 텍스트
        """
        
        # 페르소나별 톤 비율
        persona_metadata = persona.get("metadata", {})
        urgency_ratio = persona_metadata.get("urgency_ratio", 0.6)
        comfort_ratio = persona_metadata.get("comfort_ratio", 0.4)
        metaphor = persona_metadata.get("metaphor", "혈관이 막힌 거인")
        
        prompt = f"""
당신은 20년 경력의 비즈니스 심리학자이자 스토리텔러입니다.

# 역할
- 대표님의 고통을 공감하면서도 희망을 주는 전문가
- "혈관이 막힌 거인" 메타포를 일관되게 사용
- 위급성 {urgency_ratio*100}% : 위안 {comfort_ratio*100}% 비율 유지

# 입력 데이터
## 사용자 정보
{user_data}

## 병목 포인트
{bottlenecks}

## 페르소나
{persona}

# 표현 가이드

[위급성 표현 예시]
✅ "지금 이 순간에도 {bottlenecks['total_monthly_loss']['cost']//30//24}만원이 시간당 새고 있습니다"
✅ "이 혈관이 6개월 더 막혀있으면, 성장 기회를 완전히 놓칩니다"

[위안 표현 예시]
✅ "이미 대표님은 거인입니다. 단지 혈관이 막혀있을 뿐."
✅ "이 문제는 3개월이면 해결 가능한 수준입니다"
✅ "실제로 비슷한 상황의 업체는 2개월 만에 매출 30% 증가했습니다"

# 문장 구조 템플릿
1. 공감형: "대표님의 [상황]은 충분히 [감정]하실 만합니다"
2. 충격형: "현재 [구체적 손실]이 발생 중입니다"
3. 희망형: "하지만 [해결책]만 실행하면, [구체적 결과]를 얻을 수 있습니다"

# 출력 형식 (JSON)
{{
    "page1_recognition": "공감 - 당신은 이미 거인 (3-4문장)",
    "page2_diagnosis": "진단 - 막힌 혈관 발견 (병목 3개 설명)",
    "page3_shock": "충격 - 새고 있는 가치 시각화 (정량적 손실)",
    "page4_benchmark": "벤치마크 - 다른 거인들은? (격차 설명)",
    "page5_vision": "시뮬레이션 - 혈관을 뚫으면? (Before/After)",
    "page6_roadmap": "로드맵 - 혈관 뚫기 3단계",
    "page7_testimonial": "증언 - 혈관 뚫은 다른 거인들",
    "page8_warning": "위험 - 계속 막아두면?",
    "page9_proposal": "제안 - 함께 뚫겠습니다",
    "page10_closing": "마무리 - 거인은 다시 일어섭니다"
}}

모든 텍스트는 반드시 '대표님'으로 호칭하고, {metaphor} 메타포를 활용하세요.
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 비즈니스 심리학자이자 감성 스토리텔러입니다."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        import json
        narrative = json.loads(response.choices[0].message.content)
        
        return narrative
