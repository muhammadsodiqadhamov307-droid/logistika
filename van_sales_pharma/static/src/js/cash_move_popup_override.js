/** @odoo-module **/

import { CashMovePopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_popup";
import { patch } from "@web/core/utils/patch";
import { useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(CashMovePopup.prototype, {
    get partnerId() {
        return (this.pos.user && this.pos.user.partner_id) ? this.pos.user.partner_id.id : null;
    },
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");

        // Add custom state for our customer drop-down and debt
        this.customState = useState({
            selectedPartnerId: false,
            partners: [],
            partnerDebt: 0.0,
        });

        onWillStart(async () => {
            // Load Van Sales customers to populate the dropdown
            const partners = await this.orm.searchRead('res.partner', [['x_is_van_customer', '=', true]], ['id', 'name']);
            this.customState.partners = partners;
        });
    },

    async onPartnerChange(ev) {
        const partnerId = parseInt(ev.target.value);
        this.customState.selectedPartnerId = partnerId || false;

        if (partnerId) {
            // Fetch debt via RPC
            const debtInfo = await this.orm.call('res.partner', 'get_partner_van_debt', [partnerId]);
            this.customState.partnerDebt = debtInfo.total_due || 0.0;

            // Auto-fill amount if it's Kirim (Cash In)
            if (this.state.type === 'in' && this.customState.partnerDebt > 0) {
                this.state.amount = this.customState.partnerDebt.toString();
            }
        } else {
            this.customState.partnerDebt = 0.0;
        }
    },

    // Override the payload to inject the chosen partner_id
    _prepareTryCashInOutPayload(type, amount, reason, defaultPartnerId, extras) {
        // If a custom partner is selected for Kirim (in), use theirs instead of the logged-in user's
        const finalPartnerId = (type === 'in' && this.customState.selectedPartnerId)
            ? this.customState.selectedPartnerId
            : defaultPartnerId;

        // Provide a default reason if it's left empty
        let finalReason = reason;
        if (!finalReason || finalReason.trim() === '') {
            finalReason = type === 'in' ? 'Kirim (Pul kiritildi)' : 'Chiqim (Pul olindi)';
        }

        return [[this.pos.session.id], type, amount, finalReason, finalPartnerId, extras];
    },

    // Override the validation so "Sabab" (reason) is no longer strictly required
    isValidCashMove() {
        return this.env.utils.isValidFloat(this.state.amount);
    }
});
