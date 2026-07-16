import pytest
import uuid
from app.domain.deal.models import Deal
from app.application.deal_state_machine import DealState

@pytest.mark.asyncio
async def test_create_deal(client, db_data):
    response = await client.post(
        "/v1/deals",
        json={
            "org_id": str(db_data["org_id"]),
            "title": "Test Deal Create",
            "amount": 500.0,
            "fee_bps": 200,
            "fee_payer": "split"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "draft"
    assert data["public_code"] is not None
    assert data["fee_amount"] == 10.0 # 500 * (200 / 10000)
    assert data["net_amount"] == 495.0 # 500 - (10.0 / 2)

@pytest.mark.asyncio
async def test_accept_deal_as_seller_fails(db, client, db_data):
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=db_data["user_id"], # mock_user is the seller!
        title="Seller Accept Test",
        amount=100.0,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    response = await client.post(f"/v1/deals/{deal.id}/accept")
        
    assert response.status_code == 400
    assert response.json()["detail"] == "Seller cannot accept their own deal"

@pytest.mark.asyncio
async def test_accept_deal_as_buyer(db, client, db_data):
    from app.domain.auth.models import User
    
    # Setup deal owned by SOMEONE ELSE
    other_user_id = uuid.uuid4()
    other_user = User(id=other_user_id, email=f"other_{other_user_id}@test.com", status="active")
    db.add(other_user)
    
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=other_user_id,
        title="Buyer Accept Test",
        amount=100.0,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    
    response = await client.post(f"/v1/deals/{deal.id}/accept")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "awaiting_funding"
    assert data["buyer_user_id"] == str(db_data["user_id"])

@pytest.mark.asyncio
async def test_get_deal_by_code(db, client, db_data):
    public_code = f"TEST{uuid.uuid4().hex[:6].upper()}"
    deal = Deal(
        org_id=db_data["org_id"],
        seller_user_id=db_data["user_id"],
        title="Public Deal",
        amount=100.0,
        public_code=public_code,
        status=DealState.DRAFT.value
    )
    db.add(deal)
    await db.commit()
    
    response = await client.get(f"/v1/deals/by-code/{public_code}")
        
    assert response.status_code == 200
    data = response.json()
    assert data["public_code"] == public_code
