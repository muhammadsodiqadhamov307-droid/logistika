import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class VanTripCloseWizard(models.TransientModel):
    _name = 'van.trip.close.wizard'
    _description = 'Mashina Sayohatini Yopish Wizardi'

    trip_id = fields.Many2one('van.trip', string='Sayohat', required=True, readonly=True)
    company_id = fields.Many2one('res.company', related='trip_id.company_id')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    close_line_ids = fields.One2many('van.trip.close.line', 'wizard_id', string='Qaytariladigan Mahsulotlar')

    cash_expected = fields.Monetary(string='Kutilgan Naqt', related='trip_id.x_cash_expected', currency_field='currency_id')
    card_expected = fields.Monetary(string='Kutilgan Karta', related='trip_id.x_card_expected', currency_field='currency_id')

    cash_received = fields.Monetary(string='Topshirilgan Naqt', required=True, currency_field='currency_id')
    card_received = fields.Monetary(string='Topshirilgan Karta', required=True, currency_field='currency_id')
    
    note = fields.Text(string='Yopilish Izohi')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'trip_id' in res:
            trip = self.env['van.trip'].browse(res['trip_id'])
            lines = []
            for line in trip.trip_line_ids:
                if line.remaining_qty > 0:
                    lines.append((0, 0, {
                        'trip_line_id': line.id,
                        'product_id': line.product_id.id,
                        'expected_return': line.remaining_qty,
                        'actual_return': line.remaining_qty, 
                    }))
            res['close_line_ids'] = lines
        return res

    def action_close_trip(self):
        self.ensure_one()

        if self.cash_received < 0 or self.card_received < 0:
            raise UserError(_("Topshirilayotgan summa manfiy bo'lishi mumkin emas!"))

        # Step 1: Mahsulot Qoldiqlarini Qabul Qilish (Warehouse Return)
        return_moves = []
        for line in self.close_line_ids:
            if line.actual_return < 0:
                raise UserError(_("Qaytarilayotgan summa manfiy emas: %s") % line.product_id.display_name)
            
            # Haqiqatan qaytganini yozib qo'yamiz  
            line.trip_line_id.returned_qty = line.actual_return
            
            if line.actual_return > 0:
                return_moves.append(line)

        # Tranzitdan asosiy omborga qaytish ishlari
        if return_moves:
            warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
            main_location = warehouse.lot_stock_id
            van_location = self.trip_id.location_id
            
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'), 
                ('company_id', '=', self.company_id.id),
                '|', ('active', '=', True), ('active', '=', False)
            ], order='sequence, id', limit=1)
            
            if picking_type and not picking_type.active:
                picking_type.active = True
                
            if not picking_type:
                picking_type = self.env['stock.picking.type'].create({
                    'name': 'Ichki Ko\'chirish (Avto)',
                    'sequence_code': 'INT',
                    'code': 'internal',
                    'company_id': self.company_id.id,
                    'warehouse_id': warehouse.id,
                    'show_operations': True,
                })

            if main_location and van_location and picking_type:
                picking_vals = {
                    'picking_type_id': picking_type.id,
                    'location_id': van_location.id,
                    'location_dest_id': main_location.id,
                    'origin': _('Qaytaruv/Yopilish: %s', self.trip_id.name),
                    'company_id': self.company_id.id,
                }
                
                try:
                    with self.env.cr.savepoint():
                        picking = self.env['stock.picking'].create(picking_vals)
                        for r_line in return_moves:
                            move_vals = {
                                'product_id': r_line.product_id.id,
                                'product_uom_qty': r_line.actual_return,
                                'picking_id': picking.id,
                                'location_id': van_location.id,
                                'location_dest_id': main_location.id,
                                'company_id': self.company_id.id,
                            }
                            
                            if 'name' in self.env['stock.move']._fields:
                                move_vals['name'] = r_line.product_id.name
                            if 'description_picking' in self.env['stock.move']._fields:
                                move_vals['description_picking'] = r_line.product_id.name
                                
                            self.env['stock.move'].create(move_vals)
                        picking.action_confirm()
                        picking.button_validate()
                        _logger.info("Yopilish Ombor yozuvi tasdiqlandi: %s", picking.name)
                except Exception as e:
                    _logger.error("Dori Qoldiqlarini bazaga qaytarishda xatolik: %s", str(e))
                    raise UserError(_("Ombor moduliga ulanishda xato: Mashinadan tovar qaytmadi!\n(%s)") % str(e))

        # Agent doimiy profilidan qaytarilganlarni ayirib tashlash
        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', self.trip_id.agent_id.id),
        ], limit=1)
        if summary:
            for r_line in return_moves:
                if r_line.actual_return > 0:
                    inv_line = self.env['van.agent.inventory.line'].search([
                        ('summary_id', '=', summary.id),
                        ('product_id', '=', r_line.product_id.id)
                    ], limit=1)
                    if inv_line:
                        inv_line.loaded_qty -= r_line.actual_return

        # Step 2: Pul Yozuvlarini Kiritish
        self.trip_id.x_cash_received = self.cash_received
        self.trip_id.x_card_received = self.card_received
        
        # Muloqot Izohini Qo'shish
        full_note = self.trip_id.note or ''
        if self.note:
            full_note += f"\nYopilish Izohi: {self.note}"
        self.trip_id.note = full_note

        # Step 3: Holatni Yopilgan ga o'zgartirish
        self.trip_id.state = 'closed'

        # Return to the trip form to refresh the state and close popup
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'van.trip',
            'res_id': self.trip_id.id,
            'view_mode': 'form',
            'target': 'main',
        }

class VanTripCloseLine(models.TransientModel):
    _name = 'van.trip.close.line'
    _description = 'Mashinadan Qaytarilgan Mahsulotlar'

    wizard_id = fields.Many2one('van.trip.close.wizard', required=True, ondelete='cascade')
    trip_line_id = fields.Many2one('van.trip.line', required=True)
    product_id = fields.Many2one('product.product', string='Mahsulot', readonly=True)
    
    expected_return = fields.Float(string='Kutilgan Qoldiq', readonly=True)
    actual_return = fields.Float(string='Haqiqiy Qaytarilayotgani', required=True)
    
    @api.onchange('expected_return')
    def _onchange_actual_return_default(self):
        if not self.actual_return:
            self.actual_return = self.expected_return
