"""
Decision Transparency Module

Ensures every decision is documented with:
- Technical reasoning
- Assumptions
- Risks and trade-offs
- Consequences if not done
- Conservative alternatives
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime
import json


@dataclass
class DecisionRecord:
    """Record of a transparent decision"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    decision: str = ""
    technical_reasoning: str = ""
    assumptions: List[str] = field(default_factory=list)
    risks_and_tradeoffs: List[str] = field(default_factory=list)
    consequences_if_not_done: str = ""
    conservative_alternatives: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical
    action_blocked: bool = False
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def to_markdown(self) -> str:
        """Format decision as markdown for display"""
        md = f"""
## 🧠 Decision Transparency Report

**Timestamp:** {self.timestamp}  
**Risk Level:** {self._risk_badge()}  
**Action Blocked:** {"⛔ Yes" if self.action_blocked else "✅ No"}

### 📋 Decision
{self.decision}

### 🔍 Technical Reasoning
{self.technical_reasoning}

### 📌 Assumptions
{self._format_list(self.assumptions)}

### ⚠️ Risks & Trade-offs
{self._format_list(self.risks_and_tradeoffs)}

### ❌ Consequences If Not Done
{self.consequences_if_not_done}

### 🛡️ Conservative Alternatives
{self._format_list(self.conservative_alternatives)}
"""
        return md.strip()
    
    def _risk_badge(self) -> str:
        badges = {
            "low": "🟢 Low",
            "medium": "🟡 Medium", 
            "high": "🟠 High",
            "critical": "🔴 Critical"
        }
        return badges.get(self.risk_level, "⚪ Unknown")
    
    def _format_list(self, items: List[str]) -> str:
        if not items:
            return "_None identified_"
        return "\n".join(f"- {item}" for item in items)


class TransparencyModule:
    """Module for managing decision transparency"""
    
    def __init__(self):
        self.history: List[DecisionRecord] = []
    
    def create_record(
        self,
        decision: str,
        technical_reasoning: str,
        assumptions: List[str] = None,
        risks_and_tradeoffs: List[str] = None,
        consequences_if_not_done: str = "",
        conservative_alternatives: List[str] = None,
        risk_level: str = "low"
    ) -> DecisionRecord:
        """Create and store a new decision record"""
        record = DecisionRecord(
            decision=decision,
            technical_reasoning=technical_reasoning,
            assumptions=assumptions or [],
            risks_and_tradeoffs=risks_and_tradeoffs or [],
            consequences_if_not_done=consequences_if_not_done,
            conservative_alternatives=conservative_alternatives or [],
            risk_level=risk_level
        )
        self.history.append(record)
        return record
    
    def get_history(self, limit: int = 10) -> List[DecisionRecord]:
        """Get recent decision history"""
        return self.history[-limit:]
    
    def should_block_action(self, risk_level: str) -> bool:
        """Determine if action should be blocked based on risk"""
        high_risk_levels = {"high", "critical"}
        return risk_level in high_risk_levels
    
    def format_for_llm(self) -> str:
        """Format transparency requirements for LLM prompt"""
        return """
WAJIB: Untuk setiap rekomendasi atau tindakan, berikan dalam format JSON:
{
  "decision": "keputusan yang diambil",
  "technical_reasoning": "alasan teknis lengkap",
  "assumptions": ["asumsi 1", "asumsi 2"],
  "risks_and_tradeoffs": ["risiko 1", "trade-off 1"],
  "consequences_if_not_done": "apa yang terjadi jika tidak dilakukan",
  "conservative_alternatives": ["alternatif konservatif 1"],
  "risk_level": "low|medium|high|critical"
}
"""


# Singleton instance
transparency = TransparencyModule()
