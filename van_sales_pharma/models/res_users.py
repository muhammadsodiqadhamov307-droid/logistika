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

            # 2. Total Salary Paid Out (van.payment where expense_type='salary')
            salary_payments = self.env['van.payment'].search([
                ('agent_id', '=', user.id),
                ('payment_type', '=', 'out'),
                ('expense_type', '=', 'salary')
            ])
            total_paid = sum(salary_payments.mapped('amount'))

            user.oylik_balansi = total_earned - total_paid

    def action_close_salary(self):
        """
        Pays out the entire remaining oylik_balansi to the agent.
        Creates a 'salary' expense payment.
        """
        for user in self:
            if user.oylik_balansi > 0.0:
                payment_vals = {
                    'agent_id': user.id,
                    'payment_type': 'out',
                    'expense_type': 'salary',
                    'amount': user.oylik_balansi,
                    'payment_method': 'cash',
                    'note': f"Oylik qoldig'ini yopish. Komissiya foizi: {user.komissiya_foizi}%"
                }
                self.env['van.payment'].create(payment_vals)

    @api.model
    def _get_login_action(self, *args, **kwargs):
        res = super()._get_login_action(*args, **kwargs)
        if self.env.user.has_group('van_sales_pharma.group_van_agent') and not self.env.user.has_group('van_sales_pharma.group_van_admin') and not self.env.user.has_group('base.group_system'):
            pos_action = self.env.ref('van_sales_pharma.action_van_mobile_pos', raise_if_not_found=False)
            if pos_action:
                return pos_action.read()[0]
        return res
