from odoo import models, fields, api, _
from datetime import datetime, time
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
    date_from = fields.Date(string='Dastlabki Sana', default=fields.Date.context_today)
    date_to = fields.Date(string='Oxirgi Sana', default=fields.Date.context_today)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    # === Moliyaviy ko'rsatkichlar ===
    total_cash = fields.Monetary(string='Naqt Pul', currency_field='currency_id',
                                 compute='_compute_financials')
    total_card = fields.Monetary(string='Karta', currency_field='currency_id',
                                 compute='_compute_financials')
    total_nasiya = fields.Monetary(string='Nasiya (Qarz)', currency_field='currency_id',
                                   compute='_compute_financials')
    total_chiqim = fields.Monetary(string='Chiqim (Xarajat)', currency_field='currency_id',
                                  compute='_compute_financials')
    total_sales = fields.Monetary(string='Jami Sotuv', currency_field='currency_id',
                                  compute='_compute_financials')
    total_balance = fields.Monetary(string='Mavjud Balans', currency_field='currency_id',
                                   compute='_compute_financials',
                                   help="Ushbu oraliqdagi Naqt + Karta - Chiqim")

    # === Mahsulot inventariyasi ===
    inventory_line_ids = fields.One2many('van.agent.inventory.line', 'summary_id', string='Inventar')
    active_inventory_line_ids = fields.Many2many(
        'van.agent.inventory.line',
        compute='_compute_active_inventory',
        string="Faol Inventar"
    )

    def _compute_active_inventory(self):
        for rec in self:
            rec.active_inventory_line_ids = rec.inventory_line_ids.filtered(lambda l: l.remaining_qty > 0)

    # === Sotuv buyurtmalari ===
    pos_order_count = fields.Integer(string='Sotuvlar Soni', compute='_compute_financials')
    pos_order_ids = fields.Many2many('pos.order', compute='_compute_financials', string="Sotuvlar Ro'yxati")

    # === Chiqimlar ro'yxati (computed, for tab display & deletion) ===
    chiqim_ids = fields.Many2many(
        'van.payment',
        compute='_compute_chiqim_ids',
        string='Chiqimlar',
    )

    @api.depends('date_from', 'date_to', 'agent_id')
    def _compute_chiqim_ids(self):
        for rec in self:
            domain = [
                ('agent_id', '=', rec.agent_id.id),
                ('payment_type', '=', 'out'),
            ]
            if rec.date_from:
                domain.append(('date', '>=', rec.date_from))
            if rec.date_to:
                domain.append(('date', '<=', rec.date_to))
            chiqims = self.env['van.payment'].search(domain)
            rec.chiqim_ids = chiqims

    @api.depends('date_from', 'date_to', 'agent_id')
    def _compute_financials(self):
        for rec in self:
            cash = card = nasiya = total = chiqim = 0
            
            # Domain for POS orders
            order_domain = [
                ('user_id', '=', rec.agent_id.id),
                ('state', 'in', ['paid', 'done', 'invoiced'])
            ]
            
            # Use proper timezone localization for date conversion to UTC
            tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
            
            if rec.date_from:
                local_start = tz.localize(datetime.combine(rec.date_from, time.min))
                utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
                order_domain.append(('date_order', '>=', utc_start))
            if rec.date_to:
                local_end = tz.localize(datetime.combine(rec.date_to, time.max))
                utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
                order_domain.append(('date_order', '<=', utc_end))
                
            orders = self.env['pos.order'].search(order_domain)
            count = len(orders)
            
            for order in orders:
                total += order.amount_total
                for payment in order.payment_ids:
                    pm = payment.payment_method_id
                    if pm.is_cash_count:
                        cash += payment.amount
                    elif pm.split_transactions:
                        nasiya += payment.amount
                    else:
                        card += payment.amount
            
            # --- Integrate van.payments (POS Kirim/Chiqim tracked via our custom pos_session override) ---
            payment_domain = [
                ('agent_id', '=', rec.agent_id.id),
            ]
            if rec.date_from:
                payment_domain.append(('date', '>=', rec.date_from))
            if rec.date_to:
                payment_domain.append(('date', '<=', rec.date_to))

            van_payments = self.env['van.payment'].search(payment_domain)
            for vp in van_payments:
                if vp.payment_type == 'in':
                    if vp.payment_method == 'cash':
                        cash += vp.amount
                    else:
                        card += vp.amount
                elif vp.payment_type == 'out':
                    chiqim += vp.amount

            rec.total_cash = cash
            rec.total_card = card
            rec.total_nasiya = nasiya
            rec.total_sales = total
            rec.pos_order_count = count
            rec.pos_order_ids = [(6, 0, orders.ids)]
            rec.total_chiqim = chiqim
            rec.total_balance = (cash + card) - chiqim

    def action_view_pos_orders(self):
        self.ensure_one()
        order_domain = [('user_id', '=', self.agent_id.id)]
        if self.date_from:
            order_domain.append(('date_order', '>=', datetime.combine(self.date_from, time.min)))
        if self.date_to:
            order_domain.append(('date_order', '<=', datetime.combine(self.date_to, time.max)))

        orders = self.env['pos.order'].search(order_domain)
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Sotuvlar',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
            'target': 'current',
        }

    def action_view_chiqimlar(self):
        self.ensure_one()
        domain = [('agent_id', '=', self.agent_id.id), ('payment_type', '=', 'out')]
        if self.date_from:
            domain.append(('date', '>=', str(self.date_from)))
        if self.date_to:
            domain.append(('date', '<=', str(self.date_to)))
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Chiqimlar',
            'res_model': 'van.payment',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }



