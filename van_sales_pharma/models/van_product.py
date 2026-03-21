from odoo import models, fields, api
from datetime import datetime, time
import pytz

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

    sale_report_date_from = fields.Date(string='Sotuv Sana Dan')
    sale_report_date_to = fields.Date(string='Sotuv Sana Gacha')
    sale_report_agent_id = fields.Many2one('res.users', string='Sotuv Agenti')
    sale_report_partner_id = fields.Many2one('res.partner', string='Mijoz', domain=[('x_is_van_customer', '=', True)])
    sale_report_line_ids = fields.Many2many(
        'van.pos.order.line',
        compute='_compute_report_lines',
        string='Mahsulot Sotuv Hisoboti',
    )

    trip_report_date_from = fields.Date(string='Yuklash Sana Dan')
    trip_report_date_to = fields.Date(string='Yuklash Sana Gacha')
    trip_report_agent_id = fields.Many2one('res.users', string='Yuklash Agenti')
    trip_report_taminotchi_id = fields.Many2one('van.taminotchi', string='Taminotchi')
    trip_report_line_ids = fields.Many2many(
        'van.trip.line',
        compute='_compute_report_lines',
        string='Mahsulot Yuklash Hisoboti',
    )

    @api.depends(
        'sale_report_date_from', 'sale_report_date_to', 'sale_report_agent_id', 'sale_report_partner_id',
        'trip_report_date_from', 'trip_report_date_to', 'trip_report_agent_id', 'trip_report_taminotchi_id'
    )
    def _compute_report_lines(self):
        user_tz = pytz.timezone(self.env.user.tz or self.env.context.get('tz') or 'UTC')
        for rec in self:
            sale_domain = [('product_id', '=', rec.id), ('order_id.state', '=', 'done')]
            if rec.sale_report_agent_id:
                sale_domain.append(('sale_agent_id', '=', rec.sale_report_agent_id.id))
            if rec.sale_report_partner_id:
                sale_domain.append(('sale_partner_id', '=', rec.sale_report_partner_id.id))
            if rec.sale_report_date_from:
                utc_start = user_tz.localize(datetime.combine(rec.sale_report_date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
                sale_domain.append(('sale_date', '>=', utc_start))
            if rec.sale_report_date_to:
                utc_end = user_tz.localize(datetime.combine(rec.sale_report_date_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
                sale_domain.append(('sale_date', '<=', utc_end))

            trip_domain = [('product_id', '=', rec.id), ('trip_id.state', '=', 'done')]
            if rec.trip_report_agent_id:
                trip_domain.append(('trip_agent_id', '=', rec.trip_report_agent_id.id))
            if rec.trip_report_taminotchi_id:
                trip_domain.append(('trip_taminotchi_id', '=', rec.trip_report_taminotchi_id.id))
            if rec.trip_report_date_from:
                utc_start = user_tz.localize(datetime.combine(rec.trip_report_date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
                trip_domain.append(('trip_date', '>=', utc_start))
            if rec.trip_report_date_to:
                utc_end = user_tz.localize(datetime.combine(rec.trip_report_date_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
                trip_domain.append(('trip_date', '<=', utc_end))

            rec.sale_report_line_ids = self.env['van.pos.order.line'].search(sale_domain, order='sale_date desc, id desc')
            rec.trip_report_line_ids = self.env['van.trip.line'].search(trip_domain, order='trip_date desc, id desc')

    def action_clear_sale_report_filters(self):
        for rec in self:
            rec.sale_report_date_from = False
            rec.sale_report_date_to = False
            rec.sale_report_agent_id = False
            rec.sale_report_partner_id = False
        return True

    def action_clear_trip_report_filters(self):
        for rec in self:
            rec.trip_report_date_from = False
            rec.trip_report_date_to = False
            rec.trip_report_agent_id = False
            rec.trip_report_taminotchi_id = False
        return True
