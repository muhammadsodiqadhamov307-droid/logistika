/** @odoo-module */

import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { MaterialRequestPopup } from "./material_request_popup";
import { patch } from "@web/core/utils/patch";

patch(Navbar.prototype, {
    openMaterialRequestPopup() {
        this.dialog.add(MaterialRequestPopup);
    }
});
