from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    van_telegram_bot_token = fields.Char(
        string='Telegram Bot Token', 
        config_parameter='van.telegram.bot.token',
        help="Paste the HTTP API Token provided by BotFather here."
    )
