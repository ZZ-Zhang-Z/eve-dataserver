Get character wallet journal
get
https://esi.evetech.net/characters/{character_id}/wallet/journal
Retrieve the given character's wallet journal going 30 days back

This route is cached for an hour.

This route is part of the rate limit group . This group is limited to 150 tokens per 15 minutes.char-wallet

Authentication
This route requires the following scope: .esi-wallet.read_character_wallet.v1

Request
Authorization Code OAuth Flow

Authorize URL: https://login.eveonline.com/v2/oauth/authorize

Token URL: https://login.eveonline.com/v2/oauth/token

Scopes:

esi-wallet.read_character_wallet.v1 - esi-wallet.read_character_wallet.v1
Path Parameters
character_id
integer<int64>
required
The ID of the character

Example:
90000001
Query Parameters
page
integer<int32>
Which page of results to return.

>= 1
Headers
X-Compatibility-Date
string<date>
required
The compatibility date for the request.

Allowed value:
2026-06-09
Accept-Language
string
The language to use for the response.

Allowed values:
en
de
fr
ja
ru
zh
ko
es
Default:
en
If-None-Match
string
The ETag of the previous request. A 304 will be returned if this matches the current ETag.

X-Tenant
string
The tenant ID for the request.

Default:
tranquility
Example:
Responses
200
default
OK

Headers
Cache-Control
string
Directives for caching mechanisms. It controls how the response can be cached, by whom, and for how long.

ETag
string
The ETag value of the response body. Use this with If-None-Match to check whether the resource has changed.

Last-Modified
string
The last modified date of the response. Use this with If-Modified-Since to check whether the resource has changed.

X-Pages
integer<int64>
The total number of pages in the result set.

Body

application/json

application/json
responses
/
200
Wallet journal entries

array of:
amount
number<double>
The amount of ISK given or taken from the wallet as a result of the given transaction. Positive when ISK is deposited into the wallet and negative when ISK is withdrawn

balance
number<double>
Wallet balance after transaction occurred

context_id
integer<int64>
An ID that gives extra context to the particular transaction. Because of legacy reasons the context is completely different per ref_type and means different things. It is also possible to not have a context_id

context_id_type
string
The type of the given context_id if present

Allowed values:
structure_id
station_id
market_transaction_id
character_id
corporation_id
alliance_id
eve_system
industry_job_id
contract_id
planet_id
system_id
type_id
date
string<date-time>
required
Date and time of transaction

description
string
required
The reason for the transaction, mirrors what is seen in the client

first_party_id
integer<int64>
The id of the first party involved in the transaction. This attribute has no consistency and is different or non existant for particular ref_types. The description attribute will help make sense of what this attribute means. For more info about the given ID it can be dropped into the /universe/names/ ESI route to determine its type and name

id
integer<int64>
required
Unique journal reference ID

reason
string
The user stated reason for the transaction. Only applies to some ref_types

ref_type
string
required
"The transaction type for the given. transaction. Different transaction types will populate different attributes."

