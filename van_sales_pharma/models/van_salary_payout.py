# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class VanSalaryPayout(models.Model):
    _name = 'van.salary.payout'
    _description = 'Agent Oylik To\'lovi'
    _order = 'date desc, id desc'

    agent_id = fields.Many2one('res.users', string='Agent', required=True, ondelete='cascade')
    date = fields.Date(string='Sana', default=fields.Date.context_today, required=True)
    amount = fields.Monetary(string='Summa', required=True, currency_field='currency_id')
    notes = fields.Text(string='Izoh')
    admin_id = fields.Many2one('res.users', string='Kim tomonidan', default=lambda self: self.env.user, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Valyuta', default=lambda self: self.env.company.currency_id)

class VanSalaryPayoutWizard(models.TransientModel):
    _name = 'van.salary.payout.wizard'
    _description = 'Oylik Yopish Wizard'

    agent_id = fields.Many2one('res.users', string='Agent', required=True)
    amount = fields.Monetary(string='To\'lanadigan Summa', currency_field='currency_id', readonly=True)
    notes = fields.Text(string='Izoh', placeholder='Masalan: Mart oyligi to\'lovi...')
    currency_id = fields.Many2one('res.currency', string='Valyuta', related='agent_id.x_currency_id')

    def action_confirm_payout(self):
        self.ensure_one()
        if self.amount <= 0:
            return

        # 1. Create Payout Record
        self.env['van.salary.payout'].create({
            'agent_id': self.agent_id.id,
            'amount': self.amount,
            'notes': self.notes,
            'date': fields.Date.context_today(self),
            'admin_id': self.env.user.id,
        })

        # 2. Reseting balance is handled by the compute field in res.users
        # as it will now subtract these payout records.
        
        return {'type': 'ir.actions.act_window_close'}
