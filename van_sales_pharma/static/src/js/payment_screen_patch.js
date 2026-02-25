/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

/**
 * Patch PaymentScreen.validateOrder to trigger a page reload after
 * a successful sale. This ensures zero-stock products are removed from
 * the POS product list by re-running the backend _load_pos_data_domain filter.
 */
patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate = false) {
        // Get the current order before validation (it may be cleared after)
        const order = this.currentOrder;
        const hadLines = order && order.lines && order.lines.length > 0;

        // Call the original validateOrder
        await super.validateOrder(isForceValidate);

        // After successful validation, reload the page so the product list
        // is refreshed and zero-stock Agent items disappear.
        if (hadLines) {
            setTimeout(() => window.location.reload(), 1500);
        }
    }
});
