from odoo import models, fields, api


class VanAgentSummary(models.Model):
    """
    Har bir savdo agenti uchun umumiy hisobot modeli.
    Bu model faqat ko'rsatish uchun: bugungi trip va POS ma'lumotlardan
    hisoblanadigan yig'indilarni ko'rsatadi.
    """
    _name = 'van.agent.summary'
    _description = 'Agent Hisobot (Kunlik)'
    _order = 'date desc, agent_id'
    _rec_name = 'agent_id'

    agent_id = fields.Many2one('res.users', string='Agent', required=True, index=True)
    date = fields.Date(string='Sana', required=True, default=fields.Date.context_today, index=True)
    trip_id = fields.Many2one('van.trip', string='Sayohat')

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    # === Moliyaviy ko'rsatkichlar ===
    total_cash = fields.Monetary(string='Naqt Pul', currency_field='currency_id',
                                 compute='_compute_financials', store=True)
    total_card = fields.Monetary(string='Karta', currency_field='currency_id',
                                 compute='_compute_financials', store=True)
    total_nasiya = fields.Monetary(string='Nasiya (Qarz)', currency_field='currency_id',
                                   compute='_compute_financials', store=True)
    total_chiqim = fields.Monetary(string='Chiqim (Xarajat)', currency_field='currency_id',
                                  compute='_compute_financials', store=True)
    total_sales = fields.Monetary(string='Jami Sotuv', currency_field='currency_id',
                                  compute='_compute_financials', store=True)
    total_balance = fields.Monetary(string='Sotuv Agenti Balansi', currency_field='currency_id',
                                   compute='_compute_financials', store=True,
                                   help="Naqt + Karta - Chiqim")

    # === Mahsulot inventariyasi ===
    inventory_line_ids = fields.One2many('van.agent.inventory.line', 'summary_id', string='Inventar')

    # === Sotuv buyurtmalari ===
    pos_order_ids = fields.One2many('pos.order', 'x_agent_summary_id', string='POS Sotuvlar')
    pos_order_count = fields.Integer(string='Sotuvlar Soni', compute='_compute_financials', store=True)

    @api.depends('trip_id', 'trip_id.pos_order_ids', 'trip_id.pos_order_ids.payment_ids',
                 'trip_id.pos_order_ids.state', 'trip_id.pos_order_ids.amount_total',
                 'trip_id.payment_ids', 'trip_id.payment_ids.amount', 'trip_id.payment_ids.payment_type')
    def _compute_financials(self):
        for rec in self:
            cash = card = nasiya = total = count = chiqim = 0
            orders = rec.trip_id.pos_order_ids.filtered(
                lambda o: o.state in ['paid', 'done', 'invoiced']
            )
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
            
            # Count Chiqim from van.payments
            for vp in rec.trip_id.payment_ids:
                if vp.payment_type == 'out':
                    chiqim += vp.amount

            rec.total_cash = cash
            rec.total_card = card
            rec.total_nasiya = nasiya
            rec.total_sales = total
            rec.pos_order_count = count
            rec.total_chiqim = chiqim
            rec.total_balance = (cash + card) - chiqim

    def action_view_pos_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.agent_id.name} - Sotuvlar',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.trip_id.pos_order_ids.ids)],
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
    sold_qty = fields.Float(string='Sotilgan', compute='_compute_remaining', store=True)
    returned_qty = fields.Float(string='Qaytarilgan', compute='_compute_remaining', store=True)
    remaining_qty = fields.Float(string='Qoldiq', compute='_compute_remaining', store=True)

    currency_id = fields.Many2one('res.currency', related='summary_id.currency_id')
    subtotal_sold = fields.Monetary(string='Sotuv Summasi', currency_field='currency_id',
                                    compute='_compute_remaining', store=True)

    @api.depends('loaded_qty', 'price_unit', 'summary_id.trip_id.pos_order_ids', 'summary_id.trip_id.pos_order_ids.state', 'summary_id.trip_id.pos_order_ids.lines')
    def _compute_remaining(self):
        for line in self:
            # Calculate Sold Qty from POS orders of the trip
            # Note: POS lines refer to products. We sum qty for this product.
            sold = 0.0
            trip = line.summary_id.trip_id
            if trip:
                orders = trip.pos_order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
                for order in orders:
                    for l in order.lines:
                        if l.product_id == line.product_id:
                            sold += l.qty
            
            # Returned qty for now 0 or if we have a way to track returns in trip
            returned = 0.0 
            
            line.sold_qty = sold
            line.returned_qty = returned
            line.remaining_qty = line.loaded_qty - sold + returned
            line.subtotal_sold = sold * line.price_unit
