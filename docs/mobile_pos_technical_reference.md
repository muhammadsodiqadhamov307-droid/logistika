# Van Sales Pharma Mobile POS Technical Reference

This document describes the Mobile POS implementation in the `van_sales_pharma`
Odoo addon. It is intended for developers who need to maintain, extend, debug,
or integrate the mobile POS flow.

## 1. Scope

The Mobile POS is a fullscreen Odoo web client action used by van sales agents
to:

- sell products from an agent's van inventory;
- create cash sales and customer debt sales;
- collect customer payments;
- record agent cash inflows and outflows;
- create and fulfill customer requests;
- load products from suppliers into an agent's van inventory;
- work with cached data and queue transactions while offline.

The main implementation files are:

- `van_sales_pharma/static/src/js/van_mobile_pos.js`
- `van_sales_pharma/static/src/xml/van_mobile_pos.xml`
- `van_sales_pharma/controllers/main.py`
- `van_sales_pharma/controllers/pwa.py`
- `van_sales_pharma/models/van_pos_order.py`
- `van_sales_pharma/models/van_payment.py`
- `van_sales_pharma/models/van_request.py`
- `van_sales_pharma/models/van_trip.py`
- `van_sales_pharma/models/van_agent_summary.py`
- `van_sales_pharma/views/van_mobile_pos_action.xml`
- `van_sales_pharma/views/van_mobile_pos_templates.xml`
- `van_sales_pharma/static/manifest.json`
- `van_sales_pharma/static/service-worker.js`

## 2. Entry Points

### Odoo Menu Action

`views/van_mobile_pos_action.xml` defines two actions:

- `action_van_mobile_pos_entry`
  - Type: `ir.actions.act_url`
  - URL: `/van/mobile-pos`
  - Used by the `Mobil POS` menu item.
- `action_van_mobile_pos_app`
  - Type: `ir.actions.client`
  - Tag: `van_sales_pharma.MobilePosClientAction`
  - Target: `fullscreen`
  - Boots the OWL component.

The menu item is restricted to:

- `van_sales_pharma.group_van_agent`
- `van_sales_pharma.group_van_admin`

### HTTP Entry

`controllers/main.py` exposes `/van/mobile-pos`.

Behavior:

- A normal agent is redirected directly to the fullscreen OWL action.
- An admin without an active selected agent sees the agent selection template.
- An admin with `request.session['acting_as_agent_id']` is redirected to the
  fullscreen OWL action while acting as that agent.

`controllers/pwa.py` exposes `/van/app`, which is the PWA start URL.

Behavior:

- Unauthenticated users are redirected to `/web/login?redirect=/van/app`.
- Agent users are redirected to the Mobile POS action.
- Admins and other users are redirected to the Van Sales dashboard.

## 3. Frontend Architecture

The Mobile POS frontend is an OWL component:

```js
export class VanMobilePos extends Component
```

It is registered under:

```js
registry.category("actions").add(
    "van_sales_pharma.MobilePosClientAction",
    VanMobilePos
);
```

The template name is:

```js
VanMobilePos.template = "van_sales_pharma.VanMobilePos";
```

The UI template is implemented in `static/src/xml/van_mobile_pos.xml`.

### Services

The component uses:

- `action`: Odoo action service for navigation to forms, dashboards, and reloads.
- `notification`: Odoo notification service for toast messages.
- `rpc`: JSON-RPC calls to `/van/pos/*` and `/van/mijoz/*` endpoints.
- `session`: current Odoo session object.

### Startup Sequence

During `onWillStart`, the component:

1. Initializes IndexedDB.
2. Loads the current acting agent.
3. Loads clients, inventory, all products, and suppliers.
4. Starts a 15 second inventory polling interval when online.
5. Injects CSS to hide the normal Odoo navbar and make the POS fullscreen.
6. Adds `van-pos-active` to the document body.

During component teardown, it clears polling and removes the injected fullscreen
style.

### Main Screens

The active screen is stored in `state.screen`. Known screen values include:

