"""
Analysis Agent: 설문 응답을 분석하여 병목 포인트와 손실을 정량화
"""
from typing import Dict, Any, List
from openai import OpenAI
from app.config import get_settings

settings = get_settings()


class AnalysisAgent:
    """응답 데이터 분석 에이전트"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def identify_bottlenecks(self, survey_data: Dict[str, Any]) -> Dict[str, Any]:
        """병목 포인트 식별 및 손실 정량화"""
        
        prompt = f"""
당신은 20년 경력의 비즈니스 컨설턴트입니다.
아래 설문 응답을 분석하여 비즈니스의 핵심 병목 포인트를 찾아내세요.

# 설문 응답 데이터
{survey_data}

# 분석 프레임워크
1. 병목 포인트 식별 (Top 3)
   - 시스템 병목: 자동화되지 않은 수동 작업
   - 인력 병목: 특정 인력에 과도하게 의존
   - 커뮤니케이션 병목: 정보 전달 지연 및 누락

2. 손실 정량화
   - 시간 손실: 월 몇 시간이 낭비되는가?
   - 기회 손실: 월 얼마의 매출 기회를 놓치는가?
   - 성장 지연: 몇 개월의 성장이 지연되는가?

3. 긴급도 평가 (1-10점)
   - 재무적 리스크
   - 경쟁력 하락 속도
   - 팀 소진도

# 출력 형식 (JSON)
{{
    "bottlenecks": [
        {{
            "category": "시스템|인력|커뮤니케이션",
            "issue": "구체적인 문제 설명",
            "impact_hours": 120,
            "impact_cost": 3600000,
            "urgency": 8,
            "description": "상세 설명"
        }}
    ],
    "total_monthly_loss": {{
        "time": 280,
        "cost": 8400000
    }},
    "growth_delay_months": 6,
    "overall_urgency": 8
}}

반드시 JSON 형식으로만 응답하세요.
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 비즈니스 병목 분석 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.4
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        
        return result
    
    def calculate_benchmark_gap(self, survey_data: Dict[str, Any], industry: str) -> Dict[str, Any]:
        """업종 상위 10%와의 격차 분석"""
        
        prompt = f"""
{industry} 업종의 상위 10% 기업과 현재 응답자의 격차를 분석하세요.

# 현재 상태
{survey_data}

# 비교 항목
- 업무 자동화율
- 데이터 통합도
- 의사결정 속도

JSON 형식으로 응답:
{{
    "current": {{
        "automation_rate": 23,
        "data_integration": 31,
        "decision_speed_days": 3.2
    }},
    "top_10_percent": {{
        "automation_rate": 87,
        "data_integration": 94,
        "decision_speed_days": 0.5
    }},
    "gap_analysis": "격차 분석 텍스트"
}}
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 업종 벤치마킹 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        import json
        return json.loads(response.choices[0].message.content)
