"""EmailProcessingPipeline — wires cleaner → rule_engine → orchestrator."""

from ..privacy.debug_store import DebugStore
from .cleaner import EmailCleaner
from .extraction_orchestrator import ExtractionOrchestrator, FinalExtraction
from .rule_engine import RuleEngine


class EmailProcessingPipeline:
    """Runs a single email through the full extraction pipeline.

    Args:
        cleaner: EmailCleaner instance.
        rule_engine: RuleEngine instance.
        orchestrator: ExtractionOrchestrator instance.
        debug_store: DebugStore for cleaned-text artifacts.
    """

    def __init__(
        self,
        cleaner: EmailCleaner,
        rule_engine: RuleEngine,
        orchestrator: ExtractionOrchestrator,
        debug_store: DebugStore,
    ) -> None:
        self._cleaner = cleaner
        self._rules = rule_engine
        self._orchestrator = orchestrator
        self._debug = debug_store

    def process(
        self,
        email_id: str,
        raw_body: str,
        sender_domain: str | None = None,
    ) -> FinalExtraction:
        """Run the full pipeline for one email and return the FinalExtraction."""
        cleaned = self._cleaner.clean(email_id, raw_body)
        self._debug.store_cleaned_text(email_id, cleaned.cleaned_text)
        rules = self._rules.extract(email_id, cleaned.cleaned_text, sender_domain=sender_domain)
        return self._orchestrator.orchestrate(cleaned, rules)