- `products`
- `clients`
- `checkout`
- `kirim`
- `payment_history`
- `requests_list`
- `new_request_form`
- `request_details`
- `request_add_product`
- `trips_list`
- `mahsulot_yuklash_form`
- `trip_details`
- `client_report`
- `offline_queue`

The template uses this value to switch between product browsing, client
selection, checkout, payment collection, request management, product loading,
history views, and reports.

## 4. Frontend State Model

Important state groups in `van_mobile_pos.js`:

### Core Data

- `clients`: client list assigned to the current agent.
- `inventory`: products currently available in the agent's van inventory.
- `allProducts`: all active products, used by loading and request flows.
- `currentAgent`: active agent metadata.
- `taminotchis`: supplier list.

### Sale State

- `selectedClient`: selected customer. Customer id `0` represents cash sale
  without a real partner.
- `cart`: product id keyed object. Each item contains:
  - `qty`
  - `product`
  - `custom_price`
- `newNasiyaId`: debt record created after an online credit sale.
- `nasiyaAmount`: amount of the newly created debt sale.
- `kirimAmount`: amount entered for payment after a credit sale.
- `sourceSorovId`: request id when the cart was created from a customer request.

### Payment State

- `showQuickAction`
- `quickActionType`: `kirim` or `chiqim`
- `quickActionAmount`
- `quickActionNote`
- `quickActionPartnerId`
- `quickActionExpenseType`: `daily` or `salary`
- `paymentHistory`
- `paymentHistoryType`
- `editingPaymentId`

### Request State

- `requestsList`
- `requestFilter`
- `requestPartnerId`
- `requestPartnerName`
- `requestNote`
- `requestCart`
- `activeRequest`

### Trip Loading State

- `selectedTaminotchiId`
- `tripsList`
- `activeTrip`
- `tripDate`
- `tripNote`
- `tripCart`
- `yuklashPreviewLines`
- `yuklashPreviewTotal`

### Offline State

- `isOnline`
- `syncQueue`
- `isSyncing`

## 5. Data Models

### `van.pos.order`

Defined in `models/van_pos_order.py`.

Purpose: mobile POS sale document.

Important fields:

- `name`: generated from `ir.sequence` code `van.pos.order`.
- `agent_id`: selling agent.
- `partner_id`: customer. Empty means cash sale without customer.
- `date`: sale datetime.
- `amount_total`: computed from sale lines.
- `commission_amount`: snapped when order is confirmed.
- `state`: `draft`, `done`, or `cancel`.
- `line_ids`: one2many to `van.pos.order.line`.
- `nasiya_id`: debt record created for customer-backed sales.
- `offline_id`: browser generated idempotency key for offline sync.
- `payment_type`: computed as `naqt` if no partner, otherwise `nasiya`.
- `request_id`: optional link to a fulfilled customer request.

Confirmation behavior:

- Requires draft state and at least one line.
- Looks up the agent's `van.agent.summary`.
- Validates that each product has enough `remaining_qty`.
- Creates a `van.nasiya` record only when `partner_id` exists.
- Calculates commission from original product `list_price`, not discounted
  custom price.
- Sets state to `done`.
- Sends a Telegram receipt if the partner has `telegram_chat_id`.

Inventory is not manually decremented on the order. Instead,
`van.agent.inventory.line.remaining_qty` is computed from loaded plus opening
stock minus all confirmed POS sales.

### `van.pos.order.line`

Purpose: line item for a mobile POS sale.

Important fields:

- `product_id`: `van.product`.
- `qty`
- `price_unit`
- `subtotal`: `qty * price_unit`.
- `cost_price`: related to product cost.
- `margin`: `(price_unit - cost_price) * qty`.

### `van.payment`

Defined in `models/van_payment.py`.

Purpose: cash movement records.

Important fields:

