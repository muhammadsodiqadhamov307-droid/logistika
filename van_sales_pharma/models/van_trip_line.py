import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class VanTripLine(models.Model):
    _name = 'van.trip.line'
    _description = 'Kun Sayohati Mahsulotlari'

    trip_id = fields.Many2one('van.trip', string='Sayohat', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='trip_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='trip_id.currency_id', store=True)

    product_id = fields.Many2one('product.product', string='Mahsulot', required=True)
    uom_id = fields.Many2one('uom.uom', string='O\'lchov Birligi', related='product_id.uom_id')
    price_unit = fields.Float(string='Narx', required=True)

    loaded_qty = fields.Float(string='Yuklangan Miqdor', default=0.0, required=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.lst_price
