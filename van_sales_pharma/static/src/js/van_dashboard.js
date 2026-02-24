/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";

export class VanSalesDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            today_trips_count: 0,
            active_trips_count: 0,
            total_cash: 0,
            total_card: 0,
            total_chiqim: 0,
            total_nasiya: 0,
            recent_sales: [],
            recent_kirims: [],
            detail_view_id: false,
            currency_id: false,
        });

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    async fetchDashboardData() {
        const data = await this.orm.call("van.trip", "get_van_dashboard_data", []);
        this.state.today_trips_count = data.today_trips_count;
        this.state.active_trips_count = data.active_trips_count;
        this.state.total_cash = data.total_cash;
        this.state.total_card = data.total_card;
        this.state.total_chiqim = data.total_chiqim || 0;
        this.state.total_nasiya = data.total_global_nasiya;
        this.state.recent_sales = data.recent_sales;
        this.state.recent_kirims = data.recent_kirims;
        this.state.detail_view_id = data.detail_view_id;
        this.state.currency_id = data.currency_id;
    }

    formatPrice(amount) {
        return formatMonetary(amount, {
            currencyId: this.state.currency_id,
        });
    }

    openTrips() {
        const today = new Date().toISOString().slice(0, 10);
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: `Bugungi Sotuvlar`,
            res_model: 'pos.order',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [['date_order', '>=', today + ' 00:00:00']],
            target: 'current',
        });
    }

    openSales() {
        this.action.doAction('point_of_sale.action_pos_order_line');
    }

    openSale(saleId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'pos.order',
            res_id: saleId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    openSalesByMethod(method) {
        const today = new Date().toISOString().slice(0, 10);
        let domain = [];

        if (method === 'cash') {
            domain = [['payment_method', '=', 'cash'], ['transaction_type', 'in', ['sale', 'kirim']], ['date', '>=', today + " 00:00:00"]];
        } else if (method === 'nasiya') {
            domain = [['payment_method', '=', 'nasiya']]; // Global nasiya, filter off date
        } else if (method === 'chiqim') {
            domain = [['transaction_type', '=', 'chiqim'], ['date', '>=', today + " 00:00:00"]];
        } else {
            domain = [['payment_method', '=', 'card'], ['transaction_type', 'in', ['sale', 'kirim']], ['date', '>=', today + " 00:00:00"]];
        }

        const methodNames = {
            'cash': 'Naqt Amaliyotlar',
            'card': 'Karta Amaliyotlari',
            'nasiya': 'Jami Nasiyalar',
            'chiqim': 'Chiqim Amaliyotlari'
        };

        let context = {};
        if (method === 'cash') context = { 'search_default_cash': 1 };
        else if (method === 'card') context = { 'search_default_card': 1 };
        else if (method === 'nasiya') context = { 'search_default_nasiya': 1 };
        else if (method === 'chiqim') context = { 'search_default_chiqim': 1 };

        console.log("DEBUG POS: Opening dashboard detail with domain:", domain);

        this.action.doAction({
            type: 'ir.actions.act_window',
            name: methodNames[method] || 'Amaliyotlar',
            res_model: 'van.dashboard.detail',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: context,
            target: 'current',
        });
    }
}

VanSalesDashboard.template = "van_sales_pharma.DashboardView";
registry.category("actions").add("van_sales_dashboard_action", VanSalesDashboard);
