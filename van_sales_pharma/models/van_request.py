from odoo import models, fields, api, _

class VanRequest(models.Model):
    _name = 'van.request'
    _description = "Mijoz So'rovi"
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    agent_id = fields.Many2one('res.users', string='Agent', default=lambda self: self.env.user, required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Mijoz', required=True)
    product_id = fields.Many2one('van.product', string='Mahsulot', required=True)
    qty = fields.Float(string='Soni', required=True, default=1.0)
    state = fields.Selection([
        ('draft', 'Yangi'),
        ('done', 'Bajarildi'),
        ('cancel', 'Bekor qilindi'),
    ], string='Holati', readonly=True, default='draft')
    date = fields.Datetime(string='Sana', default=fields.Datetime.now, required=True)
    notes = fields.Text(string='Izoh')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('van.request') or _('New')
        return super(VanRequest, self).create(vals_list)

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})
