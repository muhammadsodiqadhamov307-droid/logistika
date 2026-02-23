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
    sold_qty = fields.Float(string='Sotilgan Miqdor', compute='_compute_sold_qty', store=True)
    returned_qty = fields.Float(string='Qaytarilgan Miqdor', default=0.0)
    remaining_qty = fields.Float(string='Qoldiq Miqdor', compute='_compute_remaining_qty', store=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.lst_price

    @api.depends('trip_id.pos_order_ids.lines.product_id', 'trip_id.pos_order_ids.state')
    def _compute_sold_qty(self):
        for line in self:
            sold_qty = 0.0
            # POS sotuvlardan ushbu mahsulotning sotilgan miqdorini hisoblash
            orders = line.trip_id.pos_order_ids.filtered(lambda o: o.state in ['paid', 'done', 'invoiced'])
            for order in orders:
                for order_line in order.lines.filtered(lambda ol: ol.product_id.id == line.product_id.id):
                    sold_qty += order_line.qty
            line.sold_qty = sold_qty

    @api.depends('loaded_qty', 'sold_qty', 'returned_qty')
    def _compute_remaining_qty(self):
        for line in self:
            line.remaining_qty = line.loaded_qty - line.sold_qty + line.returned_qty

    @api.constrains('remaining_qty')
    def _check_remaining_qty(self):
        for line in self:
            if line.remaining_qty < 0:
                raise ValidationError(_("Xatolik! '%s' mahsulotidan zaxira miqdori manfiy bo'lishi mumkin emas.", line.product_id.display_name))
