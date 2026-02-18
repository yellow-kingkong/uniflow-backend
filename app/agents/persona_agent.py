"""
Persona Agent: 설문 응답을 기반으로 경영자 유형을 5가지로 분류
"""
from typing import Dict, Any
from openai import OpenAI
from app.config import get_settings

settings = get_settings()


class PersonaAgent:
    """경영자 유형 분류 에이전트"""
    
    # 5가지 페르소나 정의
    PERSONAS = {
        "불타는_성장가": {
            "trigger": "성장 욕구 높음 + 시스템 부재",
            "pain": "확장하고 싶은데 현재 구조가 발목 잡음",
            "tone": "위급성 70%, 기회 손실 강조",
            "metaphor": "엔진은 슈퍼카급인데 브레이크가 고장난 상태",
            "urgency_ratio": 0.7,
            "comfort_ratio": 0.3
        },
        "지친_1인_오케스트라": {
            "trigger": "대표가 모든 업무 처리 + 피로도 높음",
            "pain": "나 없으면 회사가 멈춤",
            "tone": "위안 60%, 해방감 강조",
            "metaphor": "훌륭한 지휘자가 악기까지 연주하는 중",
            "urgency_ratio": 0.4,
            "comfort_ratio": 0.6
        },
        "효율_덕후": {
            "trigger": "안정적 운영 + 최적화 욕구",
            "pain": "더 잘할 수 있는데 방법을 모름",
            "tone": "데이터 중심, 구체적 수치 제시",
            "metaphor": "F1 레이서가 경차를 모는 느낌",
            "urgency_ratio": 0.5,
            "comfort_ratio": 0.5
        },
        "위기_감지형": {
            "trigger": "경쟁 위협 인식 + 변화 필요성 자각",
            "pain": "뒤처지고 있다는 불안감",
            "tone": "위급성 80%, FOMO 자극",
            "metaphor": "경주 중인데 다른 팀은 이미 피트스톱 끝냄",
            "urgency_ratio": 0.8,
            "comfort_ratio": 0.2
        },
        "신중_탐색형": {
            "trigger": "관심은 있으나 확신 부족",
            "pain": "투자 대비 효과 확신 못함",
            "tone": "교육 중심, 사례 제시",
            "metaphor": "좋은 약인 건 아는데 부작용이 걱정",
            "urgency_ratio": 0.4,
            "comfort_ratio": 0.6
        }
    }
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def classify(self, survey_data: Dict[str, Any]) -> Dict[str, Any]:
        """설문 데이터를 기반으로 페르소나 분류"""
        
        prompt = f"""
당신은 비즈니스 심리 분석 전문가입니다.
아래 설문 응답을 분석하여 경영자의 유형을 정확히 분류하세요.

# 설문 응답 데이터
{survey_data}

# 5가지 페르소나 유형
1. 불타는_성장가: 성장 욕구가 높지만 시스템 부재로 고통
2. 지친_1인_오케스트라: 모든 업무를 혼자 처리하며 피로도 높음
3. 효율_덕후: 안정적이지만 최적화에 대한 강한 욕구
4. 위기_감지형: 경쟁 위협을 인식하고 변화 필요성 자각
5. 신중_탐색형: 관심은 있으나 확신이 부족함

# 분석 기준
- 현재 고민하는 문제의 본질
- 비즈니스 성장 단계
- 의사결정 패턴
- 감정적 상태

응답은 반드시 JSON 형식으로 제공하세요:
{{
    "persona_type": "페르소나_이름",
    "confidence": 0.85,
    "reasoning": "분류 근거 설명"
}}
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "당신은 비즈니스 심리 분석 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        
        # 페르소나 메타데이터 추가
        persona_type = result["persona_type"]
        result["metadata"] = self.PERSONAS.get(persona_type, {})
        
        return result
