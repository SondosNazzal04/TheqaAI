import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, List, Tuple

from app.domain.trust.models import TrustSignal, TrustScore
from app.schemas.trust import TrustScoreResponse, SignalBreakdown

def _piecewise_linear(val: float, points: List[Tuple[float, float]]) -> float:
    if val <= points[0][0]:
        return points[0][1]
    if val >= points[-1][0]:
        return points[-1][1]
    
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if x1 <= val <= x2:
            ratio = (val - x1) / (x2 - x1)
            return y1 + ratio * (y2 - y1)
    return points[-1][1]

class TrustService:
    @staticmethod
    async def get_score(db: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> TrustScoreResponse | None:
        result = await db.execute(select(TrustScore).where(
            TrustScore.entity_type == entity_type,
            TrustScore.entity_id == entity_id
        ))
        trust_score = result.scalar_one_or_none()
        if not trust_score:
            return None
            
        return TrustScoreResponse.model_validate(trust_score)

    @staticmethod
    async def calculate_and_save_score(db: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> TrustScoreResponse:
        result = await db.execute(select(TrustSignal).where(
            TrustSignal.entity_type == entity_type,
            TrustSignal.entity_id == entity_id
        ))
        signals = result.scalars().all()
        signal_map = {s.signal_type: s for s in signals}
        
        if entity_type == 'individual':
            score, breakdown = TrustService._calculate_individual_score(signal_map)
        elif entity_type == 'merchant':
            score, breakdown = TrustService._calculate_merchant_score(signal_map)
        else:
            raise ValueError("Invalid entity type")
            
        result = await db.execute(select(TrustScore).where(
            TrustScore.entity_type == entity_type,
            TrustScore.entity_id == entity_id
        ))
        trust_score = result.scalar_one_or_none()
        
        breakdown_dict = {k: v.model_dump() for k, v in breakdown.items()}
        
        if trust_score:
            trust_score.score = score
            trust_score.breakdown = breakdown_dict
        else:
            trust_score = TrustScore(
                entity_type=entity_type,
                entity_id=entity_id,
                score=score,
                breakdown=breakdown_dict
            )
            db.add(trust_score)
            
        await db.commit()
        await db.refresh(trust_score)
        return TrustScoreResponse.model_validate(trust_score)

    @staticmethod
    def _calculate_individual_score(signal_map: Dict[str, TrustSignal]):
        breakdown = {}
        total_score = 0.0
        
        identity = signal_map.get('identity_verification')
        w_id = 0.25
        if not identity:
            val_id = 0.0
            breakdown['identity_verification'] = SignalBreakdown(weight=w_id, value=val_id, contribution=val_id * w_id, applied_prior=True)
        else:
            level = identity.metadata_payload.get('level', 'none') if identity.metadata_payload else 'none'
            if level == 'verified':
                val_id = 100.0
            elif level == 'basic':
                val_id = 40.0
            else:
                val_id = 0.0
            breakdown['identity_verification'] = SignalBreakdown(weight=w_id, value=val_id, contribution=val_id * w_id, raw_value=identity.value)
        total_score += breakdown['identity_verification'].contribution
        
        success = signal_map.get('successful_transaction_percent')
        w_suc = 0.25
        n_deals = success.metadata_payload.get('deals', 0) if success and success.metadata_payload else 0
        observed_success = success.value if success else 0.0
        if n_deals < 3:
            val_suc = (n_deals * observed_success + 3 * 70.0) / (n_deals + 3)
            breakdown['successful_transaction_percent'] = SignalBreakdown(weight=w_suc, value=val_suc, contribution=val_suc * w_suc, raw_value=observed_success, applied_prior=True)
        else:
            val_suc = min(100.0, max(0.0, observed_success))
            breakdown['successful_transaction_percent'] = SignalBreakdown(weight=w_suc, value=val_suc, contribution=val_suc * w_suc, raw_value=observed_success)
        total_score += breakdown['successful_transaction_percent'].contribution
        
        disputes = signal_map.get('dispute_history')
        w_disp = 0.20
        if not disputes:
            val_disp = 100.0
            breakdown['dispute_history'] = SignalBreakdown(weight=w_disp, value=val_disp, contribution=val_disp * w_disp, applied_prior=True)
        else:
            opened = disputes.metadata_payload.get('opened', 0) if disputes.metadata_payload else 0
            lost = disputes.metadata_payload.get('lost', 0) if disputes.metadata_payload else 0
            
            penalty_opened = min(45.0, opened * 15.0)
            penalty_lost = min(50.0, lost * 25.0)
            
            val_disp = max(0.0, 100.0 - penalty_opened - penalty_lost)
            breakdown['dispute_history'] = SignalBreakdown(weight=w_disp, value=val_disp, contribution=val_disp * w_disp, raw_value=float(opened + lost))
        total_score += breakdown['dispute_history'].contribution
            
        ratings = signal_map.get('ratings')
        w_rat = 0.15
        n_ratings = ratings.metadata_payload.get('count', 0) if ratings and ratings.metadata_payload else 0
        observed_rating = ratings.value if ratings else 0.0
        if n_ratings < 3:
            val_rat = 70.0
            breakdown['ratings'] = SignalBreakdown(weight=w_rat, value=val_rat, contribution=val_rat * w_rat, raw_value=observed_rating, applied_prior=True)
        else:
            val_rat = min(100.0, max(0.0, (observed_rating / 5.0) * 100.0))
            breakdown['ratings'] = SignalBreakdown(weight=w_rat, value=val_rat, contribution=val_rat * w_rat, raw_value=observed_rating)
        total_score += breakdown['ratings'].contribution
        
        age = signal_map.get('account_age')
        w_age = 0.15
        age_points = [(0.0, 20.0), (30.0, 50.0), (90.0, 75.0), (180.0, 100.0)]
        if not age:
            val_age = 20.0
            breakdown['account_age'] = SignalBreakdown(weight=w_age, value=val_age, contribution=val_age * w_age, applied_prior=True)
        else:
            days = age.value
            val_age = _piecewise_linear(days, age_points)
            breakdown['account_age'] = SignalBreakdown(weight=w_age, value=val_age, contribution=val_age * w_age, raw_value=days)
        total_score += breakdown['account_age'].contribution
        
        return total_score, breakdown

    @staticmethod
    def _calculate_merchant_score(signal_map: Dict[str, TrustSignal]):
        breakdown = {}
        total_score = 0.0
        
        completed = signal_map.get('completed_orders')
        w_comp = 0.20
        orders_points = [(0.0, 20.0), (5.0, 50.0), (20.0, 75.0), (50.0, 100.0)]
        observed_comp = completed.value if completed else 0.0
        val_comp = _piecewise_linear(observed_comp, orders_points)
        breakdown['completed_orders'] = SignalBreakdown(weight=w_comp, value=val_comp, contribution=val_comp * w_comp, raw_value=observed_comp)
        total_score += breakdown['completed_orders'].contribution
        
        volume = signal_map.get('transaction_volume')
        w_vol = 0.15
        vol_points = [(0.0, 20.0), (500.0, 50.0), (5000.0, 75.0), (20000.0, 100.0)]
        observed_vol = volume.value if volume else 0.0
        val_vol = _piecewise_linear(observed_vol, vol_points)
        breakdown['transaction_volume'] = SignalBreakdown(weight=w_vol, value=val_vol, contribution=val_vol * w_vol, raw_value=observed_vol)
        total_score += breakdown['transaction_volume'].contribution
        
        n_deals_refund = signal_map.get('refund_rate').metadata_payload.get('deals', 0) if signal_map.get('refund_rate') and signal_map.get('refund_rate').metadata_payload else 0
        n_deals_disp = signal_map.get('dispute_rate').metadata_payload.get('deals', 0) if signal_map.get('dispute_rate') and signal_map.get('dispute_rate').metadata_payload else 0
        n_deals = max(n_deals_refund, n_deals_disp)
        
        refund = signal_map.get('refund_rate')
        w_ref = 0.25
        ref_points = [(0.0, 100.0), (0.05, 70.0), (0.10, 40.0), (0.20, 0.0)]
        observed_ref = refund.value if refund else 0.0
        if n_deals < 5:
            blended_ref = (n_deals * observed_ref + 5 * 0.05) / (n_deals + 5)
            val_ref = _piecewise_linear(blended_ref, ref_points)
            breakdown['refund_rate'] = SignalBreakdown(weight=w_ref, value=val_ref, contribution=val_ref * w_ref, raw_value=observed_ref, applied_prior=True)
        else:
            val_ref = _piecewise_linear(observed_ref, ref_points)
            breakdown['refund_rate'] = SignalBreakdown(weight=w_ref, value=val_ref, contribution=val_ref * w_ref, raw_value=observed_ref)
        total_score += breakdown['refund_rate'].contribution
        
        dispute = signal_map.get('dispute_rate')
        w_disp = 0.25
        disp_points = [(0.0, 100.0), (0.03, 70.0), (0.08, 40.0), (0.15, 0.0)]
        observed_disp = dispute.value if dispute else 0.0
        if n_deals < 5:
            blended_disp = (n_deals * observed_disp + 5 * 0.03) / (n_deals + 5)
            val_disp = _piecewise_linear(blended_disp, disp_points)
            breakdown['dispute_rate'] = SignalBreakdown(weight=w_disp, value=val_disp, contribution=val_disp * w_disp, raw_value=observed_disp, applied_prior=True)
        else:
            val_disp = _piecewise_linear(observed_disp, disp_points)
            breakdown['dispute_rate'] = SignalBreakdown(weight=w_disp, value=val_disp, contribution=val_disp * w_disp, raw_value=observed_disp)
        total_score += breakdown['dispute_rate'].contribution
        
        response = signal_map.get('response_time')
        w_res = 0.15
        res_points = [(2.0, 100.0), (12.0, 70.0), (48.0, 40.0), (96.0, 10.0)]
        if not response:
            val_res = 60.0
            breakdown['response_time'] = SignalBreakdown(weight=w_res, value=val_res, contribution=val_res * w_res, applied_prior=True)
        else:
            hours = response.value
            val_res = _piecewise_linear(hours, res_points)
            breakdown['response_time'] = SignalBreakdown(weight=w_res, value=val_res, contribution=val_res * w_res, raw_value=hours)
        total_score += breakdown['response_time'].contribution
        
        return total_score, breakdown

async def trust_recompute(entity_type: str, entity_id: uuid.UUID):
    from app.adapters.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await TrustService.calculate_and_save_score(session, entity_type, entity_id)