Allowed values:
acceleration_gate_fee
advertisement_listing_fee
agent_donation
agent_location_services
agent_miscellaneous
agent_mission_collateral_paid
agent_mission_collateral_refunded
agent_mission_reward
agent_mission_reward_corporation_tax
agent_mission_time_bonus_reward
agent_mission_time_bonus_reward_corporation_tax
agent_security_services
agent_services_rendered
agents_preward
air_career_program_reward
alliance_maintainance_fee
alliance_registration_fee
allignment_based_gate_toll
asset_safety_recovery_tax
bounty
bounty_prize
bounty_prize_corporation_tax
bounty_prizes
bounty_reimbursement
bounty_surcharge
brokers_fee
clone_activation
clone_transfer
contraband_fine
contract_auction_bid
contract_auction_bid_corp
contract_auction_bid_refund
contract_auction_sold
contract_brokers_fee
contract_brokers_fee_corp
contract_collateral
contract_collateral_deposited_corp
contract_collateral_payout
contract_collateral_refund
contract_deposit
contract_deposit_corp
contract_deposit_refund
contract_deposit_sales_tax
contract_price
contract_price_payment_corp
contract_reversal
contract_reward
contract_reward_deposited
contract_reward_deposited_corp
contract_reward_refund
contract_sales_tax
copying
corporate_reward_payout
corporate_reward_tax
corporation_account_withdrawal
corporation_bulk_payment
corporation_dividend_payment
corporation_liquidation
corporation_logo_change_cost
corporation_payment
corporation_registration_fee
cosmetic_market_component_item_purchase
cosmetic_market_skin_purchase
cosmetic_market_skin_sale
cosmetic_market_skin_sale_broker_fee
cosmetic_market_skin_sale_tax
cosmetic_market_skin_transaction
courier_mission_escrow
cspa
cspaofflinerefund
daily_challenge_reward
daily_goal_payouts
daily_goal_payouts_tax
datacore_fee
dna_modification_fee
docking_fee
duel_wager_escrow
duel_wager_payment
duel_wager_refund
ess_escrow_transfer
external_trade_delivery
external_trade_freeze
external_trade_thaw
factory_slot_rental_fee
flux_payout
flux_tax
flux_ticket_repayment
flux_ticket_sale
freelance_jobs_broadcasting_fee
freelance_jobs_duration_fee
freelance_jobs_escrow_refund
freelance_jobs_reward
freelance_jobs_reward_corporation_tax
freelance_jobs_reward_escrow
gm_cash_transfer
gm_plex_fee_refund
industry_job_tax
infrastructure_hub_maintenance
inheritance
insurance
insurgency_corruption_contribution_reward
insurgency_suppression_contribution_reward
item_trader_payment
jump_clone_activation_fee
jump_clone_installation_fee
kill_right_fee
lp_store
manufacturing
market_escrow
market_fine_paid
market_provider_tax
market_transaction
medal_creation
medal_issued
milestone_reward_payment
mission_completion
mission_cost
mission_expiration
mission_reward
office_rental_fee
operation_bonus
opportunity_reward
planetary_construction
planetary_export_tax
planetary_import_tax
player_donation
player_trading
project_discovery_reward
project_discovery_tax
project_payouts
reaction
redeemed_isk_token
release_of_impounded_property
repair_bill
reprocessing_tax
researching_material_productivity
researching_technology
researching_time_productivity
resource_wars_reward
reverse_engineering
season_challenge_reward
security_processing_fee
shares
skill_purchase
skyhook_claim_fee
sovereignity_bill
store_purchase
store_purchase_refund
structure_gate_jump
transaction_tax
under_construction
upkeep_adjustment_fee
war_ally_contract
war_fee
war_fee_surrender
second_party_id
integer<int64>
The id of the second party involved in the transaction. This attribute has no consistency and is different or non existant for particular ref_types. The description attribute will help make sense of what this attribute means. For more info about the given ID it can be dropped into the /universe/names/ ESI route to determine its type and name

tax
number<double>
Tax amount received. Only applies to tax related transactions

tax_receiver_id
integer<int64>
The corporation ID receiving any tax paid. Only applies to tax related transactions

Token
:
Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5IiwidHlwIjoiSldUIn0.eyJzY3AiOiJlc2ktd2FsbGV0LnJlYWRfY2hhcmFjdGVyX3dhbGxldC52MSIsImp0aSI6IjUyYWQ1YzZjLWEyNDAtNGVjNi05YzlhLWNlMmU4NWVmNjc2YSIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5Iiwic3ViIjoiQ0hBUkFDVEVSOkVWRToyMTIzMjc5MTM3IiwiYXpwIjoiZGV2ZWxvcGVyc19ldmVvbmxpbmVfY29tIiwidGVuYW50IjoidHJhbnF1aWxpdHkiLCJ0aWVyIjoibGl2ZSIsInJlZ2lvbiI6IndvcmxkIiwiYXVkIjpbImRldmVsb3BlcnNfZXZlb25saW5lX2NvbSIsIkVWRSBPbmxpbmUiXSwibmFtZSI6IkNva2VDb25xdWVyb3IiLCJvd25lciI6Im5LOU9YSGJ0YWJBUzQvekR2RTA3WnV5Mms2ST0iLCJleHAiOjE3NjYwMzgwNDEsImlhdCI6MTc2NjAzNjg0MSwiaXNzIjoiaHR0cHM6Ly9sb2dpbi5ldmVvbmxpbmUuY29tIn0.YemDU9TMLezekPlx3Ezz5QwZbDj3OEfhIwDZlBOjaecrWD66ltIQti60pGc7M1jWnMxB94_6vm8k5KH3aNZLEG0IMm__ZfEppEEGlW_r7cULDYGLsqe1fUur52Wz8Wq9slX5CqYJohP7axmhDytymcGZ4hSFm4PYSu5rG0c6fgoBtB5cRgGnkfCEzaFqcobR6EoVoUMRz3ATVmIcAc1zzqBtutBBpeF7EHBKTqU04ZT7Ha_moqlYq1fR3MUYwowCRXGaCXQct2uiNc9D17w4Ylntay4K4GMgfoswEZLzkO6eeILvtSN9pqcQdwYCjaP_e_hQfMc_APwhCjwTORgkmQ
character_id*
:
integer
page
:
integer
X-Compatibility-Date*
:

2026-06-09

2026-06-09
Accept-Language
:
Not Setendefrjaruzhkoes

select an option (defaults to: en)
If-None-Match
:
string
X-Tenant
:
defaults to: tranquility
Send API Request
import http.client

