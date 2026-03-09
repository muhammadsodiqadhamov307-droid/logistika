from odoo import models, fields, api, _
from datetime import datetime, time, date as _date
import pytz

class VanAgentSummary(models.Model):
    """
    Har bir savdo agenti uchun umumiy hisobot modeli.
    Bu model yagona (doimiy) profil bo'lib xizmat qiladi.
    Moliya va sotuvlar date_from va date_to ga asosan hisoblanadi.
    """
    _name = 'van.agent.summary'
    _description = 'Agent Hisobot (Doimiy)'
    _order = 'agent_id'
    _rec_name = 'agent_id'

    agent_id = fields.Many2one('res.users', string='Agent', required=True, index=True)
    # Filtrlash uchun sanalar (majburiy emas)
    date_from = fields.Date(string='Dastlabki Sana', default=fields.Date.context_today, store=True)
    date_to = fields.Date(string='Oxirgi Sana', default=fields.Date.context_today, store=True)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    oylik_balansi = fields.Monetary(related='agent_id.oylik_balansi', string='Oylik Balansi', readonly=True)
    total_foyda = fields.Monetary(string='Foyda', compute='_compute_financials', currency_field='currency_id')
    qoladigan_pul = fields.Monetary(string='Agentdan Qoladigan', compute='_compute_financials', currency_field='currency_id')

    # === Moliyaviy ko'rsatkichlar ===
    total_cash = fields.Monetary(string='Naqt Pul', currency_field='currency_id',
                                 compute='_compute_financials')
    total_nasiya = fields.Monetary(string='Nasiya (Qarz)', currency_field='currency_id',
                                   compute='_compute_financials')
    total_chiqim = fields.Monetary(string='Chiqim (Xarajat)', currency_field='currency_id',
                                  compute='_compute_financials')
    total_sales = fields.Monetary(string='Jami Sotuv', currency_field='currency_id',
                                  compute='_compute_financials')
    total_balance = fields.Monetary(string='Mavjud Balans', currency_field='currency_id',
                                   compute='_compute_financials',
                                   help="Ushbu oraliqdagi Naqt - Chiqim")

    # === Mahsulot inventariyasi ===
    inventory_line_ids = fields.One2many('van.agent.inventory.line', 'summary_id', string='Inventar')
    active_inventory_line_ids = fields.Many2many(
        'van.agent.inventory.line',
        compute='_compute_active_inventory',
        string="Faol Inventar"
    )
    inventory_count = fields.Integer(string='Mahsulotlar Soni', compute='_compute_active_inventory')

    total_inventory_qty = fields.Float(string='Jami Mahsulotlar Soni', compute='_compute_inventory_dashboard')
    total_inventory_value = fields.Monetary(string='Jami Summa (Sotuv)', currency_field='currency_id', compute='_compute_inventory_dashboard')
    total_inventory_cost_value = fields.Monetary(string='Jami Summa (Olish Narxida)', currency_field='currency_id', compute='_compute_inventory_dashboard')
    expected_net_profit = fields.Monetary(string='Kutilayotgan Foyda', currency_field='currency_id', compute='_compute_inventory_dashboard')

    @api.depends('inventory_line_ids.remaining_qty', 'inventory_line_ids.price_unit', 'inventory_line_ids.cost_price')
    def _compute_inventory_dashboard(self):
        for rec in self:
            qty = val = cost_val = profit = 0.0
            for line in rec.active_inventory_line_ids:
                qty += line.remaining_qty
                val += line.remaining_qty * line.price_unit
                cost = line.cost_price
                cost_val += line.remaining_qty * cost
                profit += (line.price_unit - cost) * line.remaining_qty
            rec.total_inventory_qty = qty
            rec.total_inventory_value = val
            rec.total_inventory_cost_value = cost_val
            rec.expected_net_profit = profit

    @api.depends('inventory_line_ids.remaining_qty')
    def _compute_active_inventory(self):
        for rec in self:
            active_lines = rec.inventory_line_ids.filtered(lambda l: l.remaining_qty > 0)
            rec.active_inventory_line_ids = active_lines
            rec.inventory_count = len(active_lines)

    # === Sotuv buyurtmalari ===
    pos_order_count = fields.Integer(string='Sotuvlar Soni', compute='_compute_financials')
    pos_order_ids = fields.Many2many('van.pos.order', compute='_compute_financials', string="Sotuvlar Ro'yxati")

    # === Chiqimlar ro'yxati (computed, for tab display & deletion) ===
    chiqim_ids = fields.Many2many(
        'van.payment',
        compute='_compute_financials',
        string='Chiqimlar',
    )
    
    # === Kirimlar ro'yxati (computed, for tab display) ===
    kirim_ids = fields.Many2many(
        'van.payment',
        compute='_compute_financials',
        string='Kirimlar',
    )

    @api.depends('date_from', 'date_to', 'agent_id')
    def _compute_financials(self):
        for rec in self:
            tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
            utc_start = None
            utc_end = None

            if rec.date_from:
                local_start = tz.localize(datetime.combine(rec.date_from, time.min))
                utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            if rec.date_to:
                local_end = tz.localize(datetime.combine(rec.date_to, time.max))
                utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
            
            # --- POS Orders ---
            order_domain = [('agent_id', '=', rec.agent_id.id), ('state', '=', 'done')]
            if utc_start: order_domain.append(('date', '>=', utc_start))
            if utc_end: order_domain.append(('date', '<=', utc_end))
            orders = self.env['van.pos.order'].search(order_domain)
            
            # --- Payments (Kirim / Chiqim) ---
            payment_domain = [('agent_id', '=', rec.agent_id.id)]
            if utc_start: payment_domain.append(('date', '>=', utc_start))
            if utc_end: payment_domain.append(('date', '<=', utc_end))
            all_payments = self.env['van.payment'].search(payment_domain)
            
            kirims = all_payments.filtered(lambda p: p.payment_type == 'in')
            chiqims = all_payments.filtered(lambda p: p.payment_type == 'out')
            
            # --- Calculations ---
            rec.pos_order_ids = orders
            rec.pos_order_count = len(orders)
            rec.kirim_ids = kirims
            rec.chiqim_ids = chiqims
            
            total = sum(orders.mapped('amount_total'))
            
            # Sum up all orders with no partner attached, as those are cash-in-hand
            naqt_savdo_total = sum(o.amount_total for o in orders if not o.partner_id)
            kirim_total = sum(kirims.mapped('amount'))
            chiqim_total = sum(chiqims.mapped('amount'))
            
            cash = naqt_savdo_total + kirim_total
            
            # Nasiya = (Total Sales within date) - (Naqt Savdo within date) + Nasiyalar received
            # According to User rules: Nasiya in period = credit sales made within selected dates only
            nasiya = sum(o.amount_total for o in orders if o.partner_id)

            rec.total_cash = cash
            rec.total_nasiya = nasiya
            rec.total_sales = total
            rec.total_chiqim = chiqim_total
            
            # Balans in period = (Naqt + Nasiya received) - Chiqim for selected dates only
            rec.total_balance = cash - chiqim_total
            
            # Foyda calculation exactly: logic margin = (actual price - original cost_price) * qty 
            margin_period = 0.0
            for order in orders:
                for line in order.line_ids:
                    cost_unit = line.product_id.cost_price or 0.0
                    margin_period += (line.price_unit - cost_unit) * line.qty
            rec.total_foyda = margin_period
            
            # Agentdan qoladigan pul = Foyda (period) - Oylik Balansi (accumulated)
            # The user explicitly mandated this math match the on-screen numbers exactly
            rec.qoladigan_pul = margin_period - rec.oylik_balansi

    def action_view_pos_orders(self):
        self.ensure_one()
        order_domain = [('agent_id', '=', self.agent_id.id)]
        tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        
        if self.date_from:
            local_start = tz.localize(datetime.combine(self.date_from, time.min))
            utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            order_domain.append(('date', '>=', utc_start))
        if self.date_to:
            local_end = tz.localize(datetime.combine(self.date_to, time.max))
            utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
            order_domain.append(('date', '<=', utc_end))

        orders = self.env['van.pos.order'].search(order_domain)
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Sotuvlar',
            'res_model': 'van.pos.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
            'target': 'current',
        }

    def action_view_chiqimlar(self):
        self.ensure_one()
        domain = [('agent_id', '=', self.agent_id.id), ('payment_type', '=', 'out')]
        tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        
        if self.date_from:
            local_start = tz.localize(datetime.combine(self.date_from, time.min))
            utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append(('date', '>=', utc_start))
        if self.date_to:
            local_end = tz.localize(datetime.combine(self.date_to, time.max))
            utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append(('date', '<=', utc_end))
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Chiqimlar',
            'res_model': 'van.payment',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_view_kirimlar(self):
        self.ensure_one()
        domain = [('agent_id', '=', self.agent_id.id), ('payment_type', '=', 'in')]
        tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        
        if self.date_from:
            local_start = tz.localize(datetime.combine(self.date_from, time.min))
            utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append(('date', '>=', utc_start))
        if self.date_to:
            local_end = tz.localize(datetime.combine(self.date_to, time.max))
            utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
            domain.append(('date', '<=', utc_end))
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Kirimlar',
            'res_model': 'van.payment',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_view_inventory_kanban(self):
        self.ensure_one()
        view_id = self.env.ref('van_sales_pharma.view_van_agent_summary_inventory_dashboard').id
        return {
            'type': 'ir.actions.act_window',
            'name': f"{self.agent_id.name} - Olib Yurgan Mahsulotlar",
            'res_model': 'van.agent.summary',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view_id, 'form')],
            'target': 'current',
        }