- `partner_id`: optional customer, used for customer debt payments.
- `agent_id`
- `nasiya_id`: optional linked debt.
- `payment_type`: `in` for kirim, `out` for chiqim.
- `expense_type`: `daily`, `salary`, or `payout`.
- `offline_id`: browser generated idempotency key for offline sync.
- `payment_method`: `cash` or `card`.
- `amount`
- `date`
- `state`: `received` or `confirmed`.

Create behavior:

- Generates a sequence from `van.payment`.
- Sends a Telegram payment notification for customer kirim when possible.

### `van.request`

Defined in `models/van_request.py`.

Purpose: customer request or order request before it becomes a POS sale.

Important fields:

- `agent_id`
- `partner_id`
- `line_ids`
- `state`: `draft`, `done`, or `cancel`.
- `total_amount`
- `fulfilled_date`
- `sale_order_id`

Mobile POS can create, list, edit, cancel, mark done, and convert a request into
the checkout flow.

### `van.trip`

Defined in `models/van_trip.py`.

Purpose: product loading into an agent's van inventory.

Important fields:

- `taminotchi_id`: supplier.
- `agent_id`
- `location_id`
- `date`
- `state`: `draft` or `validated`.
- `trip_line_ids`
- `x_loaded_qty`
- `amount_cost_total`

Validation behavior:

- Creates an agent summary if missing.
- Groups trip lines by product.
- Adds loaded quantities to `van.agent.inventory.line`.
- Uses product cost and sale prices from the trip line/product.

The Mobile POS trip endpoint auto-validates the trip immediately after creation.

### `van.agent.summary` and `van.agent.inventory.line`

Defined in `models/van_agent_summary.py`.

Purpose: persistent per-agent operational and financial profile.

Inventory lines store:

- `loaded_qty`
- `price_unit`
- `cost_price`
- computed `sold_qty`
- computed `remaining_qty`
- computed `subtotal_sold`

`remaining_qty` is computed as:

```text
max(0, loaded_qty + agent_ostatka_qty - all_time_confirmed_pos_sold_qty)
```

This means confirmed `van.pos.order.line` records are the source of truth for
sold quantity.

### `res.users`

Extended in `models/res_users.py`.

Important Mobile POS fields:

- `komissiya_foizi`
- `oylik_balansi`
- `default_taminotchi_id`
- `mijoz_ids`: clients assigned to the agent.

New non-share users automatically get a `van.agent.summary` record.

Agents are redirected to the Mobile POS after login through `_get_login_action`.

### `res.partner`

Extended in `models/res_partner.py`.

Important Mobile POS fields:

- `telegram_chat_id`
- `van_agent_id`
- `x_van_total_due`
- `x_van_balance`
- `x_van_ostatka_ids`

Customer debt is computed from:

- all `van.nasiya` records;
- all customer `van.payment` records;
- opening debt records in `van.ostatka.qarzi`.

The wallet-style formula is:

```text
wallet_balance = total_kirim - total_chiqim - total_nasiya - total_ostatka
x_van_total_due = abs(wallet_balance) if wallet_balance < 0 else 0
```

## 6. JSON-RPC API Reference

All endpoints below are defined in `controllers/main.py` and use `auth='user'`
unless noted otherwise.

### Agent Context

`_get_agent_id()` resolves the acting agent:

- Admin/system users may act as `request.session['acting_as_agent_id']`.
- Normal users act as `request.env.uid`.

This helper is used throughout the Mobile POS API so admin mode and agent mode
share the same endpoints.

### Agent Endpoints

#### `/van/pos/get_agents`

Returns all users in the van agent group. Admin only.

Response item:

```json
{
  "id": 12,
  "name": "Agent Name",
  "image_url": "/web/image?model=res.users&id=12&field=avatar_128"
}
```

#### `/van/pos/set_agent_session`

Input:

```json
{ "agent_id": 12 }
```

Sets the selected acting agent for admin users.

#### `/van/pos/get_current_agent`

Returns current acting agent metadata:

