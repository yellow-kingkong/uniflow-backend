"""
Master Agent: 모든 에이전트를 조율하는 마스터 에이전트
"""
from typing import Dict, Any
from app.agents.persona_agent import PersonaAgent
from app.agents.analysis_agent import AnalysisAgent
from app.agents.emotion_agent import EmotionAgent


class MasterDiagnosticAgent:
    """비즈니스 진단 마스터 에이전트"""
    
    def __init__(self):
        self.persona_agent = PersonaAgent()
        self.analysis_agent = AnalysisAgent()
        self.emotion_agent = EmotionAgent()
    
    def analyze(self, survey_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        전체 분석 파이프라인 실행
        
        Args:
            survey_data: 설문 응답 데이터
        
        Returns:
            완전한 리포트 생성을 위한 모든 데이터
        """
        
        # 1. 페르소나 분류
        print("🔍 Step 1: 페르소나 분류 중...")
        persona = self.persona_agent.classify(survey_data)
        
        # 2. 병목 포인트 분석
        print("🔍 Step 2: 병목 포인트 분석 중...")
        bottlenecks = self.analysis_agent.identify_bottlenecks(survey_data)
        
        # 3. 벤치마크 분석
        print("🔍 Step 3: 업종 벤치마크 분석 중...")
        industry = survey_data.get("industry", "일반")
        benchmark = self.analysis_agent.calculate_benchmark_gap(survey_data, industry)
        
        # 4. 감성 내러티브 생성
        print("🔍 Step 4: 감성 내러티브 생성 중...")
        user_data = {
            "name": survey_data.get("name", "대표님"),
            "business_type": survey_data.get("business_type", ""),
            "industry": survey_data.get("industry", ""),
            "years_in_business": survey_data.get("years_in_business", 0),
            "revenue_range": survey_data.get("revenue_range", ""),
            "team_size": survey_data.get("team_size", 0)
        }
        
        narrative = self.emotion_agent.generate_narrative(
            bottlenecks=bottlenecks,
            persona=persona,
            user_data=user_data
        )
        
        # 5. 최종 결과 통합
        result = {
            "persona": persona,
            "bottlenecks": bottlenecks,
            "benchmark": benchmark,
            "narrative": narrative,
            "user_data": user_data,
            "cta_timing": self._calculate_optimal_cta_moment(persona, bottlenecks)
        }
        
        print("✅ 분석 완료!")
        return result
    
    def _calculate_optimal_cta_moment(
        self,
        persona: Dict[str, Any],
        bottlenecks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """최적의 CTA 타이밍 계산"""
        
        urgency = bottlenecks.get("overall_urgency", 5)
        persona_type = persona.get("persona_type", "")
        
        # 긴급도가 높을수록 빠른 CTA
        if urgency >= 8:
            timing = "즉시"
            discount_hours = 24
        elif urgency >= 6:
            timing = "24시간 내"
            discount_hours = 48
        else:
            timing = "48시간 내"
            discount_hours = 72
        
        return {
            "timing": timing,
            "discount_deadline_hours": discount_hours,
            "urgency_level": urgency
        }
