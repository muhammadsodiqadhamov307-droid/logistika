from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override to filter POS products by agent van inventory.
        Each agent should only see the products they have loaded onto their van
        with remaining quantity > 0.
        """
        base_domain = super()._load_pos_data_domain(data, config)

        cashier = False
        session = config.current_session_id
        if session:
            cashier = session.user_id

        if not cashier:
            cashier = self.env.user

        # Remove the 'available_in_pos' restriction natively if we want agent inventory to strictly override
        # We will manually construct the domain enforcing company and active states if they are an agent.

        # Find the agent summary (permanent profile) for this agent
        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', cashier.id),
        ], limit=1)

        # Allow Admins (id 1) to see normal POS items if they aren't explicitly testing an agent summary,
        # but if an Admin HAS an agent summary and inventory, show that inventory to them so they can test.
        if not summary and (not cashier or cashier._is_admin()):
            return base_domain

        if not summary:
            # If a strict Agent is logged in but hasn't been set up yet, they can't sell anything.
            return base_domain + [('id', 'in', [])]

        # Get product.template IDs that have remaining_qty > 0 in the van
        van_product_tmpl_ids = summary.inventory_line_ids.filtered(
            lambda l: l.remaining_qty > 0
        ).mapped('product_id.product_tmpl_id').ids

        if not van_product_tmpl_ids:
            return [('id', 'in', [])]

        # Return a custom domain that entirely ignores 'available_in_pos' but ensures basic access
        # This forcefully allows ANY product in their truck to appear in POS.
        return [
            ('sale_ok', '=', True),
            ('company_id', 'in', [self.env.company.id, False]),
            ('id', 'in', van_product_tmpl_ids)
        ]

    def get_product_info_pos(self, price, quantity, pos_config_id, product_variant_id=False):
        """
        Override to show the agent's van inventory (Qoldiq) instead of global
        warehouse stock when they click the 'info' button in POS.
        """
        res = super().get_product_info_pos(price, quantity, pos_config_id, product_variant_id)

        config = self.env['pos.config'].browse(pos_config_id)
        session = config.current_session_id
        cashier = session.user_id if session else self.env.user

        if not cashier or cashier.id == 1:
            return res

        # Check if this cashier is an agent with an active trip
        active_trip = self.env['van.trip'].search([
            ('agent_id', '=', cashier.id),
            ('state', 'in', ['loaded', 'in_progress'])
        ], limit=1)

        if active_trip:
            summary = self.env['van.agent.summary'].search([
                ('agent_id', '=', cashier.id),
            ], limit=1)

            if summary:
                # Find the inventory line for this product template
                inv_lines = summary.inventory_line_ids.filtered(
                    lambda l: l.product_id.product_tmpl_id.id == self.id
                )
                
                remaining = sum(inv_lines.mapped('remaining_qty'))
                
                # Replace the entire warehouse list with just the Agent's Van Inventory
                # so the info dialog only shows the Qoldiq
                res['warehouses'] = [{
                    'id': 99999, # Fake ID to avoid errors
                    'name': f"{cashier.name} - Mashina Ombori",
                    'available_quantity': remaining,
                    'free_qty': remaining,
                    'forecasted_quantity': remaining,
                    'uom': self.uom_name,
                }]

        return res
