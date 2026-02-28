from odoo import models, fields, api

class VanProduct(models.Model):
    _name = 'van.product'
    _description = 'Van Sales Product'
    _order = 'name'

    name = fields.Char(string='Mahsulot Nomi', required=True, translate=True)
    qty = fields.Float(string='Soni', default=0.0, help="Umumiy ombordagi soni")
    cost_price = fields.Float(string='Kelish Narxi', default=0.0)
    list_price = fields.Float(string='Sotish Narxi', default=0.0)
    image_1920 = fields.Image(string='Rasm')

    # Optional fields for future use or metrics
    active = fields.Boolean(default=True, string='Faol')
    company_id = fields.Many2one('res.company', string='Korxona', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)
