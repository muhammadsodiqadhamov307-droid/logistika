# -*- coding: utf-8 -*-
from odoo import models, fields, api

class VanOstatkaQarzi(models.Model):
    _name = 'van.ostatka.qarzi'
    _description = 'Mijoz Ostatka Qarzi (Opening Balance)'
    _order = 'date desc'

    date = fields.Date(string='Sana', default=fields.Date.context_today, required=True)
    amount = fields.Monetary(string='Summa', currency_field='currency_id', required=True)
    note = fields.Char(string='Izoh')
    
    partner_id = fields.Many2one('res.partner', string='Mijoz', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Korxona', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