```json
{
  "id": 12,
  "summary_id": 34,
  "name": "Agent Name",
  "phone": "",
  "oylik_balansi": 0,
  "default_taminotchi_id": 5,
  "default_taminotchi_name": "Supplier",
  "image_url": "/web/image?model=res.users&id=12&field=avatar_128",
  "is_admin_mode": false,
  "is_admin": false
}
```

### Customer Endpoints

#### `/van/pos/get_clients`

Returns clients assigned to the acting agent via `agent.mijoz_ids`.

The list is sorted by latest POS sale or kirim date, then by name. A synthetic
cash-sale client is always inserted first:

```json
{
  "id": 0,
  "name": "Naqt savdo (Mijozisiz)",
  "balance": 0,
  "total_due": 0,
  "is_cash_sale": true,
  "last_transaction_date": "",
  "sort_order": 0
}
```

#### `/van/pos/create_client`

Input:

```json
{
  "name": "Apteka",
  "phone": "+998 90 123 45 67",
  "telegram_chat_id": "123456789"
}
```

Behavior:

- Validates required name and phone.
- Rejects duplicate phone.
- Creates `res.partner` with `x_is_van_customer=True`.
- Assigns the partner to the acting agent.

#### `/van/pos/get_client_report`

Input:

```json
{
  "client_id": 42,
  "date_from": "2026-04-01",
  "date_to": "2026-04-25"
}
```

Returns a chronological ledger, then reversed for newest-first display.

Includes:

- opening debt;
- confirmed POS sales;
- incoming customer payments;
- running balance after each transaction;
- sale line details for expandable rows.

`client_id=0` returns the cash-sale ledger for the acting agent.

#### `/van/pos/update_client_telegram_chat_id`

Updates the selected client's Telegram chat id. It rejects the synthetic cash
sale client.

### Inventory and Product Endpoints

#### `/van/pos/get_inventory`

Returns active remaining inventory for the acting agent.

Source:

- `van.agent.summary.active_inventory_line_ids`

Response item:

```json
{
  "product_id": 100,
  "name": "Product Name",
  "price": 15000,
  "remaining": 7,
  "image_url": "/web/image?model=van.product&id=100&field=image_1920",
  "sort_order": 0,
  "sold_qty": 12
}
```

The response is sorted by most sold products first, then by product name.

#### `/van/pos/get_all_products`

Returns all active `van.product` records for request and trip loading flows.

Response item:

```json
{
  "product_id": 100,
  "name": "Product Name",
  "price": 15000,
  "sale_price": 15000,
  "cost_price": 10000,
  "image_url": "/web/image?model=van.product&id=100&field=image_1920"
}
```

### Sale Endpoints

#### `/van/pos/submit_order`

Input:

```json
{
  "partner_id": 42,
  "lines": [
    { "product_id": 100, "qty": 2, "price": 15000 }
  ]
}
```

Behavior:

1. Creates a `van.pos.order` in draft.
2. Creates order lines.
3. Calls `action_confirm_order()`.
4. Returns order and debt identifiers.

Response:

```json
{
  "success": true,
  "order_id": 77,
  "nasiya_id": 88,
  "nasiya_amount": 30000
}
```

For cash sale, `partner_id` is false and no `van.nasiya` is created.

#### `/van/pos/submit_kirim`

Input:

```json
{
  "nasiya_id": 88,
  "amount": 30000,
  "payment_method": "cash"
}
```

Creates a `van.payment` linked to the newly created `van.nasiya`.

### Quick Payment Endpoints

#### `/van/pos/submit_quick_action`

Input for kirim:

```json
{
  "type": "kirim",
  "amount": 50000,
  "note": "Customer payment",
  "partner_id": 42
}
```

Input for chiqim:

```json
{
  "type": "chiqim",
  "amount": 10000,
  "note": "Fuel",
  "expense_type": "daily"
}
```

Creates `van.payment` with:

- `payment_type='in'` for kirim;
- `payment_type='out'` for chiqim;
- `payment_method='cash'`.

#### `/van/pos/get_payments`

Input:

```json
{ "payment_type": "in" }
```

