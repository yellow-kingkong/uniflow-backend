"""
리포트 생성 서비스
"""
from typing import Dict, Any
from jinja2 import Template, Environment, FileSystemLoader
import os


class ReportGenerator:
    """리포트 HTML/PDF 생성"""
    
    def __init__(self, agent_output: Dict[str, Any], template_name: str = "report_template.html"):
        self.data = agent_output
        self.template_name = template_name
        
        # Jinja2 환경 설정
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))
    
    def generate_html(self) -> str:
        """HTML 리포트 생성"""
        template = self.env.get_template(self.template_name)
        
        # 데이터 준비
        context = {
            "user": self.data["user_data"],
            "persona": self.data["persona"],
            "bottlenecks": self.data["bottlenecks"],
            "benchmark": self.data.get("benchmark", {}),
            "narrative": self.data["narrative"],
            "cta": self.data["cta_timing"],
            "charts": self.generate_chart_data()
        }
        
        html = template.render(**context)
        return html
    
    def generate_chart_data(self) -> Dict[str, Any]:
        """Chart.js용 데이터 생성"""
        bottlenecks = self.data["bottlenecks"]["bottlenecks"]
        
        # 병목 심각도 차트
        severity_chart = {
            "labels": [b["issue"][:20] + "..." for b in bottlenecks],
            "data": [b["urgency"] * 10 for b in bottlenecks],
            "colors": ["#EF4444", "#F59E0B", "#F97316"]
        }
        
        # 월간 손실 차트
        loss_data = self.data["bottlenecks"]["total_monthly_loss"]
        loss_chart = {
            "time": loss_data["time"],
            "cost": loss_data["cost"]
        }
        
        # 벤치마크 차트
        benchmark = self.data.get("benchmark", {})
        benchmark_chart = {
            "current": benchmark.get("current", {}),
            "top_10": benchmark.get("top_10_percent", {})
        }
        
        return {
            "severity": severity_chart,
            "loss": loss_chart,
            "benchmark": benchmark_chart
        }
    
    def export_pdf(self) -> bytes:
        """PDF로 변환"""
        html = self.generate_html()
        
        # WeasyPrint를 사용한 PDF 변환
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html).write_pdf()
            return pdf_bytes
        except Exception as e:
            print(f"PDF 생성 실패: {e}")
            return b""
