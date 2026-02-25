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

    def unlink(self):
        for trip in self:
            # Instead of preventing deletion, forcefully cascade delete associated records
            if trip.pos_order_ids:
                trip.pos_order_ids.sudo().unlink()
            if trip.payment_ids:
                trip.payment_ids.sudo().unlink()
            
            # If trip has already affected agent summary inventory
            if trip.state in ['loaded', 'in_progress', 'closed']:
                summary = self.env['van.agent.summary'].search([
                    ('agent_id', '=', trip.agent_id.id),
                ], limit=1)
                
                if summary:
                    for line in trip.trip_line_ids:
                        inv_line = self.env['van.agent.inventory.line'].search([
                            ('summary_id', '=', summary.id),
                            ('product_id', '=', line.product_id.id)
                        ], limit=1)
                        
                        if inv_line:
                            # Reverse the 'action_start' addition
                            inv_line.loaded_qty -= line.loaded_qty
                            
                            # Reverse the 'action_close' subtraction (if it was closed)
                            if trip.state == 'closed':
                                inv_line.loaded_qty += line.returned_qty

        return super().unlink()

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
    def get_van_dashboard_data(self, date_from=False, date_to=False):
        """ Dashboard uchun moliya paneli ma'lumotlarini hisoblash RPC metodi. Date filtrlarni qo'llab quvvatlaydi. """
        import pytz
        from datetime import datetime, time
        
        # User timezone or UTC
        tz = pytz.timezone(self._context.get('tz') or 'UTC')
        today_local = datetime.now(tz).date()
        today_start = tz.localize(datetime.combine(today_local, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        
        # Date Logic
        domain_pos = []
        domain_vp = []
        
        if date_from:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            s_date = tz.localize(datetime.combine(dt_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            domain_pos.append(('date_order', '>=', s_date))
            domain_vp.append(('date', '>=', s_date))
            
        if date_to:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d")
            e_date = tz.localize(datetime.combine(dt_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
            domain_pos.append(('date_order', '<=', e_date))
            domain_vp.append(('date', '<=', e_date))
        
        # 1. Total Global Nasiya
        # We find all partners and sum up x_van_total_due (which represents their actual debt)
        partners = self.env['res.partner'].search([('x_is_van_customer', '=', True)])
        total_global_nasiya = sum(p.x_van_total_due for p in partners)

        # 2. POS Cash & Card (Filtered by Date or All-Time)
        pos_orders = self.env['pos.order'].search(domain_pos)
        t_cash = 0.0
        t_card = 0.0
        t_chiqim = 0.0
        
        for order in pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced']):
            for payment in order.payment_ids:
                if payment.payment_method_id.is_cash_count:
                    t_cash += payment.amount
                elif not payment.payment_method_id.split_transactions:
                    t_card += payment.amount

        # 3. Add Kirim / Track Chiqim (Filtered by Date or All-Time)
        van_payments = self.env['van.payment'].search(domain_vp)
        
        for vp in van_payments:
            if vp.payment_type == 'in':
                if vp.payment_method == 'cash': t_cash += vp.amount
                elif vp.payment_method == 'card': t_card += vp.amount
            elif vp.payment_type == 'out':
                t_chiqim += vp.amount
                # Chiqim decreases the agent's cash balance
                t_cash -= vp.amount


        # 4. Calculate Margin (Foyda) for Filtered sales
        # Margin = Total Price - Standard Price * quantity
        margin_today = 0.0
        for order in pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced']):
            for line in order.lines:
                # Odoo's default margin calculation (if pos_margin is installed) or fallback
                if hasattr(line, 'margin'):
                    margin_today += line.margin
                else:
                    # Fallback to standard_price or 0 if missing
                    # Some versions use `cost_price` or `standard_price`
                    cost_unit = getattr(line.product_id, 'standard_price', 0.0) or 0.0
                    cost = cost_unit * line.qty
                    margin_today += (line.price_subtotal_incl - cost)

        # 5. Top Mijozlar va Agentlar (Filtered by Date, or All-Time if no date)
        # Using the same pos_orders variable as it's already filtered properly based on date_from/date_to
        monthly_orders = pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])

        customer_totals = {}
        agent_totals = {}
        product_totals = {}
        
        for mo in monthly_orders:
            # Products
            for line in mo.lines:
                if line.product_id:
                    p_id = line.product_id.id
                    p_name = line.product_id.name
                    if p_id not in product_totals:
                        product_totals[p_id] = {'name': p_name, 'total': 0.0}
                    product_totals[p_id]['total'] += line.price_subtotal_incl
            # Customers (Aggregate by Name to merge duplicate partner records like "Yangi apteka")
            if mo.partner_id:
                c_name = mo.partner_id.name or "Noma'lum"
                c_key = c_name.strip().upper()
                if c_key not in customer_totals:
                    customer_totals[c_key] = {'name': c_name.strip(), 'total': 0.0}
                customer_totals[c_key]['total'] += mo.amount_total
                
            # Agents
            a_id = mo.user_id.id
            a_name = mo.user_id.name
            if a_id not in agent_totals:
                agent_totals[a_id] = {'name': a_name, 'total': 0.0}
            agent_totals[a_id]['total'] += mo.amount_total

        # Sort and take top 5
        top_customers = sorted(customer_totals.values(), key=lambda x: x['total'], reverse=True)[:5]
        top_agents = sorted(agent_totals.values(), key=lambda x: x['total'], reverse=True)[:5]
        top_products = sorted(product_totals.values(), key=lambda x: x['total'], reverse=True)[:5]

        # 6. Monthly Sales Chart Data (Last 6 Months)
        from dateutil.relativedelta import relativedelta
        import calendar
        
        chart_labels = []
        chart_data = []
        
        uzbek_months = {
            1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
            7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
        }

        # Going back 5 months + current month = 6 months total
        for i in range(5, -1, -1):
            target_date = today_local - relativedelta(months=i)
            first_day = target_date.replace(day=1)
            last_day = target_date.replace(day=calendar.monthrange(target_date.year, target_date.month)[1])
            
            s_date = tz.localize(datetime.combine(first_day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            e_date = tz.localize(datetime.combine(last_day, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
            
            # Calculate sum using standard search and mapped to avoid read_group API changes
            domain = [('date_order', '>=', s_date), ('date_order', '<=', e_date), ('state', 'in', ['paid', 'done', 'invoiced'])]
            orders = self.env['pos.order'].search(domain)
            month_total = sum(orders.mapped('amount_total'))
            
            chart_labels.append(f"{uzbek_months[target_date.month]} {target_date.year}")
            chart_data.append(month_total)

        # Get view_ids for explicitly opening list views
        detail_view = self.env.ref('van_sales_pharma.view_van_dashboard_detail_list', raise_if_not_found=False)
        margin_view = self.env.ref('van_sales_pharma.view_van_pos_margin_list', raise_if_not_found=False)

        return {
            'today_trips_count': len(pos_orders),
            'active_trips_count': len(pos_orders.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])),
            'total_cash': t_cash,
            'total_card': t_card,
            'total_chiqim': t_chiqim,
            'total_global_nasiya': total_global_nasiya,
            'margin_today': margin_today,
            'top_customers': top_customers,
            'top_agents': top_agents,
            'top_products': top_products,
            'chart_labels': chart_labels,
            'chart_data': chart_data,
            'detail_view_id': detail_view.id if detail_view else False,
            'margin_view_id': margin_view.id if margin_view else False,
            'currency_id': self.env.company.currency_id.id,
        }
