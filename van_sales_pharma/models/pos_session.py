from odoo import models, api

class PosSession(models.Model):
    _inherit = 'pos.session'

    def try_cash_in_out(self, _type, amount, reason, partner_id, extras):
        # Odoo's core logic will create an account.bank.statement.line
        res = super(PosSession, self).try_cash_in_out(_type, amount, reason, partner_id, extras)

        # Custom Logic: Track both Cash In and Cash Out into the Agent's van.payment.
        if _type in ['in', 'out']:
            agent = self.env.user
            # Try to find the active trip for this agent
            active_trip = self.env['van.trip'].search([
                ('agent_id', '=', agent.id), 
                ('state', 'in', ['loaded', 'in_progress'])
            ], limit=1)

            # Create a van.payment record so it shows up in Kirimlar / Chiqimlar
            self.env['van.payment'].create({
                'agent_id': agent.id,
                'trip_id': active_trip.id if active_trip else False,
                'partner_id': partner_id if _type == 'in' else False,
                'payment_type': _type,
                'payment_method': 'cash',
                'amount': float(amount),
                'note': f"POS {'Kirim' if _type == 'in' else 'Chiqim'}: {reason}",
            })

            # Since the user wants this to reflect on the customer's balance,
            # this van.payment will act as statistical tracking for Agent.
            # Real debt reduction happens when this cash is reconciled in Accounting.
            # Optionally, we might want to automatically create a payment against the oldest invoice here?
            # Or just tracking it as 'van.payment' for the Dashboard's "Naqt" totals is enough for today.
        
        return res
