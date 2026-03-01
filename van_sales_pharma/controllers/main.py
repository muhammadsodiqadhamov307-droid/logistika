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
            requests = request.env['van.request'].search([('agent_id', '=', request.env.uid)], order='date desc', limit=100)
            res = []
            for req in requests:
                lines = [{'product_name': l.product_id.name, 'qty': l.qty} for l in req.line_ids]
                
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
                    'lines': lines,
                    'notes': req.notes or ''
                })
            return {'success': True, 'requests': res}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/van/pos/update_request_state', type='jsonrpc', auth='user')
    def update_request_state(self, request_id, state):
        try:
            req = request.env['van.request'].sudo().search([('id', '=', int(request_id)), ('agent_id', '=', request.env.uid)])
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
