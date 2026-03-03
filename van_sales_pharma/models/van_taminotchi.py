# -*- coding: utf-8 -*-
from odoo import models, fields, api

class VanTaminotchi(models.Model):
    _name = 'van.taminotchi'
    _description = 'Taminotchi (Supplier)'
    
    name = fields.Char(string='Taminotchi Ismi/Kompaniyasi', required=True)
    phone = fields.Char(string='Telefon Raqami')
    address = fields.Text(string='Manzili')
    
    # Financial fields
    balance = fields.Monetary(string="Joriy Balans", compute="_compute_balance", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Valyuta', default=lambda self: self.env.company.currency_id)
    
    # Relations
    trip_ids = fields.One2many('van.trip', 'taminotchi_id', string="Mahsulot Yuklashlar")
    payment_ids = fields.One2many('van.payment', 'taminotchi_id', string="To'lovlar (Chiqim)")

    @api.depends('trip_ids.amount_cost_total', 'payment_ids.amount', 'payment_ids.state')
    def _compute_balance(self):
        for rec in self:
            # Total owed is the sum of loaded goods at their cost price
            total_debt = sum(trip.amount_cost_total for trip in rec.trip_ids if trip.state == 'validated')
            
            # Total paid is the sum of Chiqim payments related to this Taminotchi
            total_paid = sum(pay.amount for pay in rec.payment_ids if pay.state == 'received' and pay.payment_type == 'out')
            
            # Balance represents how much we still owe them
            rec.balance = total_debt - total_paid

    def action_view_ledger(self):
        self.ensure_one()
        return {
            'name': 'Taminotchi Hisoboti',
            'type': 'ir.actions.act_window',
            'res_model': 'van.taminotchi.ledger.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_taminotchi_id': self.id},
        }