class VanAgentInventoryLine(models.Model):
    """
    Agentning mashina omboridagi mahsulotlar ro'yxati.
    """
    _name = 'van.agent.inventory.line'
    _description = 'Agent Inventar Satri'

    summary_id = fields.Many2one('van.agent.summary', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Mahsulot', required=True)
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string="O'lchov")
    price_unit = fields.Float(string='Narx (So\'m)')

    loaded_qty = fields.Float(string='Yuklangan')
    # Not stored — always recomputes live so sold/remaining values reflect new POS orders immediately
    sold_qty = fields.Float(string='Sotilgan', compute='_compute_remaining')
    returned_qty = fields.Float(string='Qaytarilgan', compute='_compute_remaining')
    remaining_qty = fields.Float(string='Qoldiq', compute='_compute_remaining')

    currency_id = fields.Many2one('res.currency', related='summary_id.currency_id')
    subtotal_sold = fields.Monetary(string='Sotuv Summasi', currency_field='currency_id',
                                    compute='_compute_remaining')

    def _compute_remaining(self):
        """
        Compute sold, returned and remaining quantities for each inventory line.
        Uses direct SQL for performance. Not stored so it always reflects current POS state.
        """
        for line in self:
            agent_id = line.summary_id.agent_id.id
            date_from = line.summary_id.date_from
            date_to = line.summary_id.date_to
            product_id = line.product_id.id

            # 1. All-time sold qty (used for remaining balance)
            all_time_domain = [
                ('order_id.user_id', '=', agent_id),
                ('order_id.state', 'in', ['paid', 'done', 'invoiced']),
                ('product_id', '=', product_id),
            ]
            all_lines = self.env['pos.order.line'].search(all_time_domain)
            all_time_sold = sum(all_lines.mapped('qty'))

            # 2. Period sold qty (shown in the Sotilgan column for the chosen date range)
            if date_from or date_to:
                tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
                period_domain = list(all_time_domain)
                if date_from:
                    local_start = tz.localize(datetime.combine(date_from, time.min))
                    utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
                    period_domain.append(('order_id.date_order', '>=', utc_start))
                if date_to:
                    local_end = tz.localize(datetime.combine(date_to, time.max))
                    utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
                    period_domain.append(('order_id.date_order', '<=', utc_end))
                period_lines = self.env['pos.order.line'].search(period_domain)
                period_sold = sum(period_lines.mapped('qty'))
            else:
                period_sold = all_time_sold

            line.sold_qty = period_sold
            line.returned_qty = 0.0
            line.remaining_qty = max(0.0, line.loaded_qty - all_time_sold)
            line.subtotal_sold = period_sold * line.price_unit
