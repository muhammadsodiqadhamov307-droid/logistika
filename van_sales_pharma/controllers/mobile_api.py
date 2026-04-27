from odoo import http, fields
from odoo.http import request
import datetime
import logging

_logger = logging.getLogger(__name__)


class VanMobileApiController(http.Controller):
    """Token-based API for the native offline-first Android client."""

    def _mobile_partner_balance(self, partner):
        if not partner:
            return {'wallet_balance': 0.0, 'total_due': 0.0}
        orders = request.env['van.pos.order'].sudo().search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'done'),
        ])
        payments = request.env['van.payment'].sudo().search([
            ('partner_id', '=', partner.id),
        ])
        total_sales = sum(orders.mapped('amount_total'))
        total_kirim = sum(payments.filtered(lambda p: p.payment_type == 'in').mapped('amount'))
        total_chiqim = sum(payments.filtered(lambda p: p.payment_type == 'out').mapped('amount'))
        total_ostatka = sum(partner.x_van_ostatka_ids.mapped('amount'))
        wallet_balance = total_kirim - total_chiqim - total_sales - total_ostatka
        return {
            'wallet_balance': wallet_balance,
            'total_due': abs(wallet_balance) if wallet_balance < 0 else 0.0,
        }

    def _bearer_token(self):
        auth_header = request.httprequest.headers.get('Authorization', '') or ''
        if auth_header.lower().startswith('bearer '):
            return auth_header.split(' ', 1)[1].strip()
        return None

    def _user_from_token(self):
        token = self._bearer_token()
        if not token:
            return None
        return request.env['res.users'].sudo().search([
            ('van_mobile_api_token', '=', token)
        ], limit=1)

    def _ensure_mobile_user(self):
        user = self._user_from_token()
        if not user:
            return None, {'success': False, 'error': 'Invalid or missing mobile token'}
        is_allowed = (
            user.has_group('van_sales_pharma.group_van_agent')
            or user.has_group('van_sales_pharma.group_van_admin')
            or user.has_group('base.group_system')
        )
        if not is_allowed:
            return None, {'success': False, 'error': 'User is not allowed to use Mobile POS'}
        return user, None

    def _client_report_payload(self, user, partner=None):
        """Build the same client ledger used by the web Mobile POS report."""
        import pytz

        user_tz = pytz.timezone(user.tz or 'Asia/Tashkent')
        agent_id = user.id
        is_cash_sale = not partner
        client_name = "Naqt savdo (Mijozisiz)" if is_cash_sale else partner.name
        total_due = 0.0 if is_cash_sale else self._mobile_partner_balance(partner)['total_due']
        transactions = []

        def local_dt(value):
            value = value or fields.Datetime.now()
            if isinstance(value, str):
                value = fields.Datetime.from_string(value)
            if value.tzinfo:
                return value.astimezone(user_tz)
            return pytz.utc.localize(value).astimezone(user_tz)

        if partner:
            for ostatka in partner.x_van_ostatka_ids:
                if ostatka.amount > 0:
                    date_value = ostatka.date or datetime.date.today()
                    transactions.append({
                        'id': ostatka.id,
                        'date_obj': user_tz.localize(datetime.datetime.combine(date_value, datetime.time.min)),
                        'date_label': date_value.strftime('%d.%m.%Y'),
                        'turi': 'boshlangich_qarz',
                        'turi_label': "Boshlang'ich qarz",
                        'summa': ostatka.amount,
                        'is_debt': True,
                        'lines': [],
                    })

        order_domain = [('partner_id', '=', partner.id if partner else False), ('state', '=', 'done')]
        if not partner:
            order_domain.append(('agent_id', '=', agent_id))
        orders = request.env['van.pos.order'].sudo().search(order_domain, order='date asc')
        for order in orders:
            if order.amount_total > 0:
                order_dt = local_dt(order.date)
                transactions.append({
                    'id': order.id,
                    'date_obj': order_dt,
                    'date_label': order_dt.strftime('%d.%m.%Y %H:%M:%S'),
                    'turi': 'sotuv',
                    'turi_label': 'Sotuv',
                    'name': order.name or '',
                    'partner_name': order.partner_id.name if order.partner_id else '',
                    'state': order.state or '',
                    'summa': order.amount_total,
                    'is_debt': True,
                    'lines': [{
                        'id': line.id,
                        'product_id': line.product_id.id,
                        'name': line.product_id.name or '',
                        'qty': line.qty,
                        'price': line.price_unit,
                        'subtotal': line.qty * line.price_unit,
                    } for line in order.line_ids],
                })

        pay_domain = [('partner_id', '=', partner.id if partner else False), ('payment_type', '=', 'in')]
        if not partner:
            pay_domain.append(('agent_id', '=', agent_id))
        payments = request.env['van.payment'].sudo().search(pay_domain, order='date asc')
        for payment in payments:
            if payment.amount > 0:
                payment_dt = local_dt(payment.date)
                transactions.append({
                    'id': payment.id,
                    'date_obj': payment_dt,
                    'date_label': payment_dt.strftime('%d.%m.%Y %H:%M:%S'),
                    'turi': 'kirim',
                    'turi_label': 'Kirim',
                    'name': payment.name or '',
                    'partner_name': payment.partner_id.name if payment.partner_id else '',
                    'payment_method': payment.payment_method or '',
                    'state': payment.state or '',
                    'summa': payment.amount,
                    'is_debt': False,
                    'lines': [],
                })

        transactions.sort(key=lambda tx: tx['date_obj'])
        running_balance = 0.0
        for tx in transactions:
            if tx['is_debt']:
                running_balance += tx['summa']
            else:
                running_balance -= tx['summa']
            tx['balance'] = running_balance
            del tx['date_obj']
        transactions.reverse()

        return {
            'client_id': 0 if is_cash_sale else partner.id,
            'client_name': client_name,
            'total_due': total_due,
            'phone': '' if is_cash_sale else (partner.phone or ''),
            'telegram_chat_id': '' if is_cash_sale else (partner.telegram_chat_id or ''),
            'transactions': transactions,
        }

    def _payment_history_payload(self, user, payment_type='out'):
        import pytz

        user_tz = pytz.timezone(user.tz or 'Asia/Tashkent')
        payments = request.env['van.payment'].sudo().search([
            ('agent_id', '=', user.id),
            ('payment_type', '=', payment_type),
        ], order='date desc')
        result = []
        for payment in payments:
            local_date_str = ''
            if payment.date:
                if getattr(payment.date, 'tzinfo', None):
                    local_dt = payment.date.astimezone(user_tz)
                else:
                    local_dt = pytz.utc.localize(payment.date).astimezone(user_tz)
                local_date_str = local_dt.strftime('%d.%m.%Y %H:%M:%S')
            result.append({
                'id': payment.id,
                'name': payment.name or '',
                'payment_type': payment.payment_type,
                'amount': payment.amount,
                'date': local_date_str,
                'note': payment.note or '',
                'expense_type': payment.expense_type or '',
                'payment_method': payment.payment_method or '',
                'partner_id': payment.partner_id.id if payment.partner_id else False,
                'partner_name': payment.partner_id.name if payment.partner_id else '',
                'state': payment.state or '',
            })
        return result

    def _bootstrap_payload(self, user):
        import pytz

        agent_id = user.id
        user_tz = pytz.timezone(user.tz or 'Asia/Tashkent')
        summary = request.env['van.agent.summary'].sudo().search([('agent_id', '=', agent_id)], limit=1)
        if not summary:
            summary = request.env['van.agent.summary'].sudo().create({'agent_id': agent_id})

        partners = user.sudo().mijoz_ids
        hidden_partners = partners.filtered(lambda p: not p.x_is_van_customer or p.customer_rank < 1)
        if hidden_partners:
            hidden_partners.write({'x_is_van_customer': True, 'customer_rank': 1})
        partners.sudo()._compute_van_nasiya_stats()

        partner_map = {partner.id: partner for partner in partners}
        sorted_partner_rows = []
        if partner_map:
            query = """
                SELECT p.id, GREATEST(MAX(o.date), MAX(pay.date)) AS last_transaction_date
                FROM res_partner p
                LEFT JOIN van_pos_order o ON o.partner_id = p.id AND o.agent_id = %s AND o.state = 'done'
                LEFT JOIN van_payment pay ON pay.partner_id = p.id AND pay.agent_id = %s AND pay.payment_type = 'in'
                WHERE p.id IN %s
                GROUP BY p.id
                ORDER BY last_transaction_date DESC NULLS LAST, p.name ASC
            """
            request.env.cr.execute(query, (agent_id, agent_id, tuple(partner_map.keys())))
            sorted_partner_rows = request.env.cr.fetchall()

        clients = [{
            'id': 0,
            'name': "Naqt savdo (Mijozisiz)",
            'balance': 0.0,
            'total_due': 0.0,
            'is_cash_sale': True,
            'last_transaction_date': '',
            'sort_order': 0,
        }]
        for index, (partner_id, last_tx) in enumerate(sorted_partner_rows, start=1):
            partner = partner_map.get(partner_id)
            if not partner:
                continue
            last_tx_str = ''
            if last_tx:
                if last_tx.tzinfo:
                    last_tx_str = last_tx.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')
                else:
                    last_tx_str = pytz.utc.localize(last_tx).astimezone(user_tz).strftime('%Y-%m-%d %H:%M')
            fresh_balance = self._mobile_partner_balance(partner)
            clients.append({
                'id': partner.id,
                'name': partner.name,
                'phone': partner.phone or '',
                'balance': fresh_balance['wallet_balance'],
                'total_due': fresh_balance['total_due'],
                'telegram_chat_id': partner.telegram_chat_id or '',
                'last_transaction_date': last_tx_str,
                'sort_order': index,
            })
        client_reports = [self._client_report_payload(user)]
        for partner in partners:
            client_reports.append(self._client_report_payload(user, partner))
        payments = self._payment_history_payload(user, 'out')

        inventory = []
        for index, line in enumerate(summary.active_inventory_line_ids):
            inventory.append({
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'price': line.price_unit,
                'remaining': line.remaining_qty,
                'image_url': f'/web/image?model=van.product&id={line.product_id.id}&field=image_1920',
                'sort_order': index,
                'sold_qty': line.sold_qty,
            })

        products = []
        for product in request.env['van.product'].sudo().search([('active', '=', True)]):
            products.append({
                'product_id': product.id,
                'name': product.display_name,
                'price': product.list_price,
                'sale_price': product.list_price,
                'cost_price': product.cost_price,
                'image_url': f'/web/image?model=van.product&id={product.id}&field=image_1920',
            })

        taminotchis = [{
            'id': t.id,
            'name': t.name,
        } for t in request.env['van.taminotchi'].sudo().search([])]

        requests = []
        reqs = request.env['van.request'].sudo().search([('agent_id', '=', agent_id)], order='date desc', limit=200)
        for req in reqs:
            lines = []
            total = 0.0
            for line in req.line_ids:
                price = line.price or line.product_id.list_price or 0.0
                subtotal = line.subtotal or (line.qty * price)
                total += subtotal
                lines.append({
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.name,
                    'qty': line.qty,
                    'price': price,
                    'subtotal': subtotal,
                    'image_url': f'/web/image?model=van.product&id={line.product_id.id}&field=image_1920',
                })
            local_date_str = ''
            if req.date:
                if req.date.tzinfo:
                    local_date_str = req.date.astimezone(user_tz).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    local_date_str = pytz.utc.localize(req.date).astimezone(user_tz).strftime('%Y-%m-%d %H:%M:%S')
            requests.append({
                'id': req.id,
                'name': req.name,
                'partner_id': req.partner_id.id if req.partner_id else False,
                'partner_name': req.partner_id.name if req.partner_id else '',
                'date': local_date_str,
                'state': req.state,
                'total_amount': total,
                'notes': req.notes or '',
                'lines': lines,
            })

        trips = []
        trip_records = request.env['van.trip'].sudo().search([('agent_id', '=', agent_id)], order='date desc, id desc', limit=100)
        for trip in trip_records:
            trips.append({
                'id': trip.id,
                'name': trip.name,
                'date': fields.Datetime.to_string(trip.date) if trip.date else '',
                'agent_name': trip.agent_id.name if trip.agent_id else '',
                'state': trip.state,
                'total_cost': trip.amount_cost_total,
                'total_qty': trip.x_loaded_qty,
                'note': trip.note or '',
                'lines': [{
                    'product_name': line.product_id.name,
                    'qty': line.loaded_qty,
                    'price': line.price_unit,
                    'subtotal': line.loaded_qty * line.product_id.cost_price,
                    'image_url': f'/web/image?model=van.product&id={line.product_id.id}&field=image_1920',
                } for line in trip.trip_line_ids],
            })

        return {
            'success': True,
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'agent': {
                'id': user.id,
                'summary_id': summary.id,
                'name': user.name,
                'phone': user.phone or user.x_phone or '',
                'oylik_balansi': user.oylik_balansi,
                'komissiya_foizi': user.komissiya_foizi or 0.0,
                'is_admin': bool(
                    user.has_group('van_sales_pharma.group_van_admin')
                    or user.has_group('base.group_system')
                ),
                'default_taminotchi_id': user.default_taminotchi_id.id if user.default_taminotchi_id else False,
                'default_taminotchi_name': user.default_taminotchi_id.name if user.default_taminotchi_id else '',
                'image_url': f'/web/image?model=res.users&id={user.id}&field=avatar_128',
            },
            'clients': clients,
            'client_reports': client_reports,
            'payments': payments,
            'inventory': inventory,
            'products': products,
            'taminotchis': taminotchis,
            'requests': requests,
            'trips': trips,
        }

    @http.route('/van/mobile/api/rebuild-inventory', type='jsonrpc', auth='public', csrf=False)
    def mobile_rebuild_inventory(self):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            summary = request.env['van.agent.summary'].sudo().search([('agent_id', '=', user.id)], limit=1)
            if not summary:
                summary = request.env['van.agent.summary'].sudo().create({'agent_id': user.id})
            summary.sudo().action_rebuild_inventory()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("mobile_rebuild_inventory failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/login', type='jsonrpc', auth='public', csrf=False)
    def mobile_login(self, db=None, login=None, password=None):
        try:
            db_name = db or request.db
            if not db_name:
                return {'success': False, 'error': 'Database name is required'}
            if not login or not password:
                return {'success': False, 'error': 'Login and password are required'}

            try:
                auth_info = request.session.authenticate(request.env, {
                    'login': login,
                    'password': password,
                    'type': 'password',
                })
                uid = auth_info.get('uid') or request.session.uid
            except TypeError:
                uid = request.session.authenticate(db_name, login, password)
            if not uid:
                return {'success': False, 'error': 'Invalid login or password'}

            if hasattr(request, 'update_env'):
                request.update_env(user=uid)

            user = request.env['res.users'].sudo().browse(uid)
            is_allowed = (
                user.has_group('van_sales_pharma.group_van_agent')
                or user.has_group('van_sales_pharma.group_van_admin')
                or user.has_group('base.group_system')
            )
            if not is_allowed:
                return {'success': False, 'error': 'User is not allowed to use Mobile POS'}

            token = user.van_mobile_api_token or user._van_mobile_reset_api_token()
            bootstrap = self._bootstrap_payload(user)
            return {
                'success': True,
                'token': token,
                'database': db_name,
                'user_id': user.id,
                'user_name': user.name,
                'bootstrap': bootstrap,
            }
        except Exception as e:
            _logger.exception("Native mobile login failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/bootstrap', type='jsonrpc', auth='public', csrf=False)
    def mobile_bootstrap(self):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            return self._bootstrap_payload(user)
        except Exception as e:
            _logger.exception("Native mobile bootstrap failed")
            return {'success': False, 'error': str(e)}

    def _mobile_can_modify_agent_record(self, user, record):
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        return is_admin or record.agent_id.id == user.id

    @http.route('/van/mobile/api/update-client-telegram', type='jsonrpc', auth='public', csrf=False)
    def mobile_update_client_telegram(self, client_id=None, telegram_chat_id=''):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            client_id = int(client_id or 0)
            if not client_id:
                return {'success': False, 'error': "Naqt savdo uchun Telegram Chat ID saqlanmaydi"}
            partner = request.env['res.partner'].sudo().browse(client_id)
            if not partner.exists() or partner not in user.sudo().mijoz_ids:
                return {'success': False, 'error': 'Mijoz topilmadi'}
            chat_id = (telegram_chat_id or '').strip()
            partner.sudo().write({'telegram_chat_id': chat_id})
            return {'success': True, 'telegram_chat_id': chat_id, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile telegram update failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/create-client', type='jsonrpc', auth='public', csrf=False)
    def mobile_create_client(self, name='', phone='', telegram_chat_id=''):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            name = (name or '').strip()
            phone = (phone or '').strip()
            telegram_chat_id = (telegram_chat_id or '').strip()

            if not name:
                return {'success': False, 'error': 'Mijoz nomi kiritilmagan'}
            if not phone:
                return {'success': False, 'error': 'Telefon raqami kiritilmagan'}

            existing = request.env['res.partner'].sudo().search([('phone', '=', phone)], limit=1)
            if existing:
                return {'success': False, 'error': 'Bu telefon raqami bilan mijoz allaqachon mavjud'}

            new_client = request.env['res.partner'].sudo().create({
                'name': name,
                'phone': phone,
                'telegram_chat_id': telegram_chat_id,
                'x_is_van_customer': True,
                'van_agent_id': user.id,
                'user_id': user.id,
            })
            return {
                'success': True,
                'client_id': new_client.id,
                'message': "Mijoz yaratildi",
                'bootstrap': self._bootstrap_payload(user),
            }
        except Exception as e:
            _logger.exception("Native mobile create client failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/create-request', type='jsonrpc', auth='public', csrf=False)
    def mobile_create_request(self, partner_id=None, lines=None, notes=''):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            partner = request.env['res.partner'].sudo().browse(int(partner_id or 0))
            if not partner.exists():
                return {'success': False, 'error': "Mijoz tanlanmagan."}

            request_lines = lines or []
            prepared_lines = []
            for line in request_lines:
                product_id = int(line.get('product_id') or 0)
                qty = float(line.get('qty') or 0)
                price = float(line.get('price') or 0)
                if not product_id or qty <= 0:
                    continue
                product = request.env['van.product'].sudo().browse(product_id)
                if not product.exists():
                    continue
                prepared_lines.append((0, 0, {
                    'product_id': product.id,
                    'qty': qty,
                    'price': price if price > 0 else product.list_price,
                }))

            if not prepared_lines and not (notes or '').strip():
                return {'success': False, 'error': "Iltimos mahsulot tanlang yoki izoh kiriting."}

            new_request = request.env['van.request'].sudo().create({
                'agent_id': user.id,
                'partner_id': partner.id,
                'notes': (notes or '').strip(),
                'line_ids': prepared_lines,
            })
            return {
                'success': True,
                'request_id': new_request.id,
                'bootstrap': self._bootstrap_payload(user),
            }
        except Exception as e:
            _logger.exception("Native mobile create request failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/update-request-state', type='jsonrpc', auth='public', csrf=False)
    def mobile_update_request_state(self, request_id=None, state='draft'):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            req = request.env['van.request'].sudo().browse(int(request_id or 0))
            if not req.exists() or req.agent_id.id != user.id:
                return {'success': False, 'error': "So'rov topilmadi."}
            if state not in ('draft', 'done', 'cancel'):
                return {'success': False, 'error': "Noto'g'ri holat."}
            vals = {'state': state}
            if state == 'done':
                vals['fulfilled_date'] = fields.Datetime.now()
            req.sudo().write(vals)
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile update request state failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/update-request', type='jsonrpc', auth='public', csrf=False)
    def mobile_update_request(self, request_id=None, lines=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            req = request.env['van.request'].sudo().browse(int(request_id or 0))
            if not req.exists() or req.agent_id.id != user.id:
                return {'success': False, 'error': "So'rov topilmadi."}
            if req.state != 'draft':
                return {'success': False, 'error': "Faqat kutilayotgan so'rovlarni o'zgartirish mumkin."}

            line_commands = [(5, 0, 0)]
            for line in (lines or []):
                product_id = int(line.get('product_id') or 0)
                qty = float(line.get('qty') or 0)
                price = float(line.get('price') or 0)
                if not product_id or qty <= 0:
                    continue
                product = request.env['van.product'].sudo().browse(product_id)
                if not product.exists():
                    continue
                line_commands.append((0, 0, {
                    'product_id': product.id,
                    'qty': qty,
                    'price': price if price > 0 else product.list_price,
                }))
            req.sudo().write({'line_ids': line_commands})
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile update request failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/create-trip', type='jsonrpc', auth='public', csrf=False)
    def mobile_create_trip(self, date='', note='', lines=None, taminotchi_id=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            trip_lines = lines or []
            if not isinstance(trip_lines, list):
                return {'success': False, 'error': "Mahsulotlar ro'yxati noto'g'ri"}
            if not trip_lines:
                return {'success': False, 'error': "Hech qanday mahsulot tanlanmadi!"}

            location = request.env['stock.location'].sudo().search([
                ('usage', '=', 'internal'),
                ('company_id', 'in', [request.env.company.id, False])
            ], limit=1)
            if not location:
                return {'success': False, 'error': "Ombor topilmadi!"}

            if taminotchi_id:
                taminotchi = request.env['van.taminotchi'].sudo().browse(int(taminotchi_id))
            else:
                taminotchi = user.default_taminotchi_id

            if not taminotchi or not taminotchi.exists():
                return {'success': False, 'error': "Sizga taminotchi biriktirilmagan. Iltimos, administratorga murojaat qiling."}

            trip_date = (date or '').strip()
            if trip_date and len(trip_date) == 10:
                current_time = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
                trip_date = f"{trip_date} {current_time}"
            elif not trip_date:
                trip_date = fields.Datetime.to_string(fields.Datetime.now())

            prepared_lines = []
            for line in trip_lines:
                product_id = int(line.get('product_id') or 0)
                qty = float(line.get('qty') or 0)
                price_unit = float(line.get('price_unit') or 0)
                if not product_id or qty <= 0:
                    continue
                product = request.env['van.product'].sudo().browse(product_id)
                if not product.exists():
                    continue
                prepared_lines.append((0, 0, {
                    'product_id': product.id,
                    'loaded_qty': qty,
                    'price_unit': price_unit if price_unit > 0 else product.cost_price,
                    'sale_price_unit': product.list_price,
                }))

            if not prepared_lines:
                return {'success': False, 'error': "Saqlash uchun yaroqli mahsulot topilmadi."}

            trip_vals = {
                'taminotchi_id': taminotchi.id,
                'agent_id': user.id,
                'location_id': location.id,
                'date': trip_date,
                'note': (note or '').strip(),
                'state': 'draft',
                'trip_line_ids': prepared_lines,
            }
            new_trip = request.env['van.trip'].sudo().create(trip_vals)
            new_trip.sudo().action_validate()

            return {
                'success': True,
                'trip_id': new_trip.id,
                'trip_name': new_trip.name,
                'bootstrap': self._bootstrap_payload(user),
            }
        except Exception as e:
            _logger.exception("Native mobile create trip failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/edit-kirim', type='jsonrpc', auth='public', csrf=False)
    def mobile_edit_kirim(self, payment_id=None, new_amount=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            payment = request.env['van.payment'].sudo().browse(int(payment_id or 0))
            if not payment.exists() or payment.payment_type != 'in':
                return {'success': False, 'error': "To'lov topilmadi yoki bu kirim emas."}
            if not self._mobile_can_modify_agent_record(user, payment):
                return {'success': False, 'error': "Faqat o'zingizning kiritgan to'lovingizni tahrirlay olasiz."}
            amount = float(new_amount)
            if amount < 0:
                return {'success': False, 'error': "Noto'g'ri summa kiritildi."}
            payment.sudo().write({'amount': amount})
            if payment.partner_id:
                payment.partner_id.sudo()._compute_van_nasiya_stats()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile edit kirim failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/delete-kirim', type='jsonrpc', auth='public', csrf=False)
    def mobile_delete_kirim(self, payment_id=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            payment = request.env['van.payment'].sudo().browse(int(payment_id or 0))
            if not payment.exists() or payment.payment_type != 'in':
                return {'success': False, 'error': "To'lov topilmadi yoki bu kirim emas."}
            if not self._mobile_can_modify_agent_record(user, payment):
                return {'success': False, 'error': "Faqat o'zingizning kiritgan to'lovingizni o'chira olasiz."}
            partner = payment.partner_id
            payment.sudo().unlink()
            if partner:
                partner.sudo()._compute_van_nasiya_stats()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile delete kirim failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/edit-chiqim', type='jsonrpc', auth='public', csrf=False)
    def mobile_edit_chiqim(self, payment_id=None, new_amount=None, note='', expense_type='daily'):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            payment = request.env['van.payment'].sudo().browse(int(payment_id or 0))
            if not payment.exists() or payment.payment_type != 'out':
                return {'success': False, 'error': "To'lov topilmadi yoki bu chiqim emas."}
            if not self._mobile_can_modify_agent_record(user, payment):
                return {'success': False, 'error': "Faqat o'zingizning chiqimingizni tahrirlay olasiz."}
            amount = float(new_amount)
            if amount <= 0:
                return {'success': False, 'error': "Noto'g'ri summa kiritildi."}
            payment.sudo().write({
                'amount': amount,
                'note': (note or '').strip(),
                'expense_type': expense_type or 'daily',
            })
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile edit chiqim failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/delete-chiqim', type='jsonrpc', auth='public', csrf=False)
    def mobile_delete_chiqim(self, payment_id=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            payment = request.env['van.payment'].sudo().browse(int(payment_id or 0))
            if not payment.exists() or payment.payment_type != 'out':
                return {'success': False, 'error': "To'lov topilmadi yoki bu chiqim emas."}
            if not self._mobile_can_modify_agent_record(user, payment):
                return {'success': False, 'error': "Faqat o'zingizning chiqimingizni o'chira olasiz."}
            payment.sudo().unlink()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile delete chiqim failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/edit-sotuv', type='jsonrpc', auth='public', csrf=False)
    def mobile_edit_sotuv(self, order_id=None, lines=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            order = request.env['van.pos.order'].sudo().browse(int(order_id or 0))
            if not order.exists():
                return {'success': False, 'error': 'Sotuv topilmadi.'}
            if not self._mobile_can_modify_agent_record(user, order):
                return {'success': False, 'error': "Faqat o'zingizning sotuvingizni tahrirlay olasiz."}
            if order.state != 'done':
                return {'success': False, 'error': 'Faqat tasdiqlangan sotuvlarni tahrirlash mumkin.'}

            updates = {}
            for line in lines or []:
                line_id = int(line.get('line_id') or 0)
                updates[line_id] = {
                    'qty': float(line.get('qty') or 0),
                    'price': float(line.get('price') or 0),
                }

            for line in order.line_ids:
                if line.id not in updates:
                    continue
                new_qty = updates[line.id]['qty']
                new_price = updates[line.id]['price']
                if new_qty < 0 or new_price < 0:
                    return {'success': False, 'error': "Miqdor/Narx manfiy bo'lmaydi"}

                qty_diff = new_qty - line.qty
                if qty_diff > 0:
                    summary = request.env['van.agent.summary'].sudo().search([('agent_id', '=', order.agent_id.id)], limit=1)
                    inv = request.env['van.agent.inventory.line'].sudo().search([
                        ('summary_id', '=', summary.id),
                        ('product_id', '=', line.product_id.id),
                    ], limit=1) if summary else request.env['van.agent.inventory.line']
                    available_qty = inv.remaining_qty if inv else 0.0
                    if available_qty < qty_diff:
                        return {'success': False, 'error': f"Agentda {line.product_id.name} uchun yetarli qoldiq yo'q."}

                line.sudo().write({'qty': new_qty, 'price_unit': new_price})

            order.sudo()._compute_amount_total()
            if order.nasiya_id:
                order.nasiya_id.sudo().write({'amount_total': order.amount_total})
            if order.partner_id:
                order.partner_id.sudo()._compute_van_nasiya_stats()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile edit sotuv failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/delete-sotuv', type='jsonrpc', auth='public', csrf=False)
    def mobile_delete_sotuv(self, order_id=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        try:
            order = request.env['van.pos.order'].sudo().browse(int(order_id or 0))
            if not order.exists():
                return {'success': False, 'error': 'Sotuv topilmadi.'}
            if not self._mobile_can_modify_agent_record(user, order):
                return {'success': False, 'error': "Faqat o'zingizning sotuvingizni o'chira olasiz."}
            partner = order.partner_id
            if order.nasiya_id:
                nasiya = order.nasiya_id.sudo()
                order.sudo().write({'nasiya_id': False})
                nasiya.unlink()
            if order.line_ids:
                order.line_ids.sudo().unlink()
            order.sudo().unlink()
            if partner:
                partner.sudo()._compute_van_nasiya_stats()
            return {'success': True, 'bootstrap': self._bootstrap_payload(user)}
        except Exception as e:
            _logger.exception("Native mobile delete sotuv failed")
            return {'success': False, 'error': str(e)}

    @http.route('/van/mobile/api/sync', type='jsonrpc', auth='public', csrf=False)
    def mobile_sync(self, transactions=None):
        user, error = self._ensure_mobile_user()
        if error:
            return error
        if not transactions:
            return {'success': True, 'status': 'success', 'synced': [], 'errors': []}

        synced = []
        errors = []
        env = request.env

        for index, tx in enumerate(transactions):
            offline_id = tx.get('offline_id')
            tx_type = tx.get('type')
            data = tx.get('data') or {}
            if not offline_id:
                errors.append({'index': index, 'error': 'Missing offline_id'})
                continue

            try:
                if tx_type == 'sale':
                    existing = env['van.pos.order'].sudo().search([('offline_id', '=', offline_id)], limit=1)
                    if existing:
                        synced.append(offline_id)
                        continue
                    lines = data.get('lines') or []
                    if not lines:
                        raise ValueError('No products in sale')
                    partner_id = data.get('partner_id') or False
                    if partner_id == 0:
                        partner_id = False
                    vals = {
                        'partner_id': partner_id,
                        'agent_id': user.id,
                        'offline_id': offline_id,
                        'line_ids': [(0, 0, {
                            'product_id': line['product_id'],
                            'qty': line['qty'],
                            'price_unit': line['price'],
                        }) for line in lines],
                    }
                    order = env['van.pos.order'].sudo().create(vals)
                    order.action_confirm_order()
                    source_request_id = int(data.get('source_request_id') or 0)
                    if source_request_id:
                        req = env['van.request'].sudo().browse(source_request_id)
                        if req.exists():
                            req.sudo().write({
                                'state': 'done',
                                'fulfilled_date': fields.Datetime.now(),
                                'sale_order_id': order.id,
                            })
                    synced.append(offline_id)
                elif tx_type in ('kirim', 'chiqim'):
                    existing = env['van.payment'].sudo().search([('offline_id', '=', offline_id)], limit=1)
                    if existing:
                        synced.append(offline_id)
                        continue
                    payment_type = 'in' if tx_type == 'kirim' else 'out'
                    partner_id = data.get('partner_id') or False
                    if partner_id == 0:
                        partner_id = False
                    vals = {
                        'payment_type': payment_type,
                        'agent_id': user.id,
                        'offline_id': offline_id,
                        'amount': float(data.get('amount') or 0),
                        'note': data.get('note') or '',
                        'payment_method': data.get('payment_method') or 'cash',
                    }
                    if payment_type == 'in':
                        vals['partner_id'] = partner_id
                    else:
                        vals['expense_type'] = data.get('expense_type') or 'daily'
                    env['van.payment'].sudo().create(vals)
                    synced.append(offline_id)
                else:
                    errors.append({'offline_id': offline_id, 'error': f'Unknown transaction type {tx_type}'})
            except Exception as e:
                _logger.exception("Native mobile sync failed for %s", offline_id)
                errors.append({'offline_id': offline_id, 'error': str(e)})

        return {
            'success': True,
            'status': 'success' if not errors else 'partial_success',
            'synced': synced,
            'errors': errors,
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
            'bootstrap': self._bootstrap_payload(user),
        }
