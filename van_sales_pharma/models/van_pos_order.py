import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class VanPosOrder(models.Model):
    _name = 'van.pos.order'
    _description = 'Van Sales Mobile POS Order'
    _order = 'date desc, id desc'

    name = fields.Char(string='Buyurtma Raqami', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', string='Kompaniya', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)

    agent_id = fields.Many2one('res.users', string='Agent', required=True, default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='Mijoz')
    date = fields.Datetime(string='Sana', required=True, default=fields.Datetime.now)
    
    amount_total = fields.Monetary(string='Jami Summa', compute='_compute_amount_total', store=True, currency_field='currency_id')
    
    state = fields.Selection([
        ('draft', 'Qoralama'),
        ('done', 'Bajarilgan'),
        ('cancel', 'Bekor Qilingan')
    ], string='Holat', default='draft', required=True, tracking=True)

    line_ids = fields.One2many('van.pos.order.line', 'order_id', string='Buyurtma Qatorlari')
    
    nasiya_id = fields.Many2one('van.nasiya', string='Yaratilgan Nasiya', readonly=True, ondelete='set null')
    
    note = fields.Text(string='Eslatmalar')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('van.pos.order') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.subtotal')
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(line.subtotal for line in order.line_ids)

    def action_confirm_order(self):
        """
        Validates the order, deducts from agent inventory, and creates a Nasiya record.
        """
        for order in self:
            if order.state != 'draft':
                raise UserError(_("Faqat qoralama buyurtmalarni tasdiqlash mumkin."))
            if not order.line_ids:
                raise UserError(_("Bo'sh buyurtmani tasdiqlash mumkin emas."))

            # 1. Deduct from Agent Inventory
            summary = self.env['van.agent.summary'].search([('agent_id', '=', order.agent_id.id)], limit=1)
            if not summary:
                raise UserError(_("%s agenti uchun faol ombor hisoboti topilmadi") % order.agent_id.name)

            for line in order.line_ids:
                inv_line = self.env['van.agent.inventory.line'].search([
                    ('summary_id', '=', summary.id),
                    ('product_id', '=', line.product_id.id)
                ], limit=1)
                
                if not inv_line:
                    raise UserError(_("'%s' mahsuloti agent omborida yo'q.") % line.product_id.display_name)
                
                # Check remaining stock (loaded - sold + returned)
                # Since 'sold_qty' in van_agent_summary is dynamically computed based on pos.order/van.pos.order, 
                # we just need to ensure the new total sold doesn't exceed loaded.
                # Actually, in this custom model approach, we should define how inventory tracks van.pos.order sales.
                # We will update `_compute_remaining` in van.agent.summary later to include `van.pos.order.line`.
                rem_qty = inv_line.loaded_qty - inv_line.sold_qty + inv_line.returned_qty
                if rem_qty < line.qty:
                   raise UserError(_("'%s' uchun yetarli zaxira yo'q. Qoldiq: %s, So'ralgan: %s") % 
                                   (line.product_id.display_name, rem_qty, line.qty))

            # 2. Create Nasiya Record
            nasiya_vals = {
                'partner_id': order.partner_id.id,
                'agent_id': order.agent_id.id,
                'amount_total': order.amount_total,
                'date': order.date.date(),
                # We don't link an invoice_id here as per requirements.
                # We will add a 'van_pos_order_id' reference if needed, or just keep it loose.
            }
            nasiya = self.env['van.nasiya'].create(nasiya_vals)
            order.nasiya_id = nasiya.id
            
            order.state = 'done'

            # 3. Telegram Notification
            if order.partner_id and order.partner_id.telegram_chat_id:
                # Recalculate debt 
                order.partner_id._compute_van_nasiya_stats()
                
                import pytz
                user_tz = pytz.timezone(self.env.user.tz or 'Asia/Tashkent')
                local_dt = pytz.utc.localize(order.date).astimezone(user_tz)
                date_str = local_dt.strftime('%Y-%m-%d %H:%M')
                
                msg = f"🧾 <b>Savdo cheki</b>\n"
                msg += f"📅 {date_str}\n"
                msg += f"👤 Agent: {order.agent_id.name}\n\n"
                msg += f"📦 Mahsulotlar:\n"
                for line in order.line_ids:
                    msg += f"- {line.product_id.name} x{int(line.qty)} — {line.subtotal:,.0f} so'm\n"
                msg += f"\n💵 Jami: {order.amount_total:,.0f} so'm\n"
                msg += f"💳 Qarz: {order.partner_id.x_van_total_due:,.0f} so'm"
                
                self.env['van.telegram.utils'].send_message(order.partner_id.telegram_chat_id, msg)

        return True

class VanPosOrderLine(models.Model):
    _name = 'van.pos.order.line'
    _description = 'Van Sales Mobile POS Order Line'

    order_id = fields.Many2one('van.pos.order', string='Buyurtma', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='order_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id', store=True)

    product_id = fields.Many2one('van.product', string='Mahsulot', required=True)
    qty = fields.Float(string='Miqdor', required=True, default=1.0)
    price_unit = fields.Float(string='Narx', required=True)
    
    subtotal = fields.Monetary(string='Oraliq Summa', compute='_compute_subtotal', store=True, currency_field='currency_id')
    
    # Cost and Margin
    cost_price = fields.Float(string='Kelish Narxi', related='product_id.cost_price', readonly=True, store=True)
    margin = fields.Monetary(string='Sof Foyda', compute='_compute_margin', store=True, currency_field='currency_id')

    @api.depends('qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.price_unit

    @api.depends('qty', 'price_unit', 'cost_price')
    def _compute_margin(self):
        for line in self:
            line.margin = (line.price_unit - line.cost_price) * line.qty
