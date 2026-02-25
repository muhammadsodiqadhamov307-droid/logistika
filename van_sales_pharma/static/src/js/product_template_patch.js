/** @odoo-module */

import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { patch } from "@web/core/utils/patch";

patch(ProductTemplate.prototype, {
    get canBeDisplayed() {
        // For Van Sales Pharma: The Python backend strictly curates the loaded products
        // to exactly match the Agent's Truck. 
        // We override this native frontend check to ensure imported products display 
        // even if their global DB 'available_in_pos' flag happens to be false.
        return this.active;
    }
});
