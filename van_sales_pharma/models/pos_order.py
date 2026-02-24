from odoo import models, fields, api


class PosOrder(models.Model):
    _inherit = 'pos.order'

    x_trip_id = fields.Many2one('van.trip', string='Sayohat (Trip)', compute='_compute_trip_id', store=True)
    x_agent_summary_id = fields.Many2one('van.agent.summary', string='Agent Hisobot',
                                          compute='_compute_trip_id', store=True)

    @api.depends('session_id.config_id', 'date_order', 'user_id')
    def _compute_trip_id(self):
        for order in self:
            order_date = order.date_order.date() if order.date_order else False
            if not order_date:
                order.x_trip_id = False
                order.x_agent_summary_id = False
                continue

            trip = self.env['van.trip'].search([
                ('agent_id', '=', order.user_id.id),
                ('date', '=', order_date),
                ('state', 'in', ['loaded', 'in_progress'])
            ], limit=1)
            order.x_trip_id = trip.id if trip else False

            # Agent hisobotini ham topamiz
            summary = self.env['van.agent.summary'].search([
                ('agent_id', '=', order.user_id.id),
            ], limit=1)
            order.x_agent_summary_id = summary.id if summary else False

    @api.model
    def _process_saved_order(self, draft):
        order_id = super(PosOrder, self)._process_saved_order(draft)
        order = self.browse(order_id)
        
        # Custom Logic: Track Nasiya automatically into our van.nasiya system
        for payment in order.payment_ids:
            # If the payment method is Nasiya (split_transactions = True)
            if payment.payment_method_id.split_transactions and order.partner_id:
                # We create a van.nasiya record to track the debt exactly
                self.env['van.nasiya'].create({
                    'partner_id': order.partner_id.id,
                    'agent_id': order.user_id.id,
                    'amount_total': payment.amount,
                    'date': order.date_order.date(),
                    # Since POS already creates account moves independently, we track it simply natively here.
                    # Or attach the pos order's move if it generated an invoice natively.
                    'invoice_id': order.account_move.id if order.account_move else False,
                })
        
        return order_id

    def unlink(self):
        for order in self:
            # Custom nasiya cleanup
            if order.account_move:
                nasiya_records = self.env['van.nasiya'].search([('invoice_id', '=', order.account_move.id)])
                nasiya_records.unlink()

            # Attempt to cancel pickings gracefully, or force if needed
            if order.picking_ids:
                for picking in order.picking_ids:
                    if picking.state == 'done':
                        # Forcefully revert state to draft via SQL to avoid UserError
                        self.env.cr.execute("UPDATE stock_picking SET state='draft' WHERE id=%s", (picking.id,))
                        for move in picking.move_ids:
                            self.env.cr.execute("UPDATE stock_move SET state='draft' WHERE id=%s", (move.id,))
                            for move_line in move.move_line_ids:
                                self.env.cr.execute("UPDATE stock_move_line SET state='draft' WHERE id=%s", (move_line.id,))
                        
                        # Invalidate cache so ORM sees the draft state
                        picking.invalidate_recordset(['state'])
                        picking.move_ids.invalidate_recordset(['state'])
                        picking.move_ids.move_line_ids.invalidate_recordset(['state'])
                    
                    picking.sudo().action_cancel()
                    picking.sudo().unlink()

            # Reverse or cancel account moves
            if order.account_move:
                order.account_move.button_draft()
                order.account_move.button_cancel()
                order.account_move.with_context(force_delete=True).sudo().unlink()

            # Unlink payments
            order.payment_ids.sudo().unlink()

            # Detach from session and other relational fields safely before deletion
            # This prevents UI/Session errors that try to read the order after it's gone.
            # We use raw SQL for this to completely bypass Odoo's protection in the `write` method
            # which throws "Invalid Operation" if you try to modify a paid order.
            self.env.cr.execute(
                "UPDATE pos_order SET state='draft', session_id=NULL, account_move=NULL WHERE id=%s", 
                (order.id,)
            )
            order.invalidate_recordset(['state', 'session_id', 'account_move'])

            # Forcefully remove lines so they don't block deletion
            if order.lines:
                order.lines.sudo().unlink()

        return super(PosOrder, self).unlink()
