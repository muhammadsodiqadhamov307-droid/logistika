from odoo import models, fields, api
class ResUsers(models.Model):
    _inherit = 'res.users'

    x_phone = fields.Char(string='Telefon Raqami')
    x_commission_balance = fields.Monetary(string='Komissiya Balansi', currency_field='x_currency_id', default=0.0)
    x_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # === Oylik (Salary/Commission) Fields ===
    komissiya_foizi = fields.Float(string='Komissiya foizi (%)', default=0.0,
                                   help="Sotuvdan agentga qoladigan ulush foizi (masalan 5% bo'lsa 5 yoziladi)")
    oylik_balansi = fields.Monetary(string='Oylik Balansi', compute='_compute_oylik_balansi',
                                    currency_field='x_currency_id',
                                    help="Agentning joriy oylik komissiyalari yig'indisi minus Oylik Chiqimlar")

    ostatka_ids = fields.One2many('van.agent.ostatka', 'agent_id', string='Boshlang\'ich qoldiq (Ostatka)')
    salary_payout_ids = fields.One2many('van.salary.payout', 'agent_id', string='Oylik To\'lovlar Tarixi')
    default_taminotchi_id = fields.Many2one('van.taminotchi', string="Asosiy Taminotchi", help="Yangi Yuklash qilishda avtomatik tanlanuvchi Taminotchi")

    agent_oyligi = fields.Monetary(
        string='Agent Oyligi', 
        compute='_compute_agent_oyligi', 
        currency_field='x_currency_id',
        help="Komissiya - Oylik Chiqimlar"
    )
    agent_chiqim_ids = fields.One2many(
        'van.payment', 'agent_id', 
        string="Oylik To'lovlar Tarixi", 
        domain=[('payment_type', '=', 'out'), ('expense_type', '=', 'salary')]
    )

    def _compute_agent_oyligi(self):
        for user in self:
            user.agent_oyligi = user.oylik_balansi

    def _compute_oylik_balansi(self):
        for user in self:
            # 1. Total Commission Earned (sales with state='done')
            # Instead of multiplying all historic sales by the current percentage, 
            # we sum up the explicitly locked commission_amount from the POS Order to allow percentage changes securely.
            pos_orders = self.env['van.pos.order'].search([
                ('agent_id', '=', user.id),
                ('state', '=', 'done')
            ])
            total_earned = sum(pos_orders.mapped('commission_amount'))

            # 2. Total Salary Paid Out (van.payment where expense_type in ('salary', 'payout'))
            # 'salary' is for intermediate advance payments (Chiqim)
            # 'payout' is for final salary close (Oylik Yopish)
            salary_payments = self.env['van.payment'].search([
                ('agent_id', '=', user.id),
                ('payment_type', '=', 'out'),
                ('expense_type', 'in', ('salary', 'payout'))
            ])
            total_paid = sum(salary_payments.mapped('amount'))

            user.oylik_balansi = total_earned - total_paid

    def action_close_salary(self):
        """
        Opens a wizard to pay out the entire remaining oylik_balansi to the agent.
        """
        self.ensure_one()
        return {
            'name': 'Oylik Yopish (To\'lov)',
            'type': 'ir.actions.act_window',
            'res_model': 'van.salary.payout.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_agent_id': self.id,
                'default_amount': self.oylik_balansi,
                'default_notes': f"Oylik qoldig'ini yopish. Komissiya foizi: {self.komissiya_foizi}%"
            }
        }

    @api.model
    def _get_login_action(self, *args, **kwargs):
        res = super()._get_login_action(*args, **kwargs)
        if self.env.user.has_group('van_sales_pharma.group_van_agent') and not self.env.user.has_group('van_sales_pharma.group_van_admin') and not self.env.user.has_group('base.group_system'):
            pos_action = self.env.ref('van_sales_pharma.action_van_mobile_pos_app', raise_if_not_found=False)
            if pos_action:
                return pos_action.read()[0]
        return res
