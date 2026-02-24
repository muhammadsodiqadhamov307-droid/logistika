import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_van_total_due = fields.Monetary(
        string='Jami Nasiya Qarzi',
        compute='_compute_van_nasiya_stats',
        help="Mijozning yopilmagan (ochiq) nasiya summasi."
    )
    x_van_total_overdue = fields.Monetary(
        string='Muddati O\'tgan Nasiya',
        compute='_compute_van_nasiya_stats',
        help="To'lov muddati o'tgan nasiyalar summasi."
    )
    x_van_nasiya_count = fields.Integer(
        string='Ochiq Nasiyalar Soni',
        compute='_compute_van_nasiya_stats'
    )
    
    x_van_balance = fields.Monetary(
        string='Mijoz Balansi',
        compute='_compute_van_nasiya_stats',
        help="Mijozning haqiqiy qarz balansi (Jami Nasiya - Jami Kirim)."
    )
    
    x_van_total_cash = fields.Monetary(
        string='Jami Naqt To\'lovlar',
        compute='_compute_van_payment_stats',
        help="Sotuvchi agentlarga qilingan jami naqt to'lovlar."
    )
    x_van_total_card = fields.Monetary(
        string='Jami Karta To\'lovlar',
        compute='_compute_van_payment_stats',
        help="Sotuvchi agentlarga qilingan jami karta to'lovlar."
    )
    x_van_total_nasiya = fields.Monetary(
        string='Jami Nasiya Savdo (Tarixiy)',
        compute='_compute_van_payment_stats',
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
        help="Mijozning barcha xaridlari (POS) umumiy summasi."
    )

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
            
            # Sof hamyon xisobi (Wallet Balance)
            # Mijoz pul to'lasa (Kirim) -> Balans ko'payadi (+)
            # Mijozga pul qaytarilsa (Chiqim) yki Nasiyaga mahsulot olsa -> Balans kamayadi (-)
            wallet_balance = total_kirim - total_chiqim - total_nasiya
            
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
