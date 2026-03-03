from odoo import models, fields, api
class ResUsers(models.Model):
    _inherit = 'res.users'

    x_phone = fields.Char(string='Telefon Raqami')
    x_commission_balance = fields.Monetary(string='Komissiya Balansi', currency_field='x_currency_id', default=0.0)
    x_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    @api.model
    def _get_login_action(self, *args, **kwargs):
        res = super()._get_login_action(*args, **kwargs)
        if self.env.user.has_group('van_sales_pharma.group_van_agent') and not self.env.user.has_group('van_sales_pharma.group_van_admin') and not self.env.user.has_group('base.group_system'):
            pos_action = self.env.ref('van_sales_pharma.action_van_mobile_pos', raise_if_not_found=False)
            if pos_action:
                return pos_action.read()[0]
        return res
