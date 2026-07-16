from abc import ABC, abstractmethod

class ProviderEscrowPort(ABC):
    @abstractmethod
    async def create_payment_intent(self, amount_minor: int, currency: str, idempotency_key: str, deal_id: str) -> str:
        """
        Communicates with the licensed payment provider to create an intent to hold funds.
        Returns the provider's intent ID.
        """
        pass

    @abstractmethod
    async def release_funds(self, intent_id: str, seller_net_minor: int, fee_minor: int) -> str:
        """
        Instructs the licensed provider to release funds from escrow.
        Returns the release transaction ID.
        """
        pass
        
    @abstractmethod
    async def refund_funds(self, intent_id: str, amount_minor: int) -> str:
        """
        Instructs the licensed provider to refund funds to the buyer.
        Returns the refund transaction ID.
        """
        pass
