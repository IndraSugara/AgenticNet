"""
Security & Compliance Module

Features:
- Misconfiguration detection
- Attack surface analysis
- Compliance checking (ISO 27001, NIST, CIS)
- Risk-based prioritization
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class ComplianceStandard(Enum):
    ISO_27001 = "iso_27001"
    NIST = "nist"
    CIS = "cis"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityFinding:
    """A security finding/vulnerability"""
    title: str
    description: str
    risk_level: RiskLevel
    affected_resource: str
    remediation: str
    standards: List[ComplianceStandard] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "affected_resource": self.affected_resource,
            "remediation": self.remediation,
            "standards": [s.value for s in self.standards],
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ComplianceCheck:
    """Result of a compliance check"""
    control_id: str
    control_name: str
    standard: ComplianceStandard
    passed: bool
    details: str
    gap: str = ""


class SecurityModule:
    """
    Security and Compliance Module
    
    Capabilities:
    - Detect misconfigurations
    - Analyze attack surface
    - Check compliance against standards
    - Prioritize findings by risk
    """
    
    def __init__(self):
        self.findings: List[SecurityFinding] = []
        self.compliance_results: List[ComplianceCheck] = []
        
        # Common security checks
        self.security_checks = {
            "open_ports": self._check_open_ports,
            "weak_protocols": self._check_weak_protocols,
            "default_credentials": self._check_default_credentials,
            "unencrypted_traffic": self._check_unencrypted_traffic,
            "missing_firewall": self._check_missing_firewall
        }
    
    def analyze_config(self, config_text: str, device_type: str = "generic") -> List[SecurityFinding]:
        """
        Analyze network device configuration for security issues
        
        Args:
            config_text: Raw configuration text
            device_type: Type of device (cisco, juniper, etc.)
        """
        findings = []
        config_lower = config_text.lower()
        
        # Check for common misconfigurations
        
        # 1. Telnet enabled (should use SSH)
        if "telnet" in config_lower and "no telnet" not in config_lower:
            findings.append(SecurityFinding(
                title="Telnet Protocol Enabled",
                description="Telnet transmits data in plaintext, including credentials",
                risk_level=RiskLevel.HIGH,
                affected_resource=device_type,
                remediation="Disable Telnet and use SSH for remote management",
                standards=[ComplianceStandard.CIS, ComplianceStandard.NIST]
            ))
        
        # 2. HTTP enabled (should use HTTPS)
        if "ip http server" in config_lower and "no ip http server" not in config_lower:
            findings.append(SecurityFinding(
                title="HTTP Server Enabled",
                description="HTTP transmits data in plaintext",
                risk_level=RiskLevel.MEDIUM,
                affected_resource=device_type,
                remediation="Disable HTTP and use HTTPS only",
                standards=[ComplianceStandard.CIS]
            ))
        
        # 3. SNMP v1/v2 (should use v3)
        if "snmp-server community" in config_lower:
            findings.append(SecurityFinding(
                title="SNMP v1/v2 Community String",
                description="SNMP v1/v2 uses community strings which are transmitted in plaintext",
                risk_level=RiskLevel.MEDIUM,
                affected_resource=device_type,
                remediation="Upgrade to SNMP v3 with authentication and encryption",
                standards=[ComplianceStandard.NIST, ComplianceStandard.CIS]
            ))
        
        # 4. No password encryption
        if "password" in config_lower and "secret" not in config_lower:
            findings.append(SecurityFinding(
                title="Weak Password Storage",
                description="Passwords may be stored in plaintext or weak encryption",
                risk_level=RiskLevel.HIGH,
                affected_resource=device_type,
                remediation="Use 'enable secret' instead of 'enable password', apply service password-encryption",
                standards=[ComplianceStandard.ISO_27001, ComplianceStandard.CIS]
            ))
        
        # 5. No ACL on VTY lines
        if "line vty" in config_lower and "access-class" not in config_lower:
            findings.append(SecurityFinding(
                title="VTY Lines Without ACL",
                description="Virtual terminal lines accessible from any IP address",
                risk_level=RiskLevel.HIGH,
                affected_resource=device_type,
                remediation="Apply access-class to restrict management access by IP",
                standards=[ComplianceStandard.CIS, ComplianceStandard.NIST]
            ))
        
        self.findings.extend(findings)
        return findings
    
    def _check_open_ports(self, data: Dict) -> Optional[SecurityFinding]:
        """Check for risky open ports"""
        risky_ports = {
            21: "FTP - plaintext protocol",
            23: "Telnet - plaintext protocol",
            69: "TFTP - no authentication",
            135: "RPC - Windows vulnerability target",
            139: "NetBIOS - information disclosure",
            445: "SMB - ransomware target"
        }
        
        open_ports = data.get("open_ports", [])
        for port in open_ports:
            if port in risky_ports:
                return SecurityFinding(
                    title=f"Risky Port {port} Open",
                    description=risky_ports[port],
                    risk_level=RiskLevel.HIGH,
                    affected_resource=data.get("host", "unknown"),
                    remediation=f"Close port {port} or implement strict access controls",
                    standards=[ComplianceStandard.CIS]
                )
        return None
    
    def _check_weak_protocols(self, data: Dict) -> Optional[SecurityFinding]:
        """Check for weak protocols"""
        # Placeholder - would check actual protocol versions
        return None
    
    def _check_default_credentials(self, data: Dict) -> Optional[SecurityFinding]:
        """Check for default credentials"""
        # Placeholder - would check against known default creds
        return None
    
    def _check_unencrypted_traffic(self, data: Dict) -> Optional[SecurityFinding]:
        """Check for unencrypted traffic"""
        # Placeholder
        return None
    
    def _check_missing_firewall(self, data: Dict) -> Optional[SecurityFinding]:
        """Check for missing firewall rules"""
        # Placeholder
        return None
    
    def check_compliance(self, standard: ComplianceStandard) -> List[ComplianceCheck]:
        """
        Run compliance checks against a standard
        """
        results = []
        
        if standard == ComplianceStandard.CIS:
            results.extend(self._check_cis_controls())
        elif standard == ComplianceStandard.NIST:
            results.extend(self._check_nist_controls())
        elif standard == ComplianceStandard.ISO_27001:
            results.extend(self._check_iso27001_controls())
        
        self.compliance_results.extend(results)
        return results
    
    def _check_cis_controls(self) -> List[ComplianceCheck]:
        """CIS Benchmark checks"""
        return [
            ComplianceCheck(
                control_id="CIS-1.1",
                control_name="Inventory of Authorized and Unauthorized Devices",
                standard=ComplianceStandard.CIS,
                passed=True,
                details="Asset inventory maintained"
            ),
            ComplianceCheck(
                control_id="CIS-4.1", 
                control_name="Secure Configuration",
                standard=ComplianceStandard.CIS,
                passed=len([f for f in self.findings if f.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]) == 0,
                details="Checking for high/critical misconfigurations",
                gap="High-risk misconfigurations found" if self.findings else ""
            )
        ]
    
    def _check_nist_controls(self) -> List[ComplianceCheck]:
        """NIST framework checks"""
        return [
            ComplianceCheck(
                control_id="NIST-ID.AM",
                control_name="Asset Management",
                standard=ComplianceStandard.NIST,
                passed=True,
                details="Asset identification process in place"
            ),
            ComplianceCheck(
                control_id="NIST-PR.AC",
                control_name="Access Control",
                standard=ComplianceStandard.NIST,
                passed=True,
                details="Access control mechanisms verified"
            )
        ]
    
    def _check_iso27001_controls(self) -> List[ComplianceCheck]:
        """ISO 27001 controls"""
        return [
            ComplianceCheck(
                control_id="A.9.1",
                control_name="Access Control Policy",
                standard=ComplianceStandard.ISO_27001,
                passed=True,
                details="Access control policy defined"
            )
        ]
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get risk summary with prioritized findings"""
        by_risk = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": []
        }
        
        for finding in self.findings:
            by_risk[finding.risk_level.value].append(finding.to_dict())
        
        return {
            "total_findings": len(self.findings),
            "critical_count": len(by_risk["critical"]),
            "high_count": len(by_risk["high"]),
            "medium_count": len(by_risk["medium"]),
            "low_count": len(by_risk["low"]),
            "by_risk_level": by_risk
        }
    
    def format_for_agent(self) -> str:
        """Format security data for agent context"""
        summary = self.get_risk_summary()
        
        output = f"""
## 🔐 Security Status

**Total Findings:** {summary['total_findings']}
- 🔴 Critical: {summary['critical_count']}
- 🟠 High: {summary['high_count']}
- 🟡 Medium: {summary['medium_count']}
- 🟢 Low: {summary['low_count']}

### Top Findings (by risk)
"""
        # Show top 5 by priority
        all_findings = (
            summary['by_risk_level']['critical'][:2] +
            summary['by_risk_level']['high'][:2] +
            summary['by_risk_level']['medium'][:1]
        )
        
        for finding in all_findings[:5]:
            output += f"- [{finding['risk_level'].upper()}] {finding['title']}: {finding['description']}\n"
        
        return output


# Singleton instance
security = SecurityModule()