Returns payment history for the acting agent. `payment_type` must be `in` or
`out`.

#### `/van/pos/save_payment`

Creates or updates a payment.

Input:

```json
{
  "payment_type": "in",
  "amount": 50000,
  "note": "Payment note",
  "payment_id": false,
  "partner_id": 42,
  "expense_type": "daily"
}
```

When `payment_id` is present, the endpoint updates an existing payment and
checks that it belongs to the acting agent.

#### `/van/pos/delete_payment`

Deletes a non-confirmed payment owned by the acting agent.

### Request Endpoints

#### `/van/pos/get_requests`

Returns up to 200 requests for the acting agent, ordered newest first.

Each request includes product lines, line prices, subtotals, partner metadata,
state, notes, and a localized date string.

#### `/van/pos/submit_request`

Input:

```json
{
  "partner_id": 42,
  "lines": [
    { "product_id": 100, "qty": 2 }
  ],
  "notes": "Customer asked for delivery tomorrow"
}
```

Creates a draft `van.request`.

#### `/van/pos/update_request`

Input:

```json
{
  "request_id": 55,
  "lines": [
    { "product_id": 100, "qty": 3, "price": 15000 }
  ]
}
```

Only draft requests can be edited. The endpoint clears existing lines and
rebuilds them from the payload.

#### `/van/pos/update_request_state`

Input:

```json
{ "request_id": 55, "state": "cancel" }
```

Writes the request state using `sudo()`.

#### `/van/pos/fulfill_request`

Marks a request as done after the POS sale is created.

This endpoint is intentionally idempotent if the request is already done.

### Trip Loading Endpoints

#### `/van/pos/get_taminotchis`

Returns all suppliers:

```json
[
  { "id": 5, "name": "Supplier" }
]
```

#### `/van/pos/submit_trip`

Input:

```json
{
  "agent_id": 12,
  "taminotchi_id": 5,
  "date": "2026-04-25",
  "note": "Morning load",
  "lines": [
    { "product_id": 100, "qty": 10, "price_unit": 10000 }
  ]
}
```

Behavior:

1. Finds an internal stock location.
2. Resolves selected supplier, or falls back to agent default supplier.
3. Creates a draft `van.trip`.
4. Creates trip lines.
5. Calls `action_validate()` to update agent inventory immediately.

Note: although the frontend preview allows editing displayed cost values, the
current endpoint writes `price_unit` from the product's stored `cost_price` and
`sale_price_unit` from the product's stored `list_price`.

#### `/van/pos/get_trips`

Returns the latest 100 trips for the acting agent, including loaded products,
total cost, quantity, state, note, and localized date.

### Client Ledger Edit Endpoints

These endpoints support the client report edit mode:

- `/van/mijoz/edit-kirim`
- `/van/mijoz/delete-kirim`
- `/van/mijoz/edit-sotuv`
- `/van/mijoz/delete-sotuv`

Behavior:

- Non-admin users can only edit/delete their own records.
- Confirmed sales can be edited if inventory remains sufficient for increased
  quantities.
- Deleting a sale unlinks and deletes the related `van.nasiya`.
- Partner debt stats are recomputed after edits/deletes.

## 7. Main Transaction Flows

### Cash Sale

1. Agent opens Mobile POS.
2. `get_clients` selects synthetic client `id=0` by default.
3. `get_inventory` loads sellable products with remaining quantity.
4. Agent adds products to `state.cart`.
5. Agent can edit quantity and `custom_price`.
6. `submitOrder()` posts `/van/pos/submit_order` with `partner_id=false`.
7. Backend creates and confirms `van.pos.order`.
8. No `van.nasiya` is created.
9. Frontend resets to the products screen and refreshes inventory.

### Customer Debt Sale

1. Agent selects a real customer.
2. Agent adds products to the cart.
3. `submitOrder()` posts `/van/pos/submit_order` with `partner_id`.
4. Backend creates and confirms `van.pos.order`.
5. `action_confirm_order()` creates `van.nasiya`.
6. Frontend moves to `kirim` screen and pre-fills payment with full debt amount.
7. Agent can submit full or partial payment through `/van/pos/submit_kirim`.
8. Frontend updates local client balance and resets.

