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

        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', cashier.id),
        ], limit=1)

        if not summary and (not cashier or cashier._is_admin()):
            return base_domain

        if not summary:
            return base_domain + [('id', 'in', [])]

        van_product_tmpl_ids = summary.inventory_line_ids.filtered(
            lambda l: l.remaining_qty > 0
        ).mapped('product_id.product_tmpl_id').ids

        if not van_product_tmpl_ids:
            return [('id', 'in', [])]

        return [
            ('sale_ok', '=', True),
            ('company_id', 'in', [self.env.company.id, False]),
            ('id', 'in', van_product_tmpl_ids)
        ]

    def get_product_info_pos(self, price, quantity, pos_config_id, product_variant_id=False):
        """
        Override to show the agent's van inventory (Qoldiq) instead of global
        warehouse stock when they hold-press a product in POS.
        JS calls this on product.template, so this is the correct location.
        """
        res = super().get_product_info_pos(price, quantity, pos_config_id, product_variant_id)

        config = self.env['pos.config'].browse(pos_config_id)
        session = config.current_session_id
        cashier = session.user_id if session else self.env.user

        if not cashier:
            return res

        # Find Van Agent Summary for this cashier
        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', cashier.id),
        ], limit=1)

        if not summary:
            return res

        # Match inventory lines by any variant of THIS template (self = product.template)
        inv_lines = summary.inventory_line_ids.filtered(
            lambda l: l.product_id.product_tmpl_id.id == self.id and l.remaining_qty > 0
        )

        remaining = sum(inv_lines.mapped('remaining_qty'))

        # Replace the company warehouse list with the Agent's Truck Inventory
        res['warehouses'] = [{
            'id': 99999,
            'name': f"{cashier.name} - Mashina Ombori",
            'available_quantity': remaining,
            'free_qty': remaining,
            'forecasted_quantity': remaining,
            'uom': self.uom_name,
        }]

        return res


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Forcefully apply the same logic to the variant level to satisfy Odoo 19 mapping.
        """
        base_domain = super()._load_pos_data_domain(data, config)

        cashier = False
        session = config.current_session_id
        if session:
            cashier = session.user_id

        if not cashier:
            cashier = self.env.user

        summary = self.env['van.agent.summary'].search([
            ('agent_id', '=', cashier.id),
        ], limit=1)

        if not summary and (not cashier or cashier._is_admin()):
            return base_domain

        if not summary:
            return base_domain + [('id', 'in', [])]

        van_product_ids = summary.inventory_line_ids.filtered(
            lambda l: l.remaining_qty > 0
        ).mapped('product_id').ids

        if not van_product_ids:
            return [('id', 'in', [])]

        return [
            ('sale_ok', '=', True),
            ('company_id', 'in', [self.env.company.id, False]),
            ('id', 'in', van_product_ids)
        ]


