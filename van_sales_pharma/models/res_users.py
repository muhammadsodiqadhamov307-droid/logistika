from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    x_phone = fields.Char(string='Telefon Raqami')
    x_commission_balance = fields.Monetary(string='Komissiya Balansi', currency_field='x_currency_id', default=0.0)
    x_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
