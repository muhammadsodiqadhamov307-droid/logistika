import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class VanPayment(models.Model):
    _name = 'van.payment'
    _description = 'Agent To\'lovi'
    _order = 'date desc, id desc'

    name = fields.Char(string='To\'lov Raqami', required=True, copy=False, readonly=True, default=lambda self: _('Yangi'))
    company_id = fields.Many2one('res.company', string='Korxona', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    trip_id = fields.Many2one('van.trip', string='Sayohat')
    partner_id = fields.Many2one('res.partner', string='Kirim Qilgan Mijoz', help="POSdan qilingan mijoz qarzi to'lovi")
    agent_id = fields.Many2one('res.users', string='Agent', required=True, default=lambda self: self.env.user)
    sale_order_id = fields.Many2one('van.sale.order', string='Sotuv', ondelete='cascade')

    payment_type = fields.Selection([
        ('in', 'Kirim (+)') ,
        ('out', 'Chiqim (-)')
    ], string='Turi', default='in', required=True)

    payment_method = fields.Selection([
        ('cash', 'Naqt'),
        ('card', 'Karta / Bank')
    ], string='To\'lov Usuli', required=True)
    
    amount = fields.Monetary(string='Mablag\'', required=True, currency_field='currency_id')
    date = fields.Datetime(string='Sana', default=fields.Datetime.now, required=True)
    
    state = fields.Selection([
        ('received', 'Qabul Qilingan'),
        ('confirmed', 'Tasdiqlangan (Buxgalteriya)')
    ], string='Holat', default='received', required=True, tracking=True)
    
    note = fields.Text(string='Izoh')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Yangi')) == _('Yangi'):
                vals['name'] = self.env['ir.sequence'].next_by_code('van.payment') or _('Yangi')
        return super().create(vals_list)