class VanAgentInventoryLine(models.Model):
    """
    Agentning mashina omboridagi mahsulotlar ro'yxati.
    """
    _name = 'van.agent.inventory.line'
    _description = 'Agent Inventar Satri'

    summary_id = fields.Many2one('van.agent.summary', required=True, ondelete='cascade')
    product_id = fields.Many2one('van.product', string='Mahsulot', required=True)
    price_unit = fields.Float(string='Narx (So\'m)')
    cost_price = fields.Float(string='Kelish narxi', related='product_id.cost_price', readonly=True)

    loaded_qty = fields.Float(string='Yuklangan')
    # Not stored — always recomputes live so sold/remaining values reflect new POS orders immediately
    sold_qty = fields.Float(string='Sotilgan', compute='_compute_remaining')
    returned_qty = fields.Float(string='Qaytarilgan', compute='_compute_remaining')
    remaining_qty = fields.Float(string='Qoldiq', compute='_compute_remaining')

    currency_id = fields.Many2one('res.currency', related='summary_id.currency_id')
    subtotal_sold = fields.Monetary(string='Sotuv Summasi', currency_field='currency_id',
                                    compute='_compute_remaining')

    @api.depends('summary_id.date_from', 'summary_id.date_to', 'summary_id.agent_id', 'product_id', 'loaded_qty')
    def _compute_remaining(self):
        """
        Compute sold, returned and remaining quantities for each inventory line.
        Uses optimized search to reflect current POS state.
        """
        for line in self:
            agent_id = line.summary_id.agent_id.id
            date_from = line.summary_id.date_from
            date_to = line.summary_id.date_to
            product_id = line.product_id.id

            # Common domain parts
            base_domain = [
                ('order_id.agent_id', '=', agent_id),
                ('order_id.state', '=', 'done'),
                ('product_id', '=', product_id),
            ]

            # 1. All-time sold qty 
            fast_pos_lines = self.env['van.pos.order.line'].search(base_domain)
            all_time_sold = sum(fast_pos_lines.mapped('qty'))

            # 2. Period sold qty (shown in the 'Sotilgan' column for the chosen date range)
            period_sold = 0.0
            if date_from or date_to:
                tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
                period_domain = list(base_domain)
                if date_from:
                    local_start = tz.localize(datetime.combine(date_from, time.min))
                    utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
                    period_domain.append(('order_id.date', '>=', utc_start))
                if date_to:
                    local_end = tz.localize(datetime.combine(date_to, time.max))
                    utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
                    period_domain.append(('order_id.date', '<=', utc_end))
                
                period_lines = self.env['van.pos.order.line'].search(period_domain)
                period_sold = sum(period_lines.mapped('qty'))

            # 3. Ostatka qty
            ostatka_records = self.env['van.agent.ostatka'].search([
                ('agent_id', '=', agent_id),
                ('product_id', '=', product_id)
            ])
            ostatka_qty = sum(ostatka_records.mapped('qty'))

            line.sold_qty = period_sold
            line.returned_qty = 0.0
            line.remaining_qty = max(0.0, (line.loaded_qty + ostatka_qty) - all_time_sold)
            line.subtotal_sold = period_sold * line.price_unit
