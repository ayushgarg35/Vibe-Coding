"""
PII Guard — detects and anonymizes PII before any data reaches an LLM.
Uses Microsoft Presidio (rule-based + NLP). No PII leaves this layer.
Required for SOC2, GDPR, and DPDPA compliance.
"""
import structlog
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

log = structlog.get_logger()

# PII entity types to detect and anonymize
ENTITIES_TO_ANONYMIZE = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "LOCATION",
    "DATE_TIME",
    "NRP",              # National Registration/ID numbers
    "MEDICAL_LICENSE",
    "URL",
    "IN_PAN",           # India PAN number
    "IN_AADHAAR",       # India Aadhaar
    "US_SSN",
    "US_PASSPORT",
]


class PIIGuard:
    """
    Intercepts all text before LLM calls.
    Replaces detected PII with placeholder tokens e.g. <PERSON_1>.
    This is a best-effort layer — always review outputs for sensitive data.
    """

    def __init__(self):
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        log.info("PIIGuard initialized")

    def anonymize(self, text: str) -> str:
        if not text or not text.strip():
            return text

        results = self._analyzer.analyze(
            text=text,
            entities=ENTITIES_TO_ANONYMIZE,
            language="en",
        )

        if not results:
            return text

        log.info("PII detected and anonymized", entity_count=len(results))

        anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text

    def has_pii(self, text: str) -> bool:
        results = self._analyzer.analyze(
            text=text,
            entities=ENTITIES_TO_ANONYMIZE,
            language="en",
        )
        return len(results) > 0