conn = http.client.HTTPSConnection("esi.evetech.net")

headers = {
    'Accept-Language': "",
    'If-None-Match': "",
    'X-Compatibility-Date': "2026-06-09",
    'X-Tenant': "",
    'Accept': "application/json",
    'Authorization': "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5IiwidHlwIjoiSldUIn0.eyJzY3AiOiJlc2ktd2FsbGV0LnJlYWRfY2hhcmFjdGVyX3dhbGxldC52MSIsImp0aSI6IjUyYWQ1YzZjLWEyNDAtNGVjNi05YzlhLWNlMmU4NWVmNjc2YSIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5Iiwic3ViIjoiQ0hBUkFDVEVSOkVWRToyMTIzMjc5MTM3IiwiYXpwIjoiZGV2ZWxvcGVyc19ldmVvbmxpbmVfY29tIiwidGVuYW50IjoidHJhbnF1aWxpdHkiLCJ0aWVyIjoibGl2ZSIsInJlZ2lvbiI6IndvcmxkIiwiYXVkIjpbImRldmVsb3BlcnNfZXZlb25saW5lX2NvbSIsIkVWRSBPbmxpbmUiXSwibmFtZSI6IkNva2VDb25xdWVyb3IiLCJvd25lciI6Im5LOU9YSGJ0YWJBUzQvekR2RTA3WnV5Mms2ST0iLCJleHAiOjE3NjYwMzgwNDEsImlhdCI6MTc2NjAzNjg0MSwiaXNzIjoiaHR0cHM6Ly9sb2dpbi5ldmVvbmxpbmUuY29tIn0.YemDU9TMLezekPlx3Ezz5QwZbDj3OEfhIwDZlBOjaecrWD66ltIQti60pGc7M1jWnMxB94_6vm8k5KH3aNZLEG0IMm__ZfEppEEGlW_r7cULDYGLsqe1fUur52Wz8Wq9slX5CqYJohP7axmhDytymcGZ4hSFm4PYSu5rG0c6fgoBtB5cRgGnkfCEzaFqcobR6EoVoUMRz3ATVmIcAc1zzqBtutBBpeF7EHBKTqU04ZT7Ha_moqlYq1fR3MUYwowCRXGaCXQct2uiNc9D17w4Ylntay4K4GMgfoswEZLzkO6eeILvtSN9pqcQdwYCjaP_e_hQfMc_APwhCjwTORgkmQ"
}

conn.request("GET", "/characters/{character_id}/wallet/journal", headers=headers)

res = conn.getresponse()
data = res.read()

print(data.decode("utf-8"))
[
  {
    "amount": 0,
    "balance": 0,
    "context_id": 0,
    "context_id_type": "structure_id",
    "date": "2019-08-24T14:15:22Z",
    "description": "string",
    "first_party_id": 0,
    "id": 0,
    "reason": "string",
    "ref_type": "acceleration_gate_fee",
    "second_party_id": 0,
    "tax": 0,
    "tax_receiver_id": 0
  }
]
Get a character's wallet balance
get
https://esi.evetech.net/characters/{character_id}/wallet
Returns a character's wallet balance

This route is cached for 2 minutes.

This route is part of the rate limit group char-wallet. This group is limited to 150 tokens per 15 minutes.

Authentication
This route requires the following scope: esi-wallet.read_character_wallet.v1.

Request
Authorization Code OAuth Flow

Authorize URL: https://login.eveonline.com/v2/oauth/authorize

Token URL: https://login.eveonline.com/v2/oauth/token

Scopes:

esi-wallet.read_character_wallet.v1 - esi-wallet.read_character_wallet.v1
Path Parameters
character_id
integer<int64>
required
The ID of the character

Example:
90000001
Headers
X-Compatibility-Date
string<date>
required
The compatibility date for the request.

Allowed value:
2026-06-09
Accept-Language
string
The language to use for the response.

Allowed values:
en
de
fr
ja
ru
zh
ko
es
Default:
en
If-None-Match
string
The ETag of the previous request. A 304 will be returned if this matches the current ETag.

X-Tenant
string
The tenant ID for the request.

Default:
tranquility
Example:
Responses
200
default
OK

Headers
Cache-Control
string
Directives for caching mechanisms. It controls how the response can be cached, by whom, and for how long.

ETag
string
The ETag value of the response body. Use this with If-None-Match to check whether the resource has changed.

Last-Modified
string
The last modified date of the response. Use this with If-Modified-Since to check whether the resource has changed.

Body

application/json

application/json
responses
/
200
number<double>
Wallet balance

