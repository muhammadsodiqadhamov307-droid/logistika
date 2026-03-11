import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'
    currency_id = fields.Many2one('res.currency', string='Valyuta', related='company_id.currency_id', readonly=True)
    telegram_chat_id = fields.Char(string='Telegram Chat ID', help="Avtomatik ravishda bot orqali to'ldiriladi.")

    x_van_total_due = fields.Monetary(
        string='Jami Nasiya Qarzi',
        compute='_compute_van_nasiya_stats',
        currency_field='currency_id',
        help="Mijozning yopilmagan (ochiq) nasiya summasi."
    )
    x_van_total_overdue = fields.Monetary(
        string='Muddati O\'tgan Nasiya',
        compute='_compute_van_nasiya_stats',
        currency_field='currency_id',
        help="To'lov muddati o'tgan nasiyalar summasi."
    )
    x_van_nasiya_count = fields.Integer(
        string='Ochiq Nasiyalar Soni',
        compute='_compute_van_nasiya_stats'
    )
    
    x_van_ostatka_ids = fields.One2many(
        'van.ostatka.qarzi', 'partner_id',
        string="Mijoz Ostatka Qarzi"
    )
    x_van_ostatka_total = fields.Monetary(
        string="Jami Ostatka Qarzi",
        compute='_compute_van_nasiya_stats',
        currency_field='currency_id',
        help="Systemadan oldingi tarixiy qarzlar yig'indisi"
    )
    
    x_van_balance = fields.Monetary(
        string='Mijoz Balansi',
        compute='_compute_van_nasiya_stats',
        currency_field='currency_id',
        help="Mijozning haqiqiy qarz balansi (Jami Nasiya - Jami Kirim)."
    )
    
    x_van_total_cash = fields.Monetary(
        string='Jami Naqt To\'lovlar',
        compute='_compute_van_payment_stats',
        currency_field='currency_id',
        help="Sotuvchi agentlarga qilingan jami naqt to'lovlar."
    )
    x_van_total_card = fields.Monetary(
        string='Jami Karta To\'lovlar',
        compute='_compute_van_payment_stats',
        currency_field='currency_id',
        help="Sotuvchi agentlarga qilingan jami karta to'lovlar."
    )
    x_van_total_nasiya = fields.Monetary(
        string='Jami Nasiya Savdo (Tarixiy)',
        compute='_compute_van_payment_stats',
        currency_field='currency_id',
        help="Mijoz ushbu korxonadan olgan jami nasiya savdolari."
    )
    
    x_van_pos_product_count = fields.Integer(
        string='Olingan Mahsulotlar (Soni)',
        compute='_compute_van_pos_stats',
        help="Mijoz xarid qilgan jami mahsulotlar soni."
    )
    x_van_pos_total_sum = fields.Monetary(
        string='Jami Xarid Summasi',
        compute='_compute_van_pos_stats',
        currency_field='currency_id',
        help="Mijozning barcha xaridlari (POS) umumiy summasi."
    )
    
    x_van_hisob_kitob_html = fields.Html(
        string="Hisob-kitob (Ledger)",
        compute='_compute_van_hisob_kitob_html',
        help="Mijozning qarz va to'lovlar xronologiyasi"
    )

    def _compute_van_hisob_kitob_html(self):
        for partner in self:
            transactions = []
            
            # 1. Boshlang'ich qarz (Ostatka)
            for ostatka in partner.x_van_ostatka_ids:
                if ostatka.amount > 0:
                    transactions.append({
                        'date': ostatka.date or fields.Date.today(),
                        'hujjat': 'Ostatka Qarzi',
                        'turi': "🟠 Boshlang'ich qarz",
                        'summa': ostatka.amount,
                        'is_debt': True,
                    })
                    
            # 2. Sotuvlar (POS Orders)
            pos_orders = self.env['van.pos.order'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'done')
            ])
            for order in pos_orders:
                if order.amount_total > 0:
                    transactions.append({
                        'date': order.date.date() if order.date else fields.Date.today(),
                        'hujjat': order.name,
                        'turi': "🛒 Sotuv",
                        'summa': order.amount_total,
                        'is_debt': True,
                    })
                    
            # 3. Kirimlar (Payments)
            payments = self.env['van.payment'].search([
                ('partner_id', '=', partner.id),
                ('payment_type', '=', 'in')
            ])
            for payment in payments:
                if payment.amount > 0:
                    transactions.append({
                        'date': payment.date.date() if payment.date else fields.Date.today(),
                        'hujjat': payment.name,
                        'turi': "💵 Kirim",
                        'summa': payment.amount,
                        'is_debt': False,
                    })
                    
            # Sort all transactions chronologically by date
            transactions.sort(key=lambda x: x['date'])
            
            # Build HTML table
            html = """
            <div class="table-responsive">
                <table class="table table-sm table-hover table-striped mb-0" style="border: 1px solid #dee2e6;">
                    <thead class="table-light">
                        <tr>
                            <th>Sana</th>
                            <th>Hujjat</th>
                            <th>Turi</th>
                            <th class="text-end">Summa</th>
                            <th class="text-end">Balans</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            if not transactions:
                html += """
                    <tr>
                        <td colspan="5" class="text-center text-muted py-3">Ma'lumot topilmadi</td>
                    </tr>
                """
            
            running_balance = 0.0
            for rx in transactions:
                d_str = rx['date'].strftime('%d.%m.%Y')
                turi_badge = f'<span class="badge rounded-pill bg-success">{rx["turi"]}</span>' if rx['turi'] == "🛒 Sotuv" else (f'<span class="badge rounded-pill bg-info text-dark">{rx["turi"]}</span>' if rx['turi'] == "💵 Kirim" else f'<span class="badge rounded-pill bg-warning text-dark">{rx["turi"]}</span>')
                
                if rx['is_debt']:
                    running_balance += rx['summa']
                    sum_html = f'<span class="text-danger fw-bold">+{rx["summa"]:,.0f}</span>'
                else:
                    running_balance -= rx['summa']
                    sum_html = f'<span class="text-success fw-bold">-{rx["summa"]:,.0f}</span>'
                    
                bal_color = 'text-danger fw-bold' if running_balance > 0 else 'text-success fw-bold'
                
                html += f"""
                    <tr>
                        <td>{d_str}</td>
                        <td class="fw-bold">{rx['hujjat']}</td>
                        <td>{turi_badge}</td>
                        <td class="text-end">{sum_html}</td>
                        <td class="text-end {bal_color}">{running_balance:,.0f}</td>
                    </tr>
                """
                
            html += "</tbody></table></div>"
            
            # Render the Grand Total at the bottom
            final_color = 'text-danger' if running_balance > 0 else 'text-success'
            html += f"""
            <div class="mt-3 text-end">
                <h4 class="{final_color} fw-bold">Jami Qarz: {running_balance:,.0f} so'm</h4>
            </div>
            """
            
            partner.x_van_hisob_kitob_html = html

    def _compute_van_pos_stats(self):
        for partner in self:
            pos_orders = self.env['pos.order'].search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ['paid', 'done', 'invoiced'])
            ])
            partner.x_van_pos_total_sum = sum(pos_orders.mapped('amount_total'))
            
            qty = sum(sum(order.lines.mapped('qty')) for order in pos_orders)
            partner.x_van_pos_product_count = int(qty)

    def action_van_kirim(self):
        self.ensure_one()
        return {
            'name': "Kirim (Qarzni Undirish)",
            'type': 'ir.actions.act_window',
            'res_model': 'van.payment',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.id,
                'default_payment_type': 'in',
                'default_amount': self.x_van_total_due if self.x_van_total_due > 0 else 0.0,
            },
            'target': 'new',
        }

    def action_view_van_pos_orders(self):
        self.ensure_one()
        return {
            'name': "Mijoz Xaridlari (POS)",
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id), ('state', 'in', ['paid', 'done', 'invoiced'])],
            'context': {'create': False},
        }

    def action_view_van_pos_lines(self):
        self.ensure_one()
        pos_orders = self.env['pos.order'].search([
            ('partner_id', '=', self.id),
            ('state', 'in', ['paid', 'done', 'invoiced'])
        ])
        return {
            'name': "Olingan Mahsulotlar (POS)",
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order.line',
            'view_mode': 'list,form',
            'domain': [('order_id', 'in', pos_orders.ids)],
            'context': {'create': False},
        }

    def action_view_van_balance_details(self):
        self.ensure_one()
        return {
            'name': "Nasiyalar va To'lovlar (Balans)",
            'type': 'ir.actions.act_window',
            'res_model': 'van.nasiya',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'create': False},
        }

    @api.depends('invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.amount_residual')
    def _compute_van_nasiya_stats(self):
        for partner in self:
            # Jami olingan Nasiyalar (Tarixiy summa)
            nasiyas = self.env['van.nasiya'].search([
                ('partner_id', '=', partner.id)
            ])
            total_nasiya = sum(n.amount_total for n in nasiyas)
            
            # Mijozdan kelgan barcha qarz uzish to'lovlari (Kirimlar) va Mijozga qaytarilgan pullar (Chiqimlar)
            payments = self.env['van.payment'].search([
                ('partner_id', '=', partner.id)
            ])
            total_kirim = sum(p.amount for p in payments if p.payment_type == 'in')
            total_chiqim = sum(p.amount for p in payments if p.payment_type == 'out')
            
            # Ostatka (Opening Balance Debts)
            total_ostatka = sum(o.amount for o in partner.x_van_ostatka_ids)
            
            # Sof hamyon xisobi (Wallet Balance)
            # Mijoz pul to'lasa (Kirim) -> Balans ko'payadi (+)
            # Mijozga pul qaytarilsa (Chiqim) yki Nasiyaga mahsulot olsa -> Balans kamayadi (-)
            # Ostatka qarz (avvaldan qolgan qarz) -> Balans kamayadi (-)
            wallet_balance = total_kirim - total_chiqim - total_nasiya - total_ostatka
            
            # Eski method: Overdue hisoblash
            overdue_amount = 0.0
            today = fields.Date.today()
            for n in nasiyas:
                if n.state in ['open', 'partial'] and n.invoice_id and n.invoice_id.invoice_date_due and n.invoice_id.invoice_date_due < today:
                    # Approximation for overdue. 
                    overdue_amount += n.amount_residual if hasattr(n, 'amount_residual') else n.amount_total

            # Agar hamyon balansi manfiy bo'lsa (0 dan kichik), demak u qarzdor. Qarz summasi balansning moduli.
            partner.x_van_total_due = abs(wallet_balance) if wallet_balance < 0 else 0.0
            partner.x_van_balance = wallet_balance
            partner.x_van_total_overdue = overdue_amount
            partner.x_van_nasiya_count = len([n for n in nasiyas if n.state in ['open', 'partial']])
            partner.x_van_ostatka_total = total_ostatka

    def _compute_van_payment_stats(self):
        for partner in self:
            # Payments matched by van.payment -> van.sale.order -> partner_id
            payments = self.env['van.payment'].search([
                ('sale_order_id.partner_id', '=', partner.id),
                ('state', '=', 'received')
            ])
            
            partner.x_van_total_cash = sum(p.amount for p in payments if p.payment_method == 'cash')
            partner.x_van_total_card = sum(p.amount for p in payments if p.payment_method == 'card')
            
            # Total strictly Nasiya Sales created (Historical)
            nasiyas = self.env['van.nasiya'].search([('partner_id', '=', partner.id)])
            partner.x_van_total_nasiya = sum(n.amount_total for n in nasiyas)

    @api.model
    def get_partner_van_debt(self, partner_id):
        """ RPC method called from the OWL frontend dashboard to get immediate customer stats """
        partner = self.browse(partner_id)
        if not partner.exists():
            return {}
            
        partner._compute_van_nasiya_stats() # Force compute for real-time
        return {
            'total_due': partner.x_van_total_due,
            'total_overdue': partner.x_van_total_overdue,
            'nasiya_count': partner.x_van_nasiya_count,
            'currency_id': partner.currency_id.id,
        }
