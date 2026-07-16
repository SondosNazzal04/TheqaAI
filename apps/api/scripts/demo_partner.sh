#!/bin/bash
# Demo Partner Script to create a deal programmatically

echo "Creating a deal via API as Alpha Electronics (Partner)"
curl -X POST http://localhost:8000/v1/deals \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk_test_theqademo123_secretkey123" \
  -d '{
    "org_id": "6f3d1d2b-d080-4e70-ab62-86acd78d4204",
    "title": "API Created Deal",
    "description": "This deal was created by a third-party partner integration.",
    "amount": 1500.00,
    "currency": "JOD",
    "fulfillment_mode": "standard",
    "fee_bps": 200,
    "fee_payer": "seller"
  }' | jq .
