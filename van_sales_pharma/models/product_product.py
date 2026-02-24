from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override to filter POS products by agent van inventory.
        Each agent should only see the products they have loaded onto their van.
        If the current user has no active trip or no inventory, fall back to default products.
        """
        # Get base domain from parent
        base_domain = super()._load_pos_data_domain(data, config)

        current_user = self.env.user

        # Find the agent's active trip (loaded or in_progress)
        active_trip = self.env['van.trip'].search([
            ('agent_id', '=', current_user.id),
            ('state', 'in', ['loaded', 'in_progress'])
        ], limit=1)

        if not active_trip:
            # No active trip — fallback to default POS product list
            return base_domain

        # Find the agent summary (permanent profile) for this agent
        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', current_user.id),
        ], limit=1)

        if not summary:
            return base_domain

        # Get product IDs that have remaining qty > 0 in the van
        van_product_ids = summary.inventory_line_ids.filtered(
            lambda l: l.remaining_qty > 0
        ).mapped('product_id').ids

        if not van_product_ids:
            return base_domain

        # Restrict the product.product domain to only van inventory IDs
        return base_domain + [('id', 'in', van_product_ids)]
