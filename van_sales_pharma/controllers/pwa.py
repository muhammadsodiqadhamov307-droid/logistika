# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class VanSalesPWA(http.Controller):
    def _web_action_url(self, xmlid):
        action = request.env.ref(xmlid, raise_if_not_found=False)
        if action:
            return f'/web#action={action.id}'
        return '/web'


    @http.route('/van/app', type='http', auth='public')
    def van_app_entry(self, **kw):
        # Redirect unauthenticated users to login, with return URL set back to /van/app
        if not request.session.uid:
            return request.redirect('/web/login?redirect=/van/app')
            
        user = request.env.user
        is_admin = user.has_group('van_sales_pharma.group_van_admin') or user.has_group('base.group_system')
        is_agent = user.has_group('van_sales_pharma.group_van_agent')
        
        # Agents go strictly to Mobile POS
        if is_agent and not is_admin:
            return request.redirect(self._web_action_url('van_sales_pharma.action_van_mobile_pos_app'))
            
        # Admins or others go to the Van Sales Dashboard
        return request.redirect(self._web_action_url('van_sales_pharma.action_van_sales_dashboard'))
