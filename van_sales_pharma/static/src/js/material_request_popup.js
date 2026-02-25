/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";

export class MaterialRequestPopup extends Component {
    static template = "van_sales_pharma.MaterialRequestPopup";
    static components = { Dialog };
    static props = ["close", "getPayload?"];

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();
        this.searchInput = useRef("searchInput");
        this.searchTimeout = null;

        this.state = useState({
            searchResults: [],
            selectedLines: [],
            lineCounter: 0,
        });
    }

    async searchProducts() {
        const query = this.searchInput.el.value;
        if (!query || query.length < 2) {
            this.state.searchResults = [];
            return;
        }

        try {
            const products = await this.orm.call("product.product", "search_read", [
                [
                    "|", "|",
                    ["name", "ilike", query],
                    ["default_code", "ilike", query],
                    ["barcode", "ilike", query],
                    ["sale_ok", "=", true],
                ],
                ["display_name", "id", "uom_id"]
            ], { limit: 10 });

            this.state.searchResults = products;
        } catch (error) {
            console.error("Error searching products:", error);
            this.notification.add(_t("Xatolik yuz berdi. Iltimos qayta urining."), 3000);
        }
    }

    onSearchInput(ev) {
        clearTimeout(this.searchTimeout);
        if (ev.key === "Enter") {
            this.searchProducts();
        } else {
            this.searchTimeout = setTimeout(() => {
                this.searchProducts();
            }, 400); // 400ms debounce for real-time search
        }
    }

    addProduct(product) {
        const existing = this.state.selectedLines.find(l => l.product.id === product.id);
        if (existing) {
            existing.qty += 1;
        } else {
            this.state.lineCounter++;
            this.state.selectedLines.push({
                id: this.state.lineCounter,
                product: product,
                qty: 1,
            });
        }

        this.searchInput.el.value = "";
        this.state.searchResults = [];
        this.searchInput.el.focus();
    }

    removeLine(lineId) {
        this.state.selectedLines = this.state.selectedLines.filter(l => l.id !== lineId);
    }

    async confirm() {
        if (this.state.selectedLines.length === 0) {
            return;
        }

        try {
            const lines = this.state.selectedLines.map(line => {
                return {
                    product_id: line.product.id,
                    qty: line.qty,
                };
            });

            const tripId = await this.orm.call("van.trip", "create_material_request_from_pos", [
                this.pos.user.id,
                lines
            ]);

            if (tripId) {
                this.notification.add(_t("Material so'rovi muvaffaqiyatli bajarildi! Sahifa yangilanmoqda..."), 5000);
                this.props.close();

                // Refresh the POS application to pull the newly injected Agent inventory products
                setTimeout(() => window.location.reload(), 1500);
            }
        } catch (error) {
            console.error("Error creating material request:", error);
            this.notification.add(_t("So'rovni yuborishda xatolik yuz berdi. Internetni tekshiring."), 5000);
        }
    }
}
