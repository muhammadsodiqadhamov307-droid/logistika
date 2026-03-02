from odoo import http
from odoo.http import request

class VanPosController(http.Controller):

    @http.route('/van/pos/get_clients', type='jsonrpc', auth='user')
    def get_clients(self):
        partners = request.env['res.partner'].search([('x_is_van_customer', '=', True)])
        # recompute balances based on new nasiya
        partners._compute_van_nasiya_stats()
        
        return [{
            'id': p.id,
            'name': p.name,
            'balance': p.x_van_balance,
            'total_due': p.x_van_total_due
        } for p in partners]

    @http.route('/van/pos/get_inventory', type='jsonrpc', auth='user')
    def get_inventory(self):
        summary = request.env['van.agent.summary'].search([('agent_id', '=', request.env.uid)], limit=1)
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

    @http.route('/van/pos/submit_order', type='jsonrpc', auth='user')
    def submit_order(self, partner_id, lines):
        """
        lines = [{'product_id': ID, 'qty': QTY, 'price': PRICE}]
        """
        try:
            order_vals = {
                'agent_id': request.env.uid,
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
            'agent_id': request.env.uid,
            'nasiya_id': nasiya.id,
            'payment_type': 'in',
            'payment_method': payment_method,
            'amount': amount,
        })
        
        return {'success': True, 'payment_id': payment.id}

    @http.route('/van/pos/submit_quick_action', type='jsonrpc', auth='user')
    def submit_quick_action(self, type, amount, note='', partner_id=None):
        try:
            payment_vals = {
                'agent_id': request.env.uid,
                'payment_type': 'in' if type == 'kirim' else 'out',
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
                'agent_id': request.env.uid,
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
            user = request.env.user
            if user.has_group('van_sales_pharma.group_van_agent') or user.has_group('base.group_system'):
                return {
                    'id': user.id,
                    'name': user.name,
                    'phone': user.phone or '',
                    'image_url': f'/web/image?model=res.users&id={user.id}&field=avatar_128'
                }
            return None
        except Exception as e:
            return None

    @http.route('/van/pos/submit_trip', type='jsonrpc', auth='user')
    def submit_trip(self, agent_id, date, note, lines):
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

            trip_vals = {
                'agent_id': int(agent_id),
                'location_id': location.id,
                'date': date,
                'note': note or '',
                'state': 'draft',
                'trip_line_ids': [(0, 0, {
                    'product_id': l['product_id'],
                    'loaded_qty': float(l['qty']),
                    'price_unit': request.env['van.product'].sudo().browse(l['product_id']).list_price,
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
            trips = request.env['van.trip'].sudo().search([('agent_id', '=', request.env.uid)], order='date desc, id desc', limit=100)
            res = []
            
            for trip in trips:
                lines = []
                total_amount = 0.0
                total_qty = 0.0
                
                for l in trip.trip_line_ids:
                    price = l.price_unit or 0.0
                    subtotal = price * l.loaded_qty
                    total_amount += subtotal
                    total_qty += l.loaded_qty
                    
                    lines.append({
                        'product_name': l.product_id.name,
                        'qty': l.loaded_qty,
                        'price': price,
                        'subtotal': subtotal,
                        'image_url': f'/web/image?model=van.product&id={l.product_id.id}&field=image_1920'
                    })
                
                res.append({
                    'id': trip.id,
                    'name': trip.name,
                    'date': str(trip.date) if trip.date else '',
                    'agent_name': trip.agent_id.name if trip.agent_id else '',
                    'state': trip.state,
                    'total_amount': total_amount,
                    'total_qty': total_qty,
                    'lines': lines,
                    'note': trip.note or ''
                })
            return {'success': True, 'trips': res}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==========================================
    # CLIENT TELEGRAM WEB APP ROUTES (PUBLIC)
    # ==========================================

    @http.route('/van/client/request', type='http', auth='public', website=True)
    def client_request_page(self, chat_id=None, **kwargs):
        if not chat_id:
            return "Telegram Chat ID is missing. Iltimos bot orqali kiring."
            
        # Validate partner
        partner = request.env['res.partner'].sudo().search([('telegram_chat_id', '=', str(chat_id))], limit=1)
        if not partner:
            return "Kechirasiz, sizning hisobingiz topilmadi. Iltimos botdan qayta ro'yxatdan o'ting."
            
        # Get active products
        products = request.env['van.product'].sudo().search([])
        product_data = []
        for p in products:
            product_data.append({
                'id': p.id,
                'name': p.name,
                'price': p.list_price,
                'price_str': f"{p.list_price:,.0f}",
                'image_url': f"/web/image?model=van.product&id={p.id}&field=image_1920" if p.image_1920 else ""
            })
            
        base_url = request.env['ir.config_parameter'].sudo().get_param('van_telegram_odoo_url', request.env['ir.config_parameter'].sudo().get_param('web.base.url', ''))

        values = {
            'partner_id': partner.id,
            'partner_name': partner.name,
            'products': product_data,
            'odoo_url': base_url
        }
        
        return request.render('van_sales_pharma.client_request_template', values)

    @http.route('/van/client/submit_request', type='jsonrpc', auth='public', csrf=False)
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
            
            # Send confirmation message to client
            msg = f"✅ <b>Sizning so'rovingiz qabul qilindi!</b>\n\n🔖 Raqam: #{new_request.id}\nBiz tez orada siz bilan bog'lanamiz."
            request.env['van.telegram.utils'].sudo().send_message(partner.telegram_chat_id, msg)
            
            return {'success': True, 'request_id': new_request.id}
        except Exception as e:
            return {'success': False, 'error': str(e)}