### Quick Kirim

1. Agent opens kirim from the action menu or payment history.
2. Agent selects a client or `Turli Tushum`.
3. Frontend calls `/van/pos/save_payment` or `/van/pos/submit_quick_action`.
4. Backend creates `van.payment(payment_type='in')`.
5. Partner debt stats are reflected through recompute and subsequent reload.

### Chiqim

1. Agent opens chiqim.
2. Agent selects expense type:
   - `daily`: business operating expense;
   - `salary`: salary/commission withdrawal.
3. Frontend calls the payment endpoint.
4. Backend creates `van.payment(payment_type='out')`.
5. Agent financial summaries include this payment in balance calculations.

### Request to Sale

1. Agent opens `So'rovlar`.
2. `get_requests` loads requests assigned to the acting agent.
3. Agent opens a draft request and may edit lines.
4. `saveRequestEdits(false)` persists any edits.
5. `fulfillRequest()` builds the POS cart from request lines.
6. Frontend opens checkout with selected client and prefilled products.
7. After `submit_order` succeeds, frontend calls `/van/pos/fulfill_request`.
8. Request state becomes `done`.

### Product Loading

1. Agent opens `Mahsulot Yuklash`.
2. `get_trips`, `get_taminotchis`, and `get_all_products` provide required data.
3. Agent builds `tripCart`.
4. Frontend opens a preview modal.
5. `confirmYuklash()` posts `/van/pos/submit_trip`.
6. Backend creates and validates `van.trip`.
7. `van.agent.inventory.line.loaded_qty` is increased.
8. Future `get_inventory` calls include the new remaining stock.

## 8. Offline and PWA Behavior

### PWA Manifest

`static/manifest.json` defines:

- `start_url`: `/van/app`
- `display`: `standalone`
- `orientation`: `portrait`
- app icons: 192 and 512 px.

`views/web_layout_inherit.xml` injects the manifest and registers the service
worker globally.

### Service Worker

`static/service-worker.js` caches only the app icons at install time.

Fetch behavior:

- `/van/*` routes use network-first behavior and return cached response or
  `503 Offline` on failure.
- Images use cache-first behavior with background refresh.
- Other requests attempt network and fall back to cache.

### IndexedDB

The component opens `VanSalesAppDB` version 1.

Object stores:

- `clients`, key path `id`
- `inventory`, key path `product_id`
- `allProducts`, key path `id`
- `agent`, key path `id`
- `taminotchis`, key path `id`
- `syncQueue`, key path `offline_id`

Cached clients, inventory, agent metadata, suppliers, and sync queue entries are
loaded before server refreshes, so the POS can render usable sales data after a
reload without network. The `allProducts` store exists in the schema, but the
current `loadAllProducts()` implementation fetches from the server only and does
not save or restore that store. Also note that `/van/pos/get_all_products`
returns `product_id`, while the unused store is declared with key path `id`.

### Offline Queue

Offline transactions are queued in `syncQueue` with:

```json
{
  "offline_id": "uuid",
  "type": "sale",
  "timestamp": "2026-04-25T10:15:00.000Z",
  "data": {}
}
```

Supported queue types:

- `sale`
- `kirim`
- `chiqim`

When the browser returns online, `syncOfflineTransactions()` sends the queue to
`/van/pos/sync_offline`.

### Server Sync Idempotency

The server uses `offline_id` to avoid duplicates:

- sale duplicates are checked against `van.pos.order.offline_id`;
- payment duplicates are checked against `van.payment.offline_id`.

Successfully synced offline ids are removed from IndexedDB. Partial failures
remain in the queue and are reported in the browser console and toast.

### Offline Limitations

- Offline sales can be queued.
- Offline cash sales reset immediately and locally deduct cached inventory.
- Offline customer debt sales update cached client balance locally.
- Offline partial payment against the newly created nasiya is not supported,
  because no real `nasiya_id` exists until sync.
