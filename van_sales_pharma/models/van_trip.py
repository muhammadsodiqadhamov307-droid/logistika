import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class VanTrip(models.Model):
    _name = 'van.trip'
    _description = 'Kun Sayohati (Van Trip)'
    _order = 'date desc, id desc'

    name = fields.Char(string='Sayohat Raqami', required=True, copy=False, readonly=True, default=lambda self: _('Yangi'))
    company_id = fields.Many2one('res.company', string='Korxona', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    agent_id = fields.Many2one('res.users', string='Savdo Agenti', required=True, default=lambda self: self.env.user)
    location_id = fields.Many2one('stock.location', string='Mashina Ombori', required=True, domain=[('usage', '=', 'internal')])
    
    date = fields.Date(string='Sana', required=True, default=fields.Date.context_today)
    
    state = fields.Selection([
        ('draft', 'Qoralama'),
        ('loaded', 'Yuklangan'),
        ('in_progress', 'Jarayonda'),
        ('closed', 'Yopilgan')
    ], string='Holat', default='draft', required=True, copy=False, tracking=True)

    trip_line_ids = fields.One2many('van.trip.line', 'trip_id', string='Yuklangan Mahsulotlar')
    pos_order_ids = fields.One2many('pos.order', 'x_trip_id', string='POS Sotuvlar')
    payment_ids = fields.One2many('van.payment', 'trip_id', string='To\'lovlar')

    # Financials
    x_cash_expected = fields.Monetary(string='Kutilgan Naqt', compute='_compute_financials', store=True, currency_field='currency_id')
    x_card_expected = fields.Monetary(string='Kutilgan Karta', compute='_compute_financials', store=True, currency_field='currency_id')
    x_nasiya_total = fields.Monetary(string='Jami Nasiya', compute='_compute_financials', store=True, currency_field='currency_id')
    
    x_cash_received = fields.Monetary(string='Topshirilgan Naqt', copy=False, currency_field='currency_id')
    x_card_received = fields.Monetary(string='Topshirilgan Karta', copy=False, currency_field='currency_id')
    
    x_difference = fields.Monetary(string='Farq', compute='_compute_difference', store=True, currency_field='currency_id')

    # Quantities
    x_loaded_qty = fields.Float(string='Yuklangan Miqdor', compute='_compute_quantities')
    x_sold_qty = fields.Float(string='Sotilgan Miqdor', compute='_compute_quantities')
    x_returned_qty = fields.Float(string='Qaytarilgan Miqdor', compute='_compute_quantities')
    x_remaining_qty = fields.Float(string='Mashina Qoldig\'i', compute='_compute_quantities')

    note = fields.Text(string='Izoh')


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Yangi')) == _('Yangi'):
                vals['name'] = self.env['ir.sequence'].next_by_code('van.trip') or _('Yangi')
        return super().create(vals_list)

    @api.depends('pos_order_ids.state', 'pos_order_ids.payment_ids.amount', 'pos_order_ids.amount_total')
    def _compute_financials(self):
        for trip in self:
            cash_expected = 0.0
            card_expected = 0.0
            nasiya_total = 0.0

            # POS to'lov turlariga qarab ajratamiz
            for order in trip.pos_order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced']):
                for payment in order.payment_ids:
                    method = payment.payment_method_id
                    if method.is_cash_count:
                        cash_expected += payment.amount
                    elif method.split_transactions: # Nasiya (Customer Account)
                        nasiya_total += payment.amount
                    else: # Boshqa (Karta va h.k)
                        card_expected += payment.amount

            trip.x_cash_expected = cash_expected
            trip.x_card_expected = card_expected
            trip.x_nasiya_total = nasiya_total

    @api.depends('x_cash_expected', 'x_cash_received')
    def _compute_difference(self):
        for trip in self:
            trip.x_difference = trip.x_cash_received - trip.x_cash_expected

    @api.depends('trip_line_ids.loaded_qty', 'trip_line_ids.sold_qty', 'trip_line_ids.returned_qty', 'trip_line_ids.remaining_qty')
    def _compute_quantities(self):
        for trip in self:
            trip.x_loaded_qty = sum(trip.trip_line_ids.mapped('loaded_qty'))
            trip.x_sold_qty = sum(trip.trip_line_ids.mapped('sold_qty'))
            trip.x_returned_qty = sum(trip.trip_line_ids.mapped('returned_qty'))
            trip.x_remaining_qty = sum(trip.trip_line_ids.mapped('remaining_qty'))

    def action_load(self):
        """ Ochadi yuklash wizardini """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Faqat Qoralama holatdagi sayohatga yuklash mumkin!"))
        
        return {
            'name': _('Mashinaga Yuklash'),
            'type': 'ir.actions.act_window',
            'res_model': 'van.load.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_trip_id': self.id}
        }

    def action_start(self):
        for trip in self:
            if trip.state != 'loaded':
                raise UserError(_("Sayohatni boshlash uchun u avval yuklangan bo'lishi kerak!"))
            trip.state = 'in_progress'

            # Agent doimiy hisoboti profilini qidiramiz
            summary = self.env['van.agent.summary'].search([
                ('agent_id', '=', trip.agent_id.id),
            ], limit=1)

            if not summary:
                summary = self.env['van.agent.summary'].create({
                    'agent_id': trip.agent_id.id,
                })

            # Inventar satrlarini yangilash (ochirib yubormasdan)
            for line in trip.trip_line_ids:
                existing_inv_line = self.env['van.agent.inventory.line'].search([
                    ('summary_id', '=', summary.id),
                    ('product_id', '=', line.product_id.id)
                ], limit=1)

                if existing_inv_line:
                    # Doimiy profilga yangi yuklangan miqdorni qo'shamiz +=
                    existing_inv_line.loaded_qty += line.loaded_qty
                    existing_inv_line.price_unit = line.price_unit
                else:
                    self.env['van.agent.inventory.line'].create({
                        'summary_id': summary.id,
                        'product_id': line.product_id.id,
                        'price_unit': line.price_unit,
                        'loaded_qty': line.loaded_qty,
                        'sold_qty': 0.0,
                        'returned_qty': 0.0,
                    })
        return True

    def action_close(self):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("Sayohatni yopish uchun u 'Jarayonda' bo'lishi kerak!"))
            
        return {
            'name': _('Sayohatni Yopish'),
            'type': 'ir.actions.act_window',
            'res_model': 'van.trip.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_trip_id': self.id,
                'default_cash_received': self.x_cash_expected,
                'default_card_received': self.x_card_expected
            }
        }

    @api.model
    def get_van_dashboard_data(self):
        """ Dashboard uchun moliya paneli ma'lumotlarini hisoblash RPC metodi """
        import pytz
        from datetime import datetime, time
        
        # User timezone or UTC
        tz = pytz.timezone(self._context.get('tz') or 'UTC')
        today_local = datetime.now(tz).date()
        today_start = tz.localize(datetime.combine(today_local, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        
        # 1. Total Global Nasiya
        # We find all partners and sum up x_van_balance where it is > 0
        partners = self.env['res.partner'].search([('x_is_van_customer', '=', True)])
        total_global_nasiya = sum(p.x_van_balance for p in partners if p.x_van_balance > 0)

        # 2. Today's POS Cash & Card
        pos_orders = self.env['pos.order'].search([
            ('date_order', '>=', today_start)
        ])
        t_cash = 0.0
        t_card = 0.0
        t_chiqim = 0.0
        
        for order in pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced']):
            for payment in order.payment_ids:
                if payment.payment_method_id.is_cash_count:
                    t_cash += payment.amount
                elif not payment.payment_method_id.split_transactions:
                    t_card += payment.amount

        # 3. Add Today's Kirim / Track Chiqim (van.payments)
        today_van_payments = self.env['van.payment'].search([
            ('date', '>=', today_start)
        ])
        for vp in today_van_payments:
            if vp.payment_type == 'in':
                if vp.payment_method == 'cash': t_cash += vp.amount
                elif vp.payment_method == 'card': t_card += vp.amount
            elif vp.payment_type == 'out':
                t_chiqim += vp.amount
                # Note: We don't subtract chiqim from cash/card cards as user wants "money that was received"

        # 4. Recent POS Sales
        recent_sales = []
        for o in pos_orders.sorted(key=lambda x: x.date_order, reverse=True)[:10]:
            methods = []
            for p in o.payment_ids:
                if p.payment_method_id.is_cash_count: methods.append('Naqt')
                elif p.payment_method_id.split_transactions: methods.append('Nasiya')
                else: methods.append('Karta')
            
            p_type = 'nasiya' if 'Nasiya' in methods else ('card' if 'Karta' in methods else 'cash')
            recent_sales.append({
                'id': o.id,
                'name': o.name,
                'partner_id': [o.partner_id.id, o.partner_id.name] if o.partner_id else False,
                'amount_total': o.amount_total,
                'state': 'To\'langan' if o.state in ['paid', 'done', 'invoiced'] else 'Qoralama',
                'payment_method_display': ' / '.join(set(methods)) or "Noma'lum",
                'payment_type': p_type
            })

        # 5. Recent Kirim & Chiqim
        recent_kirims = []
        for vp in today_van_payments.sorted(key=lambda x: x.date, reverse=True)[:15]:
            recent_kirims.append({
                'id': vp.id,
                'name': vp.name,
                'partner_id': [vp.partner_id.id, vp.partner_id.name] if vp.partner_id else False,
                'amount': vp.amount,
                'type': vp.payment_type, # 'in' or 'out'
                'method_display': 'Naqt' if vp.payment_method == 'cash' else 'Karta',
                'note': vp.note or ''
            })

        # Get view_id for explicitly opening the list view
        detail_view = self.env.ref('van_sales_pharma.view_van_dashboard_detail_list', raise_if_not_found=False)

        return {
            'today_trips_count': len(pos_orders),
            'active_trips_count': len(pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])),
            'total_cash': t_cash,
            'total_card': t_card,
            'total_chiqim': t_chiqim,
            'total_global_nasiya': total_global_nasiya,
            'recent_sales': recent_sales,
            'recent_kirims': recent_kirims,
            'detail_view_id': detail_view.id if detail_view else False,
        }