Token
:
Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5IiwidHlwIjoiSldUIn0.eyJzY3AiOiJlc2ktd2FsbGV0LnJlYWRfY2hhcmFjdGVyX3dhbGxldC52MSIsImp0aSI6IjUyYWQ1YzZjLWEyNDAtNGVjNi05YzlhLWNlMmU4NWVmNjc2YSIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5Iiwic3ViIjoiQ0hBUkFDVEVSOkVWRToyMTIzMjc5MTM3IiwiYXpwIjoiZGV2ZWxvcGVyc19ldmVvbmxpbmVfY29tIiwidGVuYW50IjoidHJhbnF1aWxpdHkiLCJ0aWVyIjoibGl2ZSIsInJlZ2lvbiI6IndvcmxkIiwiYXVkIjpbImRldmVsb3BlcnNfZXZlb25saW5lX2NvbSIsIkVWRSBPbmxpbmUiXSwibmFtZSI6IkNva2VDb25xdWVyb3IiLCJvd25lciI6Im5LOU9YSGJ0YWJBUzQvekR2RTA3WnV5Mms2ST0iLCJleHAiOjE3NjYwMzgwNDEsImlhdCI6MTc2NjAzNjg0MSwiaXNzIjoiaHR0cHM6Ly9sb2dpbi5ldmVvbmxpbmUuY29tIn0.YemDU9TMLezekPlx3Ezz5QwZbDj3OEfhIwDZlBOjaecrWD66ltIQti60pGc7M1jWnMxB94_6vm8k5KH3aNZLEG0IMm__ZfEppEEGlW_r7cULDYGLsqe1fUur52Wz8Wq9slX5CqYJohP7axmhDytymcGZ4hSFm4PYSu5rG0c6fgoBtB5cRgGnkfCEzaFqcobR6EoVoUMRz3ATVmIcAc1zzqBtutBBpeF7EHBKTqU04ZT7Ha_moqlYq1fR3MUYwowCRXGaCXQct2uiNc9D17w4Ylntay4K4GMgfoswEZLzkO6eeILvtSN9pqcQdwYCjaP_e_hQfMc_APwhCjwTORgkmQ
character_id*
:
integer
X-Compatibility-Date*
:

2026-06-09

2026-06-09
Accept-Language
:
Not Setendefrjaruzhkoes

select an option (defaults to: en)
If-None-Match
:
string
X-Tenant
:
defaults to: tranquility
Send API Request
import http.client

conn = http.client.HTTPSConnection("esi.evetech.net")

headers = {
    'Accept-Language': "",
    'If-None-Match': "",
    'X-Compatibility-Date': "2026-06-09",
    'X-Tenant': "",
    'Accept': "application/json",
    'Authorization': "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5IiwidHlwIjoiSldUIn0.eyJzY3AiOiJlc2ktd2FsbGV0LnJlYWRfY2hhcmFjdGVyX3dhbGxldC52MSIsImp0aSI6IjUyYWQ1YzZjLWEyNDAtNGVjNi05YzlhLWNlMmU4NWVmNjc2YSIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5Iiwic3ViIjoiQ0hBUkFDVEVSOkVWRToyMTIzMjc5MTM3IiwiYXpwIjoiZGV2ZWxvcGVyc19ldmVvbmxpbmVfY29tIiwidGVuYW50IjoidHJhbnF1aWxpdHkiLCJ0aWVyIjoibGl2ZSIsInJlZ2lvbiI6IndvcmxkIiwiYXVkIjpbImRldmVsb3BlcnNfZXZlb25saW5lX2NvbSIsIkVWRSBPbmxpbmUiXSwibmFtZSI6IkNva2VDb25xdWVyb3IiLCJvd25lciI6Im5LOU9YSGJ0YWJBUzQvekR2RTA3WnV5Mms2ST0iLCJleHAiOjE3NjYwMzgwNDEsImlhdCI6MTc2NjAzNjg0MSwiaXNzIjoiaHR0cHM6Ly9sb2dpbi5ldmVvbmxpbmUuY29tIn0.YemDU9TMLezekPlx3Ezz5QwZbDj3OEfhIwDZlBOjaecrWD66ltIQti60pGc7M1jWnMxB94_6vm8k5KH3aNZLEG0IMm__ZfEppEEGlW_r7cULDYGLsqe1fUur52Wz8Wq9slX5CqYJohP7axmhDytymcGZ4hSFm4PYSu5rG0c6fgoBtB5cRgGnkfCEzaFqcobR6EoVoUMRz3ATVmIcAc1zzqBtutBBpeF7EHBKTqU04ZT7Ha_moqlYq1fR3MUYwowCRXGaCXQct2uiNc9D17w4Ylntay4K4GMgfoswEZLzkO6eeILvtSN9pqcQdwYCjaP_e_hQfMc_APwhCjwTORgkmQ"
}

conn.request("GET", "/characters/{character_id}/wallet", headers=headers)

res = conn.getresponse()
data = res.read()

print(data.decode("utf-8"))
