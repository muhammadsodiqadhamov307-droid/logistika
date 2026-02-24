import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class VanLoadWizard(models.TransientModel):
    _name = 'van.load.wizard'
    _description = 'Mashinaga Yuklash Wizardi'

    trip_id = fields.Many2one('van.trip', string='Sayohat', required=True, readonly=True)
    company_id = fields.Many2one('res.company', related='trip_id.company_id')
    
    warehouse_id = fields.Many2one('stock.warehouse', string='Asosiy Ombor', required=True, 
                                   default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1))
    
    load_line_ids = fields.One2many('van.load.line', 'wizard_id', string='Yuklanadigan Mahsulotlar')

    def action_load(self):
        self.ensure_one()
        if not self.load_line_ids:
            raise UserError(_("Yuklash uchun kamida bitta mahsulot kiritilishi shart!"))

        # Step 1: Create or update trip lines
        for line in self.load_line_ids:
            if line.qty <= 0:
                raise UserError(_("Miqdor 0 dan katta bo'lishi kerak: %s") % line.product_id.display_name)
                
            existing_line = self.env['van.trip.line'].search([
                ('trip_id', '=', self.trip_id.id),
                ('product_id', '=', line.product_id.id)
            ], limit=1)
            
            if existing_line:
                existing_line.loaded_qty += line.qty
            else:
                self.env['van.trip.line'].create({
                    'trip_id': self.trip_id.id,
                    'product_id': line.product_id.id,
                    'loaded_qty': line.qty,
                    'price_unit': line.product_id.lst_price,
                })

        # Step 2: Create a Stock Picking from Main Warehouse to Van Location
        # Find ANY internal transfer picking type for this company (active or archived)
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'), 
            ('company_id', '=', self.company_id.id),
            '|', ('active', '=', True), ('active', '=', False)
        ], order='sequence, id', limit=1)
        
        if picking_type and not picking_type.active:
            picking_type.active = True
            
        if not picking_type:
            # Auto-create if they completely deleted it from their database
            warehouse = self.warehouse_id or self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
            picking_type = self.env['stock.picking.type'].create({
                'name': 'Ichki Ko\'chirish (Avto)',
                'sequence_code': 'INT',
                'code': 'internal',
                'company_id': self.company_id.id,
                'warehouse_id': warehouse.id,
                'show_operations': True,
            })
            
        if not picking_type:
            raise UserError(_("Tizimda 'Internal Transfer' (Ichki Ko'chirish) operatsiya turini avtomatik yaratib bo'lmadi."))
        
        main_location = self.warehouse_id.lot_stock_id
        van_location = self.trip_id.location_id

        if not main_location or not van_location:
            raise UserError(_("Ombor manzillarini topishda xatolik yuz berdi. Tranzit ombor (Van Location) yoki Asosiy ombor belgilanmagan."))

        picking_vals = {
            'picking_type_id': picking_type.id if picking_type else False,
            'location_id': main_location.id,
            'location_dest_id': van_location.id,
            'origin': _('Yuklash: %s', self.trip_id.name),
            'company_id': self.company_id.id,
        }
        
        try:
            with self.env.cr.savepoint():
                picking = self.env['stock.picking'].create(picking_vals)
                for line in self.load_line_ids:
                    self.env['stock.move'].create({
                        'description_picking': line.product_id.name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.qty,
                        'uom_id': line.product_id.uom_id.id,
                        'picking_id': picking.id,
                        'location_id': main_location.id,
                        'location_dest_id': van_location.id,
                        'company_id': self.company_id.id,
                    })
                picking.action_confirm()
                picking.button_validate()  # Automate the transfer
                _logger.info("Ombor ko'chirish yozuvi tasdiqlandi: %s", picking.name)
        except Exception as e:
            _logger.error("Ombor zaxirasini siljitishda xatolik: %s", str(e))
            raise UserError(_("Ombor moduliga ulanishda xato: Mahsulot zaxirada yetarli bo'lmasligi mumkin!\n(%s)") % str(e))

        # Step 3: Change Trip State
        self.trip_id.state = 'loaded'
        
        # Return to the trip form to refresh the state and close popup
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'van.trip',
            'res_id': self.trip_id.id,
            'view_mode': 'form',
            'target': 'main',
        }


class VanLoadLine(models.TransientModel):
    _name = 'van.load.line'
    _description = 'Yuklash Satrlari'

    wizard_id = fields.Many2one('van.load.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Mahsulot', required=True)
    qty = fields.Float(string='Miqdor', required=True, default=1.0)
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string='O\'lchov', readonly=True)
