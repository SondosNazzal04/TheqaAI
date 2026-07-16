from abc import ABC, abstractmethod

class ProviderEscrowPort(ABC):
    @abstractmethod
    async def create_payment_intent(self, amount_minor: int, currency: str, idempotency_key: str, deal_id: str) -> str:
        """
        Communicates with the licensed payment provider to create an intent to hold funds.
        Returns the provider's intent ID.
        """
        pass
