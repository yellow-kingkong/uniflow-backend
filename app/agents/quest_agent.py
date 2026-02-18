"""
Quest Agent: VIP의 6대 균형 지표를 기반으로 성장 미션 질문 생성 및 답변 평가
"""
from typing import Dict, Any, List
from openai import OpenAI
import json
from app.config import get_settings

settings = get_settings()

class QuestAgent:
    """비즈니스 멘토 관점의 퀘스트 관리 에이전트"""
    
    CATEGORY_CONTEXTS = {
        "future_safety_net": "불안함을 느끼고 있습니다. 밤에 잠들기 전, '내일 갑자기 수입이 끊기면?'이라는 생각이 스쳐 지나갈 때가 있습니다.",
        "emotional_anchor": "정서적으로 흔들리고 있습니다. '나만 힘든 건가?' 가끔 이런 생각에 지칠 때가 있습니다.",
        "time_mastery": "시간에 쫓기고 있습니다. '언제쯤 여유가 생길까?' 하루하루가 바쁘게만 느껴집니다.",
        "body_signals": "신체적으로 지쳐있습니다. '이렇게 계속 달려도 괜찮을까?' 몸이 보내는 신호를 놓치고 있진 않은지 걱정됩니다.",
        "relationship_power": "인맥 관리가 부족합니다. '내 편이 되어줄 사람이 있을까?' 때론 혼자인 것 같아 외롭습니다.",
        "system_leverage": "같은 일을 반복하고 있습니다. '이걸 언제까지 손으로 해야 하나?' 더 효율적인 방법이 있을 것 같은데 막막합니다."
    }

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_questions(self, vip_name: str, category: str, score: int) -> Dict[str, Any]:
        """퀘스트별 맞춤형 체크리스트 생성"""
        
        emotional_context = self.CATEGORY_CONTEXTS.get(category, "성장을 위해 노력하고 있습니다.")
        category_name = self._get_category_name(category)
        
        system_prompt = "당신은 10년 경력의 비즈니스 멘토입니다."
        user_prompt = f"""
{vip_name}님은 지금 {category_name}(현재 점수: {score}점) 영역에서 다음과 같은 상태입니다: {emotional_context}

{vip_name}님이 스스로 점검하며 "아, 나 생각보다 괜찮네" 또는 "이런 부분만 채우면 되겠구나"라고 느낄 수 있는 따뜻하고 구체적인 체크리스트를 만들어주세요.

조건:
- 5~7개 문항
- "~했나요?" 또는 "~하고 있나요?" 형식
- 비난이 아닌 따뜻하고 격려하는 톤
- 구체적이고 실행 가능한 내용
- 비즈니스 오너의 관점 반영

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "intro": "간결하고 임팩트 있는 제목",
  "subtitle": "대표님을 향한 따뜻한 격려 문구",
  "checklist": ["질문1", "질문2", "질문3", "질문4", "질문5"],
  "minChecks": 3
}}
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        return json.loads(response.choices[0].message.content)

    def evaluate_answers(self, vip_name: str, category: str, questions: List[str], checked_indices: List[int]) -> Dict[str, Any]:
        """VIP의 체크리스트 응답 평가"""
        
        category_name = self._get_category_name(category)
        checked_items = [questions[i] for i in checked_indices]
        unchecked_items = [questions[i] for i in range(len(questions)) if i not in checked_indices]
        
        checked_count = len(checked_indices)
        total_count = len(questions)
        min_checks = 3 # 기본 기준
        
        system_prompt = "당신은 비즈니스 오너의 성장을 돕는 전문 멘토입니다."
        user_prompt = f"""
{vip_name}님이 "{category_name}" 영역의 체크리스트를 완료했습니다.

체크된 항목 ({checked_count}/{total_count}개):
{chr(10).join([f'✓ {item}' for item in checked_items])}

체크 안 된 항목:
{chr(10).join([f'☐ {item}' for item in unchecked_items])}

이 VIP의 "{category_name}" 개선 준비도를 평가하고, 다음 단계로 넘어갈 수 있는지 판단해주세요.

판단 기준:
- {min_checks}개 이상 체크 시 통과(passed: true).
- 하지만 핵심적인 항목이 빠졌거나 성의가 부족해 보인다면 재검토 권장 가능.
- 톤은 매우 따뜻하고 격려하며, 전문가적인 인사이트를 포함해야 함.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "passed": true 또는 false,
  "score": {checked_count},
  "total": {total_count},
  "message": "평가 및 격려 메시지 (3-4문장)",
  "nextStep": "통과 시 다음 단계 안내 문구 (미통과 시 빈 문자열)"
}}
"""
        
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        return json.loads(response.choices[0].message.content)

    def _get_category_name(self, category: str) -> str:
        names = {
            "future_safety_net": "자산 안정성",
            "emotional_anchor": "정서 균형",
            "time_mastery": "시간 독립성",
            "body_signals": "신체 신호",
            "relationship_power": "관계 파워",
            "system_leverage": "시스템 레버리지"
        }
        return names.get(category, category)
