import logging
from odoo import models, fields, tools

_logger = logging.getLogger(__name__)

class VanDashboardDetail(models.Model):
    _name = 'van.dashboard.detail'
    _description = 'Moliya Paneli Tafsilotlari (Kirim / Chiqim / Savdo)'
    _auto = False
    _order = 'date desc, id desc'

    name = fields.Char('Hujjat Raqami', readonly=True)
    date = fields.Datetime('Sana', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Mijoz', readonly=True)
    amount = fields.Float('Summa', readonly=True)
    payment_method = fields.Selection([
        ('cash', 'Naqt'),
        ('card', 'Karta'),
        ('nasiya', 'Nasiya')
    ], 'To\'lov Usuli', readonly=True)
    transaction_type = fields.Selection([
        ('sale', 'Savdo (POS)'),
        ('kirim', 'Kirim (+)'),
        ('chiqim', 'Chiqim (-)')
    ], 'Amaliyot Turi', readonly=True)
    note = fields.Text('Izoh', readonly=True)
    
    company_id = fields.Many2one('res.company', 'Korxona', readonly=True)
    currency_id = fields.Many2one('res.currency', 'Valyuta', readonly=True)
    
    res_id = fields.Integer('Resurs ID', readonly=True)
    res_model = fields.Char('Resurs Modeli', readonly=True)

    def action_open_record(self):
        """ Redirect to the actual record form view """
        self.ensure_one()
        if not self.res_id or not self.res_model:
            return False
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW van_dashboard_detail AS (
                -- 1. POS Payments (Sales)
                SELECT 
                    pp.id + 1000000 AS id, 
                    po.name AS name,
                    pp.payment_date AS date,
                    po.partner_id AS partner_id,
                    pp.amount AS amount,
                    CASE 
                        WHEN pm.is_cash_count = TRUE THEN 'cash'
                        WHEN pm.split_transactions = TRUE THEN 'nasiya'
                        ELSE 'card'
                    END AS payment_method,
                    'sale' AS transaction_type,
                    '' AS note,
                    po.company_id AS company_id,
                    rc.currency_id AS currency_id,
                    po.id AS res_id,
                    'pos.order' AS res_model
                FROM pos_payment pp
                JOIN pos_order po ON pp.pos_order_id = po.id
                JOIN pos_payment_method pm ON pp.payment_method_id = pm.id
                JOIN res_company rc ON po.company_id = rc.id
                WHERE po.state IN ('paid', 'done', 'invoiced')

                UNION ALL

                -- 2. Van Payments (Kirim/Chiqim)
                SELECT 
                    vp.id + 2000000 AS id,
                    vp.name AS name,
                    vp.date AS date,
                    vp.partner_id AS partner_id,
                    vp.amount AS amount,
                    vp.payment_method AS payment_method,
                    CASE WHEN vp.payment_type = 'in' THEN 'kirim' ELSE 'chiqim' END AS transaction_type,
                    vp.note AS note,
                    vp.company_id AS company_id,
                    vp.currency_id AS currency_id,
                    vp.id AS res_id,
                    'van.payment' AS res_model
                FROM van_payment vp
            )
        """)
