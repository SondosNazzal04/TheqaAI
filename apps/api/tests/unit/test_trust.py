import pytest
from app.application.trust_service import TrustService
from app.domain.trust.models import TrustSignal

def test_individual_score_calculation():
    signals = {
        'identity_verification': TrustSignal(signal_type='identity_verification', value=1.0, metadata_payload={'level': 'basic'}),
        'successful_transaction_percent': TrustSignal(signal_type='successful_transaction_percent', value=95.0, metadata_payload={'deals': 20}),
        'dispute_history': TrustSignal(signal_type='dispute_history', value=1.0, metadata_payload={'opened': 1, 'lost': 0}),
        'ratings': TrustSignal(signal_type='ratings', value=4.5, metadata_payload={'count': 10}),
        'account_age': TrustSignal(signal_type='account_age', value=60.0)
    }

    score, breakdown = TrustService._calculate_individual_score(signals)
    
    assert breakdown['identity_verification'].contribution == pytest.approx(10.0) # 40 * 0.25
    assert breakdown['successful_transaction_percent'].contribution == pytest.approx(23.75) # 95 * 0.25
    assert breakdown['dispute_history'].contribution == pytest.approx(17.0) # (100 - 15) * 0.20
    assert breakdown['ratings'].contribution == pytest.approx(13.5) # 90 * 0.15
    assert breakdown['account_age'].contribution == pytest.approx(9.375) # 62.5 * 0.15
    assert score == pytest.approx(73.625)

def test_individual_cold_start():
    signals = {}
    score, breakdown = TrustService._calculate_individual_score(signals)
    
    assert breakdown['identity_verification'].contribution == pytest.approx(0.0)
    assert breakdown['successful_transaction_percent'].contribution == pytest.approx(17.5) # 70 * 0.25
    assert breakdown['dispute_history'].contribution == pytest.approx(20.0) # 100 * 0.20
    assert breakdown['ratings'].contribution == pytest.approx(10.5) # 70 * 0.15
    assert breakdown['account_age'].contribution == pytest.approx(3.0) # 20 * 0.15
    assert score == pytest.approx(51.0)

def test_merchant_score_calculation():
    signals = {
        'completed_orders': TrustSignal(signal_type='completed_orders', value=12.5),
        'transaction_volume': TrustSignal(signal_type='transaction_volume', value=2750.0),
        'refund_rate': TrustSignal(signal_type='refund_rate', value=0.075, metadata_payload={'deals': 20}),
        'dispute_rate': TrustSignal(signal_type='dispute_rate', value=0.055, metadata_payload={'deals': 20}),
        'response_time': TrustSignal(signal_type='response_time', value=30.0)
    }

    score, breakdown = TrustService._calculate_merchant_score(signals)
    
    assert breakdown['completed_orders'].contribution == pytest.approx(12.5) # 62.5 * 0.20
    assert breakdown['transaction_volume'].contribution == pytest.approx(9.375) # 62.5 * 0.15
    assert breakdown['refund_rate'].contribution == pytest.approx(13.75) # 55 * 0.25
    assert breakdown['dispute_rate'].contribution == pytest.approx(13.75) # 55 * 0.25
    assert breakdown['response_time'].contribution == pytest.approx(8.25) # 55 * 0.15
    assert score == pytest.approx(57.625)

def test_merchant_cold_start():
    signals = {}
    score, breakdown = TrustService._calculate_merchant_score(signals)
    
    assert breakdown['completed_orders'].contribution == pytest.approx(4.0) # 20 * 0.20
    assert breakdown['transaction_volume'].contribution == pytest.approx(3.0) # 20 * 0.15
    assert breakdown['refund_rate'].contribution == pytest.approx(17.5) # 70 * 0.25
    # Dispute: 0 deals, blended = 0.03. 0.03 is 70 in piecewise mapping.
    assert breakdown['dispute_rate'].contribution == pytest.approx(17.5) # 70 * 0.25
    assert breakdown['response_time'].contribution == pytest.approx(9.0) # 60 * 0.15
    assert score == pytest.approx(51.0)
