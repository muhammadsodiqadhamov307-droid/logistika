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

    @api.model_create_multi
    def create(self, vals_list):
        records = super(VanOstatkaQarzi, self).create(vals_list)
        for record in records:
            if record.partner_id.telegram_chat_id:
                record.partner_id._compute_van_nasiya_stats() # Recalculate balance to show the latest
                msg = f"📝 <b>Ostatka qarzi (Eski qarz) kiritildi!</b>\n\n"
                msg += f"📅 Sana: {record.date.strftime('%Y-%m-%d')}\n"
                msg += f"💵 Summa: {record.amount:,.0f} so'm\n"
                if record.note:
                    msg += f"ℹ️ Izoh: {record.note}\n"
                msg += f"\n💳 Umumiy Qarz: {record.partner_id.x_van_total_due:,.0f} so'm"
                
                # Fetch button for WebApp
                base_url = self.env['ir.config_parameter'].sudo().get_param('van_telegram_odoo_url', self.env['ir.config_parameter'].sudo().get_param('web.base.url', ''))
                if not base_url.startswith('http'):
                    base_url = "https://" + base_url.lstrip('/')
                elif base_url.startswith('http://') and not ('localhost' in base_url or '127.0.0.1' in base_url):
                    base_url = base_url.replace('http://', 'https://')
                    
                base_url = base_url.rstrip('/')
                web_app_url = f"{base_url}/van/client/request?chat_id={record.partner_id.telegram_chat_id}"
                
                button = {"text": "🛒 Zakaz berish", "web_app": {"url": web_app_url}}
                reply_markup = {"inline_keyboard": [[button]]}
                
                self.env['van.telegram.utils'].sudo().send_message(
                    record.partner_id.telegram_chat_id, 
                    msg, 
                    reply_markup=reply_markup
                )
        return records

