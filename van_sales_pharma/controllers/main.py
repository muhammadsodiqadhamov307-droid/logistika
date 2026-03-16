from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
import logging
import datetime

_logger = logging.getLogger(__name__)

class VanPosController(http.Controller):

    def _get_agent_id(self):
        """Returns the acting agent ID if an admin has selected one, otherwise the actual user ID."""
        if request.env.user.has_group('van_sales_pharma.group_van_admin'):
            acting_id = request.session.get('acting_as_agent_id')
            if acting_id:
                return acting_id
        return request.env.uid

    @http.route('/van/mobile-pos', type='http', auth='user')
    def mobile_pos_entry(self):
        user = request.env.user
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        
        if is_admin:
            acting_agent_id = request.session.get('acting_as_agent_id')
            if not acting_agent_id:
                agent_group = request.env.ref('van_sales_pharma.group_van_agent')
                request.env.cr.execute("SELECT uid FROM res_groups_users_rel WHERE gid = %s", (agent_group.id,))
                user_ids = [row[0] for row in request.env.cr.fetchall()]
                agents = request.env['res.users'].sudo().browse(user_ids)
                return request.render('van_sales_pharma.agent_select_template', {'agents': agents})
                
        # If normal agent, or admin with an already selected agent session, boot the OWL app
        return request.redirect('/web#action=van_sales_pharma.action_van_mobile_pos_app')

    @http.route('/van/mobile-pos/select-agent', type='http', auth='user', methods=['GET'], csrf=False)
    def select_agent(self, agent_id=None, **kwargs):
        user = request.env.user
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        if not is_admin:
            return request.redirect('/van/mobile-pos')
        if agent_id:
            request.session['acting_as_agent_id'] = int(agent_id)
        return request.redirect('/van/mobile-pos')

    @http.route('/van/mobile-pos/change-agent', type='http', auth='user')
    def mobile_pos_change_agent(self):
        if request.session.get('acting_as_agent_id'):
            del request.session['acting_as_agent_id']
        return request.redirect('/van/mobile-pos')

    @http.route('/van/pos/get_agents', type='jsonrpc', auth='user')
    def get_agents(self):
        """Returns list of all agent users. Admin only."""
        user = request.env.user
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        if not is_admin:
            return []
        agent_group = request.env.ref('van_sales_pharma.group_van_agent')
        request.env.cr.execute("SELECT uid FROM res_groups_users_rel WHERE gid = %s", (agent_group.id,))
        user_ids = [row[0] for row in request.env.cr.fetchall()]
        agents = request.env['res.users'].sudo().browse(user_ids)
        return [{
            'id': a.id,
            'name': a.name,
            'image_url': f'/web/image?model=res.users&id={a.id}&field=avatar_128',
        } for a in agents]

    @http.route('/van/pos/set_agent_session', type='jsonrpc', auth='user')
    def set_agent_session(self, agent_id):
        """Sets acting_as_agent_id in session for admin users."""
        user = request.env.user
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        if not is_admin:
            return {'success': False}
        if agent_id:
            request.session['acting_as_agent_id'] = int(agent_id)
        return {'success': True}

    @http.route('/van/pos/get_client_report', type='jsonrpc', auth='user')
    def get_client_report(self, client_id, date_from=None, date_to=None):
        """Returns client transaction history with running balance for Mobile POS Hisob-kitob."""
        try:
            import pytz
            user_tz = pytz.timezone(request.env.user.tz or 'Asia/Tashkent')

            if int(client_id) == 0:
                # Support "Naqt Savdo" (virtual client)
                partner = None
                client_name = "Naqt savdo (Mijozisiz)"
                total_due = 0.0
            else:
                partner = request.env['res.partner'].sudo().browse(int(client_id))
                if not partner.exists():
                    return {'success': False, 'error': 'Mijoz topilmadi'}
                client_name = partner.name
                total_due = partner.x_van_total_due or 0.0

            transactions = []

            # 1. Boshlang'ich qarz (Ostatka Qarzi) - only for real partners
            if partner:
                for ostatka in partner.x_van_ostatka_ids:
                    if ostatka.amount > 0:
                        transactions.append({
                            'date_obj': user_tz.localize(datetime.datetime.combine(ostatka.date or datetime.date.today(), datetime.time.min)),
                            'date_label': (ostatka.date or datetime.date.today()).strftime('%d.%m.%Y'),
                            'turi': "boshlangich_qarz",
                            'turi_label': "Boshlang'ich qarz",
                            'summa': ostatka.amount,
                            'is_debt': True,
                            'lines': [],
                        })

            # 2. Sotuvlar (POS Orders)
            order_domain = [('partner_id', '=', partner.id if partner else False), ('state', '=', 'done')]
            if date_from:
                order_domain.append(('date', '>=', date_from + ' 00:00:00'))
            if date_to:
                order_domain.append(('date', '<=', date_to + ' 23:59:59'))
            orders = request.env['van.pos.order'].sudo().search(order_domain, order='date asc')
            for order in orders:
                if order.amount_total > 0:
                    local_dt = pytz.utc.localize(order.date).astimezone(user_tz)
                    lines = []
                    for l in order.line_ids:
                        lines.append({
                            'name': l.product_id.name or '',
                            'qty': l.qty,
                            'price': l.price_unit,
                            'subtotal': l.qty * l.price_unit,
                        })
                    transactions.append({
                        'date_obj': local_dt,
                        'date_label': local_dt.strftime('%d.%m.%Y %H:%M:%S'),
                        'turi': 'sotuv',
                        'turi_label': '🛒 Sotuv',
                        'summa': order.amount_total,
                        'is_debt': True,
                        'lines': lines,
                    })

            # 3. Kirimlar (Payments)
            pay_domain = [('partner_id', '=', partner.id if partner else False), ('payment_type', '=', 'in')]
            if date_from:
                pay_domain.append(('date', '>=', date_from + ' 00:00:00'))
            if date_to:
                pay_domain.append(('date', '<=', date_to + ' 23:59:59'))
            payments = request.env['van.payment'].sudo().search(pay_domain, order='date asc')
            for payment in payments:
                if payment.amount > 0:
                    local_dt = pytz.utc.localize(payment.date).astimezone(user_tz)
                    transactions.append({
                        'date_obj': local_dt,
                        'date_label': local_dt.strftime('%d.%m.%Y %H:%M:%S'),
                        'turi': 'kirim',
                        'turi_label': '💵 Kirim',
                        'summa': payment.amount,
                        'is_debt': False,
                        'lines': [],
                    })

            # Sort chronologically by date_obj to compute running balance
            transactions.sort(key=lambda x: x['date_obj'] if isinstance(x['date_obj'], (datetime.datetime, datetime.date)) else datetime.datetime.min)
            running_balance = 0.0
            for tx in transactions:
                if tx['is_debt']:
                    running_balance += tx['summa']
                else:
                    running_balance -= tx['summa']
                tx['balance'] = running_balance
                # clean up date_obj for JSON serialization
                if 'date_obj' in tx: del tx['date_obj']

            # Reverse for display (newest first)
            transactions.reverse()

            return {
                'success': True,
                'client_name': client_name,
                'total_due': total_due,
                'transactions': transactions,
            }
        except Exception as e:
            _logger.error(f"get_client_report error: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/create_client', type='jsonrpc', auth='user')
    def create_client(self, name, phone, telegram_chat_id=''):
        """Creates a new client directly from Mobile POS and assigns it to current agent."""
        try:
            name = (name or '').strip()
            phone = (phone or '').strip()
            
            if not name:
                return {'success': False, 'error': 'Mijoz nomi kiritilmagan'}
            if not phone:
                return {'success': False, 'error': 'Telefon raqami kiritilmagan'}

            # Validate duplicate phone
            existing = request.env['res.partner'].sudo().search([('phone', '=', phone)], limit=1)
            if existing:
                return {'success': False, 'error': 'Bu telefon raqami bilan mijoz allaqachon mavjud'}

            agent_id = self._get_agent_id()
            
            new_client = request.env['res.partner'].sudo().create({
                'name': name,
                'phone': phone,
                'telegram_chat_id': telegram_chat_id or '',  # This is the correct field name found in res_partner.py
                'x_is_van_customer': True, # Ensure it gets picked up
                'user_id': agent_id, # Optional standard assignment
            })
            
            # Make sure it's linked in the custom logic if necessary (mijoz_ids)
            # The get_clients logic looks for x_is_van_customer=True, or agent.mijoz_ids.
            agent = request.env['res.users'].sudo().browse(agent_id)
            if hasattr(agent, 'mijoz_ids'):
                # Many2many relation
                agent.write({'mijoz_ids': [(4, new_client.id)]})

            return {
                'success': True,
                'client_id': new_client.id,
                'client_name': new_client.name,
                'message': 'Mijoz muvaffaqiyatli qo\'shildi'
            }
        except Exception as e:
            _logger.error(f"Error creating client: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/get_clients', type='jsonrpc', auth='user')
    def get_clients(self):
        agent_id = self._get_agent_id()
        agent = request.env['res.users'].sudo().browse(agent_id)
        
        if agent.mijoz_ids:
            partners = agent.mijoz_ids
        else:
            partners = request.env['res.partner'].sudo().search([('x_is_van_customer', '=', True)])
            
        # recompute balances based on new nasiya
        partners.sudo()._compute_van_nasiya_stats()
        
        # Get partner IDs for SQL query
        partner_ids = partners.ids
        if partner_ids:
            # Use SQL for efficient sorting by last transaction date (Sale OR Kirim)
            query = """
                SELECT p.id, GREATEST(MAX(o.date), MAX(pay.date)) as last_transaction_date
                FROM res_partner p
                LEFT JOIN van_pos_order o ON o.partner_id = p.id AND o.agent_id = %s AND o.state = 'done'
                LEFT JOIN van_payment pay ON pay.partner_id = p.id AND pay.agent_id = %s AND pay.payment_type = 'in'
                WHERE p.id IN %s
                GROUP BY p.id
                ORDER BY last_transaction_date DESC NULLS LAST, p.name ASC
            """
            request.env.cr.execute(query, (agent_id, agent_id, tuple(partner_ids)))
            sorted_partner_ids = [row[0] for row in request.env.cr.fetchall()]
            
            # Map partners to ensure we keep the ones we found
            partner_map = {p.id: p for p in partners}
            client_list = []
            for pid in sorted_partner_ids:
                p = partner_map.get(pid)
                if p:
                    client_list.append({
                        'id': p.id,
                        'name': p.name,
                        'balance': p.x_van_balance,
                        'total_due': p.x_van_total_due
                    })
        else:
            client_list = []
        
        # Always Prepend "Naqt savdo (Mijozisiz)"
        client_list.insert(0, {
            'id': 0,
            'name': "Naqt savdo (Mijozisiz)",
            'balance': 0.0,
            'total_due': 0.0,
            'is_cash_sale': True
        })
        
        # Add explicit sort_order for frontend persistence
        for idx, client in enumerate(client_list):
            client['sort_order'] = idx
            
        return client_list

    @http.route('/van/pos/get_inventory', type='jsonrpc', auth='user')
    def get_inventory(self):
        agent_id = self._get_agent_id()
        summary = request.env['van.agent.summary'].with_context(lang='uz_UZ').search([('agent_id', '=', agent_id)], limit=1)
        if not summary:
            return []
            
        items = []
        for line in summary.active_inventory_line_ids:
            items.append({
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'price': line.price_unit,
                'remaining': line.remaining_qty,
                'image_url': f'/web/image?model=van.product&id={line.product_id.id}&field=image_1920',
            })
        return items

    @http.route('/van/pos/get_all_products', type='jsonrpc', auth='user')
    def get_all_products(self):
        products = request.env['van.product'].with_context(lang='uz_UZ').sudo().search([('active', '=', True)])
        return [{
            'product_id': p.id,
            'name': p.display_name,
            'price': p.cost_price,
            'image_url': f'/web/image?model=van.product&id={p.id}&field=image_1920',
        } for p in products]

    @http.route('/van/pos/sync_offline', type='json', auth='user')
    def sync_offline(self, transactions=None):
        """
        Batches offline transactions (sales, kirim, chiqim).
        Ensures idempotency using 'offline_id'.
        Input format: [{'type': 'sale', 'offline_id': 'abc...', 'data': {...}}, ...]
        """
        if not transactions:
            return {'status': 'success', 'synced': [], 'errors': []}
            
        synced_ids = []
        errors = []
        
        env = request.env
        
        for idx, tx in enumerate(transactions):
            tx_type = tx.get('type')
            offline_id = tx.get('offline_id')
            data = tx.get('data', {})
            
            if not offline_id:
                errors.append({'index': idx, 'error': 'Missing offline_id'})
                continue
                
            try:
                if tx_type == 'sale':
                    # Check Idempotency
                    existing = env['van.pos.order'].sudo().search([('offline_id', '=', offline_id)], limit=1)
                    if existing:
                        synced_ids.append(offline_id)
                        continue
                        
                    partner_id = data.get('partner_id')
                    part_agent_id = self._get_agent_id()
                    agent_id = part_agent_id
                    lines = data.get('lines', [])
                    
                    if not lines:
                        raise ValueError("No products in sale")
                        
                    # Create Order
                    order_vals = {
                        'partner_id': partner_id,
                        'agent_id': agent_id,
                        'offline_id': offline_id,
                        'line_ids': [(0, 0, {
                            'product_id': l['product_id'],
                            'qty': l['qty'],
                            'price_unit': l['price'],
                        }) for l in lines]
                    }
                    
                    # Apply historical date if provided
                    tx_date = tx.get('timestamp')
                    if tx_date:
                        # Convert ISO String '2026-03-07T12:51:35.386Z' to '%Y-%m-%d %H:%M:%S'
                        if 'T' in tx_date:
                            tx_date = tx_date.split('.')[0].replace('T', ' ')
                        order_vals['date'] = tx_date
                        
                    order = env['van.pos.order'].sudo().create(order_vals)
                    order.action_confirm_order()
                    synced_ids.append(offline_id)
                    
                elif tx_type in ['kirim', 'chiqim']:
                    # Check Idempotency
                    existing = env['van.payment'].sudo().search([('offline_id', '=', offline_id)], limit=1)
                    if existing:
                        synced_ids.append(offline_id)
                        continue
                        
                    payment_type = 'in' if tx_type == 'kirim' else 'out'
                    vals = {
                        'payment_type': payment_type,
                        'agent_id': self._get_agent_id(),
                        'offline_id': offline_id,
                        'amount': float(data.get('amount', 0)),
                        'note': data.get('note', ''),
                        'payment_method': data.get('payment_method', 'cash')
                    }
                    
                    if payment_type == 'in':
                        vals['partner_id'] = data.get('partner_id')
                    else:
                        vals['expense_type'] = data.get('expense_type', 'daily')
                        
                    if tx.get('timestamp'):
                        tx_date = tx.get('timestamp')
                        if 'T' in tx_date:
                            tx_date = tx_date.split('.')[0].replace('T', ' ')
                        vals['date'] = tx_date
                        
                    env['van.payment'].sudo().create(vals)
                    synced_ids.append(offline_id)
                    
                else:
                    errors.append({'offline_id': offline_id, 'error': f"Unknown type {tx_type}"})
                    
            except Exception as e:
                _logger.error(f"Error syncing offline transaction {offline_id}: {str(e)}")
                errors.append({'offline_id': offline_id, 'error': str(e)})
                
        return {
            'status': 'success' if len(errors) == 0 else 'partial_success',
            'synced': synced_ids,
            'errors': errors
        }

    @http.route('/van/pos/submit_order', type='jsonrpc', auth='user')
    def submit_order(self, partner_id, lines):
        """
        lines = [{'product_id': ID, 'qty': QTY, 'price': PRICE}]
        """
        try:
            order_vals = {
                'agent_id': self._get_agent_id(),
                'partner_id': partner_id if partner_id else False,
                'line_ids': [(0, 0, {
                    'product_id': l['product_id'],
                    'qty': l['qty'],
                    'price_unit': l['price']
                }) for l in lines]
            }
            order = request.env['van.pos.order'].create(order_vals)
            order.action_confirm_order()
            
            return {
                'success': True,
                'order_id': order.id,
                'nasiya_id': order.nasiya_id.id,
                'nasiya_amount': order.nasiya_id.amount_total
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/submit_kirim', type='jsonrpc', auth='user')
    def submit_kirim(self, nasiya_id, amount, payment_method='cash'):
        nasiya = request.env['van.nasiya'].browse(nasiya_id)
        if not nasiya.exists():
            return {'success': False, 'error': 'Nasiya not found'}
            
        payment = request.env['van.payment'].create({
            'partner_id': nasiya.partner_id.id,
            'agent_id': self._get_agent_id(),
            'nasiya_id': nasiya.id,
            'payment_type': 'in',
            'payment_method': payment_method,
            'amount': amount,
        })
        
        return {'success': True, 'payment_id': payment.id}

    @http.route('/van/pos/submit_quick_action', type='jsonrpc', auth='user')
    def submit_quick_action(self, type, amount, note='', partner_id=None, expense_type='daily'):
        try:
            payment_vals = {
                'agent_id': self._get_agent_id(),
                'payment_type': 'in' if type == 'kirim' else 'out',
                'expense_type': expense_type if type == 'chiqim' else False,
                'amount': float(amount),
                'payment_method': 'cash',
                'note': note,
            }
            if partner_id and type == 'kirim':
                payment_vals['partner_id'] = partner_id
                
            payment = request.env['van.payment'].create(payment_vals)
            return {'success': True, 'payment_id': payment.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/get_requests', type='jsonrpc', auth='user')
    def get_requests(self):
        try:
            import pytz
            user_tz = pytz.timezone(request.env.user.tz or 'Asia/Tashkent')
            # Show all requests to all agents as requested by the user
            requests = request.env['van.request'].sudo().search([], order='date desc', limit=200)
            res = []
            for req in requests:
                lines = []
                total_amount = 0.0
                for l in req.line_ids:
                    price = l.product_id.list_price or 0.0
                    subtotal = price * l.qty
                    total_amount += subtotal
                    lines.append({
                        'product_name': l.product_id.name,
                        'qty': l.qty,
                        'price': price,
                        'subtotal': subtotal,
                        'image_url': f'/web/image?model=van.product&id={l.product_id.id}&field=image_1920'
                    })
                
                local_date_str = ''
                if req.date:
                    local_dt = pytz.utc.localize(req.date).astimezone(user_tz)
                    local_date_str = local_dt.strftime('%Y-%m-%d %H:%M:%S')

                res.append({
                    'id': req.id,
                    'name': req.name,
                    'date': local_date_str,
                    'partner_name': req.partner_id.name if req.partner_id else '',
                    'state': req.state,
                    'total_amount': total_amount,
                    'lines': lines,
                    'notes': req.notes or ''
                })
            return {'success': True, 'requests': res}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/update_request_state', type='jsonrpc', auth='user')
    def update_request_state(self, request_id, state):
        try:
            # Sudo allows agents to update any request state, even if they didn't create it
            req = request.env['van.request'].sudo().search([('id', '=', int(request_id))])
            if req:
                req.sudo().write({'state': state})
                return {'success': True}
            return {'success': False, 'error': "So'rov topilmadi yoki ruxsat yo'q"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/submit_request', type='jsonrpc', auth='user')
    def submit_request(self, partner_id, lines, notes=''):
        try:
            if not partner_id:
                return {'success': False, 'error': "Mijozni tanlash so'rov qoldirish uchun majburiy!"}

            request_vals = {
                'agent_id': self._get_agent_id(),
                'partner_id': partner_id,
                'notes': notes,
                'line_ids': [(0, 0, {
                    'product_id': l['product_id'],
                    'qty': float(l['qty'])
                }) for l in lines]
            }
            # Use sudo() to bypass strict creation rules for POS users
            new_request = request.env['van.request'].sudo().create(request_vals)
            return {'success': True, 'request_id': new_request.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/get_current_agent', type='jsonrpc', auth='user')
    def get_current_agent(self):
        try:
            agent_id = self._get_agent_id()
            user = request.env['res.users'].sudo().browse(agent_id)
            if user.has_group('van_sales_pharma.group_van_agent') or user.has_group('base.group_system'):
                # Get the summary ID for this agent
                summary = request.env['van.agent.summary'].sudo().search([('agent_id', '=', user.id)], limit=1)
                if not summary:
                    summary = request.env['van.agent.summary'].sudo().create({'agent_id': user.id})
                summary_id = summary.id
                
                # Check if currently acting as an admin
                is_admin_mode = bool(request.env.user.has_group('van_sales_pharma.group_van_admin') and request.session.get('acting_as_agent_id'))
                is_admin = request.env.user.has_group('van_sales_pharma.group_van_admin')

                return {
                    'id': user.id,
                    'summary_id': summary_id,
                    'name': user.name,
                    'phone': user.phone or '',
                    'oylik_balansi': user.oylik_balansi,
                    'default_taminotchi_id': user.default_taminotchi_id.id,
                    'default_taminotchi_name': user.default_taminotchi_id.name or '',
                    'image_url': f'/web/image?model=res.users&id={user.id}&field=avatar_128',
                    'is_admin_mode': is_admin_mode,
                    'is_admin': is_admin
                }
            return None
        except Exception as e:
            return None

    @http.route('/van/pos/get_taminotchis', type='jsonrpc', auth='user')
    def get_taminotchis(self):
        taminotchis = request.env['van.taminotchi'].sudo().search([])
        return [{
            'id': t.id,
            'name': t.name,
        } for t in taminotchis]

    @http.route('/van/pos/submit_trip', type='jsonrpc', auth='user')
    def submit_trip(self, agent_id, date, note, lines, taminotchi_id=None):
        try:
            if not agent_id:
                return {'success': False, 'error': "Agentni tanlash majburiy!"}
            if not lines:
                return {'success': False, 'error': "Hech qanday mahsulot tanlanmadi!"}

            # Get internal location for the trip
            location = request.env['stock.location'].sudo().search([
                ('usage', '=', 'internal'), 
                ('company_id', 'in', [request.env.company.id, False])
            ], limit=1)

            if not location:
                return {'success': False, 'error': "Ombor topilmadi!"}

            # Fetch Taminotchi
            if taminotchi_id:
                taminotchi = request.env['van.taminotchi'].sudo().browse(int(taminotchi_id))
            else:
                agent = request.env['res.users'].sudo().browse(int(agent_id))
                taminotchi = agent.default_taminotchi_id
            
            if not taminotchi or not taminotchi.exists():
                return {'success': False, 'error': "Sizga taminotchi biriktirilmagan. Iltimos, taminotchini tanlang yoki administratorga murojaat qiling."}

            trip_vals = {
                'taminotchi_id': taminotchi.id,
                'agent_id': int(agent_id),
                'location_id': location.id,
                'date': date,
                'note': note or '',
                'state': 'draft',
                'trip_line_ids': [(0, 0, {
                    'product_id': l['product_id'],
                    'loaded_qty': float(l['qty']),
                    'price_unit': request.env['van.product'].sudo().browse(l['product_id']).cost_price,
                }) for l in lines]
            }
            
            # Sudo is needed because agents may not natively have creation rights on other agents
            new_trip = request.env['van.trip'].sudo().create(trip_vals)
            
            # Auto validate the trip to push quantities into van.agent.inventory
            new_trip.sudo().action_validate()
            
            return {'success': True, 'trip_id': new_trip.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/get_trips', type='jsonrpc', auth='user')
    def get_trips(self):
        try:
            import pytz
            user_tz = pytz.timezone(request.env.user.tz or 'Asia/Tashkent')
            
            # Fetch trips associated with the current agent
            agent_id = self._get_agent_id()
            trips = request.env['van.trip'].sudo().search([('agent_id', '=', agent_id)], order='date desc, id desc', limit=100)
            res = []
            
            for trip in trips:
                res.append({
                    'id': trip.id,
                    'name': trip.name,
                    'date': str(trip.date) if trip.date else '',
                    'agent_name': trip.agent_id.name if trip.agent_id else '',
                    'state': trip.state,
                    'total_cost': trip.amount_cost_total,
                    'total_qty': trip.x_loaded_qty,
                    'lines': [{
                        'product_name': l.product_id.name,
                        'qty': l.loaded_qty,
                        'price': l.price_unit,
                        'subtotal': l.loaded_qty * l.product_id.cost_price, # Cost subtotal
                        'image_url': f'/web/image?model=van.product&id={l.product_id.id}&field=image_1920'
                    } for l in trip.trip_line_ids],
                    'note': trip.note or ''
                })
            return {'success': True, 'trips': res}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==========================================
    # CLIENT TELEGRAM WEB APP ROUTES (PUBLIC)
    # ==========================================

    @http.route('/van/public/image/<int:product_id>', type='http', auth='public', cors='*')
    def public_product_image(self, product_id, **kwargs):
        """Serve product images to public WebApp without session auth restrictions"""
        product = request.env['van.product'].sudo().browse(product_id)
        if not product.exists() or not product.image_1920:
            return request.not_found()
            
        import base64
        try:
            image_base64 = base64.b64decode(product.image_1920)
            headers = [
                ('Content-Type', 'image/jpeg'),
                ('Content-Length', str(len(image_base64)))
            ]
            return request.make_response(image_base64, headers)
        except Exception:
            return request.not_found()

    @http.route('/van/client/request', type='http', auth='public', website=True, cors='*')
    def client_request_page(self, chat_id=None, **kwargs):
        if not chat_id:
            return "Telegram Chat ID is missing. Iltimos bot orqali kiring."
            
        # Validate partner
        partner = request.env['res.partner'].sudo().search([('telegram_chat_id', '=', str(chat_id))], limit=1)
        if not partner:
            return "Kechirasiz, sizning hisobingiz topilmadi. Iltimos botdan qayta ro'yxatdan o'ting."
            
        base_url = request.env['ir.config_parameter'].sudo().get_param('van_telegram_odoo_url', request.env['ir.config_parameter'].sudo().get_param('web.base.url', ''))
        if not base_url.startswith('http'):
            base_url = "https://" + base_url.lstrip('/')
        elif base_url.startswith('http://') and not ('localhost' in base_url or '127.0.0.1' in base_url):
            base_url = base_url.replace('http://', 'https://')
        base_url = base_url.rstrip('/')
        
        # Get active products in the client's language to prevent translation mismatches
        products = request.env['van.product'].sudo().with_context(lang='uz_UZ').search([])
        product_data = []
        for p in products:
            product_data.append({
                'id': p.id,
                'name': p.name,
                'price': p.list_price,
                'price_str': f"{p.list_price:,.0f}",
                'image_url': f"{base_url}/van/public/image/{p.id}" if p.image_1920 else ""
            })
            
        import json
        products_dict = {p['id']: p for p in product_data}
        values = {
            'partner_id': partner.id,
            'partner_name': partner.name,
            'products': product_data,
            'products_json': json.dumps(products_dict),
            'odoo_url': base_url
        }
        
        headers = [
            ('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0'),
            ('Pragma', 'no-cache'),
            ('Expires', '0')
        ]
        return request.render('van_sales_pharma.client_request_template', values, headers=headers)

    @http.route('/van/client/submit_request', type='jsonrpc', auth='public', csrf=False, cors='*')
    def client_submit_request(self, partner_id, lines, notes=''):
        try:
            if not partner_id:
                return {'success': False, 'error': 'Missing partner ID'}
            
            partner = request.env['res.partner'].sudo().browse(int(partner_id))
            if not partner.exists():
                return {'success': False, 'error': 'Partner not found'}
                
            # Create request without an agent originally. 
            # Later we can assign to an active agent in that region or leave it generic for office.
            # We'll assign it to the admin User for now, or just leave agent_id empty if schema permits.
            # Usually we need an agent_id. Let's find the first valid agent.
            admin = request.env.ref('base.user_admin')
            
            request_vals = {
                'agent_id': admin.id, 
                'partner_id': partner.id,
                'notes': f"TELEGRAM WEB APP ORQALI:\n{notes}",
                'line_ids': [(0, 0, {
                    'product_id': l['product_id'],
                    'qty': float(l['qty'])
                }) for l in lines]
            }
            
            new_request = request.env['van.request'].sudo().create(request_vals)
            
            # Attach Web App Button for Zakaz Berish
            base_url = request.env['ir.config_parameter'].sudo().get_param('van_telegram_odoo_url', request.env['ir.config_parameter'].sudo().get_param('web.base.url', ''))
            if not base_url.startswith('http'):
                base_url = "https://" + base_url.lstrip('/')
            elif base_url.startswith('http://') and not ('localhost' in base_url or '127.0.0.1' in base_url):
                base_url = base_url.replace('http://', 'https://')
            base_url = base_url.rstrip('/')
            
            import time
            web_app_url = f"{base_url}/van/client/request?chat_id={partner.telegram_chat_id}&v={int(time.time())}"
            button = {"text": "🛒 Zakaz berish", "web_app": {"url": web_app_url}}
            reply_markup = {"inline_keyboard": [[button]]}

            # Send confirmation message to client
            msg = f"✅ <b>Sizning so'rovingiz qabul qilindi!</b>\n\n🔖 Raqam: #{new_request.id}\nBiz tez orada siz bilan bog'lanamiz."
            request.env['van.telegram.utils'].sudo().send_message(partner.telegram_chat_id, msg, reply_markup=reply_markup)
            
            return {'success': True, 'request_id': new_request.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}