- Offline quick kirim and chiqim can be queued.
- Offline edits to existing payments, sales, or requests are not supported.

## 9. Security and Access Notes

- `/van/mobile-pos` and all `/van/pos/*` endpoints require an authenticated
  Odoo user.
- Admin users can act as agents through the session variable
  `acting_as_agent_id`.
- Most API methods use `sudo()` for reads and writes needed by the mobile flow,
  while relying on `_get_agent_id()` and explicit ownership checks where needed.
- `delete_payment` prevents deletion of confirmed payments.
- Client ledger edit/delete endpoints enforce owner checks for non-admin users.
- The public client request flow is separate and uses `/van/client/request` and
  `/van/client/submit_request` with public auth.

## 10. Important Implementation Notes

- Customer id `0` is a frontend/backend convention for synthetic cash sale
  display. It is never a real `res.partner`.
- `partner_id=False` on `van.pos.order` means cash sale without customer.
- Customer debt is not derived directly from POS order totals. It is derived
  through `van.nasiya`, `van.payment`, and opening debt records.
- Inventory remaining quantity is computed, not directly decremented, for sales.
- `get_inventory` only returns products with positive remaining quantity through
  `active_inventory_line_ids`.
- The product list used for loading and request editing comes from
  `/van/pos/get_all_products`, not from remaining inventory.
- Sale price can be customized in the mobile cart via `custom_price`.
- Commission is calculated from the product's original list price, not the
  custom sale price.
- Request fulfillment does not create the sale directly from the request model;
  the frontend converts the request into the normal checkout flow.
- Telegram notifications are sent after customer sales and customer kirim when
  `telegram_chat_id` is available.

## 11. Extension Guidelines

When adding a new Mobile POS feature:

1. Keep the acting-agent rule centralized through `_get_agent_id()`.
2. Add frontend state in one clearly named group inside `setup()`.
3. Prefer existing JSON-RPC patterns over direct model calls from the frontend.
4. Cache read-heavy reference data in IndexedDB if it is required offline.
5. Add `offline_id` if the feature can create records offline.
6. Make server sync idempotent before enabling offline creation.
7. Recompute or reload client balances after any payment or debt mutation.
8. Avoid manual inventory mutation for sales; let POS lines drive computed
   remaining quantities.
9. Use `van.payment` for cash movement and `van.nasiya` for customer debt.
10. Check both normal agent mode and admin acting-as-agent mode.

## 12. Debugging Checklist

### POS Does Not Open

- Confirm the user belongs to `group_van_agent` or `group_van_admin`.
- Confirm `action_van_mobile_pos_app` exists.
- Check browser console for asset bundle errors.
- Verify `van_mobile_pos.js` and `van_mobile_pos.xml` are included in
  `web.assets_backend`.

### Agent Has No Products

- Check that a `van.agent.summary` exists for the agent.
- Check `van.agent.inventory.line.loaded_qty`.
- Check `van.agent.ostatka` opening inventory.
- Check confirmed `van.pos.order.line` records for all-time sold quantity.
- Use `/van/debug/check-inventory?agent_id=<id>` as admin.

### Client Debt Looks Wrong

- Recompute partner `_compute_van_nasiya_stats()`.
- Check `van.nasiya` records for the partner.
- Check `van.payment` records for the partner.
- Check `van.ostatka.qarzi` opening debt records.

### Offline Sync Duplicates or Fails

- Check browser IndexedDB `syncQueue`.
- Check `offline_id` values on `van.pos.order` or `van.payment`.
- Check server response from `/van/pos/sync_offline`.
- Verify inventory was still sufficient when queued sales reached the server.

### Request Fulfillment Does Not Mark Done

- Confirm `state.sourceSorovId` is set before checkout.
- Confirm `/van/pos/fulfill_request` is called after successful sale creation.
- Check whether the request was already cancelled or edited by another user.
