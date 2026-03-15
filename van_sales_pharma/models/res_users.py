from odoo import models, fields, api
class ResUsers(models.Model):
    _inherit = 'res.users'

    x_phone = fields.Char(string='Telefon Raqami')
    x_commission_balance = fields.Monetary(string='Komissiya Balansi', currency_field='x_currency_id', default=0.0)
    x_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # === Oylik (Salary/Commission) Fields ===
    komissiya_foizi = fields.Float(string='Komissiya foizi (%)', default=0.0,
                                   help="Sotuvdan agentga qoladigan ulush foizi (masalan 5% bo'lsa 5 yoziladi)")
    oylik_balansi = fields.Monetary(string='Oylik Balansi', compute='_compute_oylik_balansi',
                                    currency_field='x_currency_id',
                                    help="Agentning joriy oylik komissiyalari yig'indisi minus Oylik Chiqimlar")

    ostatka_ids = fields.One2many('van.agent.ostatka', 'agent_id', string='Boshlang\'ich qoldiq (Ostatka)')
    salary_payout_ids = fields.One2many('van.salary.payout', 'agent_id', string='Oylik To\'lovlar Tarixi')
    default_taminotchi_id = fields.Many2one('van.taminotchi', string="Asosiy Taminotchi", help="Yangi Yuklash qilishda avtomatik tanlanuvchi Taminotchi")

    agent_oyligi = fields.Monetary(
        string='Agent Oyligi', 
        compute='_compute_agent_oyligi', 
        currency_field='x_currency_id',
        help="Komissiya ishlab topilgan (Yalpi balansdan)"
    )
    
    # NEW FIELDS FOR COMMISSION FIX:
    yalpi_balans = fields.Monetary(string='Yalpi Balans', compute='_compute_oylik_balansi', currency_field='x_currency_id')
    agent_oyligi_earned = fields.Monetary(string='Agent Oyligi (Ishlab topilgan)', compute='_compute_oylik_balansi', currency_field='x_currency_id')
    oylik_olindi = fields.Monetary(string='Oylik Olindi', compute='_compute_oylik_balansi', currency_field='x_currency_id')
    oylik_qoldigi = fields.Monetary(string='Oylik Qoldig\'i', compute='_compute_oylik_balansi', currency_field='x_currency_id')
    sof_balans = fields.Monetary(string='Sof Balans', compute='_compute_oylik_balansi', currency_field='x_currency_id')

    agent_chiqim_ids = fields.One2many(
        'van.payment', 'agent_id', 
        string="Oylik To'lovlar Tarixi", 
        domain=[('payment_type', '=', 'out'), ('expense_type', '=', 'salary')]
    )

    def _compute_agent_oyligi(self):
        for user in self:
            user.agent_oyligi = user.agent_oyligi_earned

    def _compute_oylik_balansi(self):
        # Initialize all computed fields for all records in the set
        # This prevents "Compute method failed to assign" error during creation
        for user in self:
            user.yalpi_balans = 0.0
            user.agent_oyligi_earned = 0.0
            user.oylik_olindi = 0.0
            user.oylik_qoldigi = 0.0
            user.sof_balans = 0.0
            user.oylik_balansi = 0.0

        # Only process records that exist in the database
        real_users = self.filtered(lambda u: isinstance(u.id, int))
        if not real_users:
            return

        user_ids = real_users.ids

        # --- 1. Batch fetch Naqt Savdo Totals ---
        naqt_rg = self.env['van.pos.order'].read_group(
            domain=[('agent_id', 'in', user_ids), ('state', '=', 'done'), ('partner_id', '=', False)],
            fields=['agent_id', 'amount_total'],
            groupby=['agent_id']
        )
        naqt_dict = {rg['agent_id'][0]: rg['amount_total'] for rg in naqt_rg}

        # --- 2. Batch fetch Payments ---
        pay_rg = self.env['van.payment'].read_group(
            domain=[('agent_id', 'in', user_ids)],
            fields=['agent_id', 'payment_type', 'expense_type', 'amount'],
            groupby=['agent_id', 'payment_type', 'expense_type'],
            lazy=False
        )

        kirim_dict = {}
        chiqim_dict = {}
        salary_paid_dict = {}

        for rg in pay_rg:
            ag_id = rg['agent_id'][0]
            p_type = rg['payment_type']
            e_type = rg.get('expense_type')
            amt = rg['amount']

            if p_type == 'in':
                kirim_dict[ag_id] = kirim_dict.get(ag_id, 0.0) + amt
            elif p_type == 'out':
                chiqim_dict[ag_id] = chiqim_dict.get(ag_id, 0.0) + amt
                if e_type in ('salary', 'payout'):
                    salary_paid_dict[ag_id] = salary_paid_dict.get(ag_id, 0.0) + amt

        for user in real_users:
            uid = user.id
            naqt_savdo_total = naqt_dict.get(uid, 0.0)
            kirim_total = kirim_dict.get(uid, 0.0)
            chiqim_total = chiqim_dict.get(uid, 0.0)
            
            cash = naqt_savdo_total + kirim_total
            total_paid = salary_paid_dict.get(uid, 0.0)
            
            # Daily expenses are total chiqm minus salary payouts
            daily_chiqim = chiqim_total - total_paid
            
            # Gross Balance (Yalpi) = incoming cash minus ONLY operating daily expenses
            user.yalpi_balans = cash - daily_chiqim
            
            # Earned Commission is based entirely on Yalpi Balans
            user.agent_oyligi_earned = user.yalpi_balans * (user.komissiya_foizi / 100.0)
            
            # Salary taken
            user.oylik_olindi = total_paid
            
            # Net Balance (Sof) = Yalpi minus salary taken
            user.sof_balans = user.yalpi_balans - user.oylik_olindi
            
            # Remaining salary to payout
            user.oylik_qoldigi = user.agent_oyligi_earned - user.oylik_olindi
            
            # Keep original alias for backward compatibility but return remaining commission
            user.oylik_balansi = user.oylik_qoldigi

    def action_close_salary(self):
        """
        Opens a wizard to pay out the entire remaining oylik_balansi to the agent.
        """
        self.ensure_one()
        return {
            'name': 'Oylik Yopish (To\'lov)',
            'type': 'ir.actions.act_window',
            'res_model': 'van.salary.payout.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_agent_id': self.id,
                'default_amount': self.oylik_balansi,
                'default_notes': f"Oylik qoldig'ini yopish. Komissiya foizi: {self.komissiya_foizi}%"
            }
        }

    @api.model
    def _get_login_action(self, *args, **kwargs):
        res = super()._get_login_action(*args, **kwargs)
        if self.env.user.has_group('van_sales_pharma.group_van_agent') and not self.env.user.has_group('van_sales_pharma.group_van_admin') and not self.env.user.has_group('base.group_system'):
            pos_action = self.env.ref('van_sales_pharma.action_van_mobile_pos_app', raise_if_not_found=False)
            if pos_action:
                return pos_action.read()[0]
        return res
