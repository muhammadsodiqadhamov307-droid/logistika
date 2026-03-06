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

    partner_id = fields.Many2one('res.partner', string='Kirim Qilgan Mijoz', help="POSdan qilingan mijoz qarzi to'lovi")
    agent_id = fields.Many2one('res.users', string='Agent', required=True, default=lambda self: self.env.user)
    sale_order_id = fields.Many2one('van.sale.order', string='Sotuv', ondelete='cascade')
    nasiya_id = fields.Many2one('van.nasiya', string='Nasiya', ondelete='cascade')
    taminotchi_id = fields.Many2one('van.taminotchi', string="Taminotchi (Yetkazib beruvchi)", ondelete='cascade')
    taminotchi_balance_dummy = fields.Monetary(
        string="Hisobidagi Qoldiq", 
        related='taminotchi_id.balance', 
        currency_field='currency_id', 
        readonly=True,
        help="Tanlangan Taminotchiga qancha qarzimiz borligini ko'rsatadi"
    )

    payment_type = fields.Selection([
        ('in', 'Kirim (+)') ,
        ('out', 'Chiqim (-)')
    ], string='Turi', default='in', required=True)

    expense_type = fields.Selection([
        ('daily', '🟡 Kunlik Chiqim'),
        ('salary', '🟣 Oylik Chiqim'),
        ('payout', '🟢 Oylik To\'lovi (Yopish)')
    ], string='Chiqim Turi', default='daily', help="Chiqim bo'lganda bu agentning oyligidan chegiriladimi yoki yo'q")

    payment_method = fields.Selection([
        ('cash', 'Naqt'),
        ('card', 'Karta / Bank')
    ], string='To\'lov Usuli', required=True, default='cash')
    
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
        records = super().create(vals_list)
        
        # 3. Telegram Notification for Inbound Payments
        for rec in records:
            if rec.payment_type == 'in' and rec.partner_id and rec.partner_id.telegram_chat_id:
                # Recalculate debt dynamically
                rec.partner_id._compute_van_nasiya_stats()
                
                import pytz
                user_tz = pytz.timezone(self.env.user.tz or 'Asia/Tashkent')
                local_dt = pytz.utc.localize(rec.date).astimezone(user_tz)
                date_str = local_dt.strftime('%Y-%m-%d %H:%M')
                
                msg = f"✅ <b>To'lov qabul qilindi</b>\n"
                msg += f"📅 {date_str}\n"
                msg += f"💵 Miqdor: {rec.amount:,.0f} so'm\n"
                msg += f"💳 Qolgan qarz: {rec.partner_id.x_van_total_due:,.0f} so'm"
                
                # Attach Web App Button for Zakaz Berish
                base_url = self.env['ir.config_parameter'].sudo().get_param('van_telegram_odoo_url', self.env['ir.config_parameter'].sudo().get_param('web.base.url', ''))
                if not base_url.startswith('http'):
                    base_url = "https://" + base_url.lstrip('/')
                elif base_url.startswith('http://') and not ('localhost' in base_url or '127.0.0.1' in base_url):
                    base_url = base_url.replace('http://', 'https://')
                base_url = base_url.rstrip('/')
                
                web_app_url = f"{base_url}/van/client/request?chat_id={rec.partner_id.telegram_chat_id}"
                button = {"text": "🛒 Zakaz berish", "web_app": {"url": web_app_url}}
                reply_markup = {"inline_keyboard": [[button]]}
                
                self.env['van.telegram.utils'].send_message(rec.partner_id.telegram_chat_id, msg, reply_markup=reply_markup)
        return records
