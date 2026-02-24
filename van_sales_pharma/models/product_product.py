from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override to filter POS products by agent van inventory.
        Each agent should only see the products they have loaded onto their van
        with remaining quantity > 0.

        Fallback rules:
        - No active trip found for agent → show all POS products (normal mode)
        - Active trip exists but inventory empty/all sold → show NOTHING (an agent
          cannot sell products they haven't loaded or have already sold out)
        """
        # Get base domain from parent (includes available_in_pos, sale_ok, company checks)
        base_domain = super()._load_pos_data_domain(data, config)

        # IMPORTANT: self.env.user during POS data loading runs in the server context (OdooBot),
        # NOT as the actual POS cashier. We must get the real cashier from the current session.
        cashier = False
        session = config.current_session_id
        if session:
            cashier = session.user_id

        # Fallback to env.user if no session found
        if not cashier:
            cashier = self.env.user

        if not cashier or cashier.id == 1:
            # Can't identify real cashier — show all products (admin/setup context)
            return base_domain

        # Find the agent's active trip (loaded or in_progress)
        active_trip = self.env['van.trip'].search([
            ('agent_id', '=', cashier.id),
            ('state', 'in', ['loaded', 'in_progress'])
        ], limit=1)

        if not active_trip:
            # No active trip — this is a normal (non-van) POS session, show all products
            return base_domain

        # Agent has an active trip — from here, ALWAYS restrict to van inventory only.
        # Find the agent summary (permanent profile) for this agent
        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', cashier.id),
        ], limit=1)

        if not summary:
            # No summary profile yet — show nothing (agent must be set up properly)
            return base_domain + [('id', 'in', [])]

        # Get product.template IDs that have remaining_qty > 0 in the van
        van_product_tmpl_ids = summary.inventory_line_ids.filtered(
            lambda l: l.remaining_qty > 0
        ).mapped('product_id.product_tmpl_id').ids

        # Always restrict to van inventory — even if empty (show nothing rather than everything)
        return base_domain + [('id', 'in', van_product_tmpl_ids)]
