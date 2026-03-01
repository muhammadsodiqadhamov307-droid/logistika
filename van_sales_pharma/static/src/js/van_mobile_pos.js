/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class VanMobilePos extends Component {
    setup() {
        this.action = useService("action");

        this.state = useState({
            screen: 'products', // clients, products, checkout, kirim
            error: null,

            // Data
            clients: [],
            inventory: [],

            // Active selection
            selectedClient: { id: false, name: 'Naqt savdo', total_due: 0 },
            cart: {}, // productId: {qty, product}

            // Post-checkout
            newNasiyaId: null,
            nasiyaAmount: 0,
            kirimAmount: 0,

            loading: true,
            searchQuery: '',
            productSearchQuery: '',

            // Quick Actions (Kirim / Chiqim)
            showQuickAction: false,
            quickActionType: 'kirim', // 'kirim' or 'chiqim'
            quickActionAmount: '',
            quickActionNote: '',
            quickActionPartnerId: '',

            // Action Menu (3-dots)
            showActionMenu: false,

            // Requests (So'rovlar)
            showRequestPopup: false,
            requestPartnerId: '',
            requestProductId: '',
            requestQty: '',
            requestNote: '',
        });

        onWillStart(async () => {
            await Promise.all([
                this.loadClients(),
                this.loadInventory()
            ]);
        });
    }

    async loadClients() {
        this.state.loading = true;
        try {
            this.state.clients = await rpc("/van/pos/get_clients", {});
        } catch (e) {
            this.state.error = "Xatolik: Mijozlarni yuklash imkonsiz.";
        }
        this.state.loading = false;
    }

    async loadInventory() {
        this.state.loading = true;
        try {
            this.state.inventory = await rpc("/van/pos/get_inventory", {});
        } catch (e) {
            this.state.error = "Xatolik: Omborni yuklash imkonsiz.";
        }
        this.state.loading = false;
    }

    selectClient(client) {
        this.state.selectedClient = client;
        this.state.screen = 'products';
    }

    get filteredClients() {
        if (!this.state.searchQuery) return this.state.clients;
        return this.state.clients.filter(c => c.name.toLowerCase().includes(this.state.searchQuery.toLowerCase()));
    }

    get filteredInventory() {
        if (!this.state.productSearchQuery) return this.state.inventory;
        return this.state.inventory.filter(p => p.name.toLowerCase().includes(this.state.productSearchQuery.toLowerCase()));
    }

    get cartItems() {
        return Object.values(this.state.cart);
    }

    get cartTotal() {
        return this.cartItems.reduce((sum, item) => sum + (item.qty * item.custom_price), 0);
    }

    addToCart(product) {
        if (this.state.cart[product.product_id]) {
            if (this.state.cart[product.product_id].qty < product.remaining) {
                this.state.cart[product.product_id].qty++;
            }
        } else {
            if (product.remaining > 0) {
                this.state.cart[product.product_id] = { qty: 1, product: product, custom_price: product.price };
            }
        }
    }

    removeFromCart(productId) {
        if (this.state.cart[productId]) {
            this.state.cart[productId].qty--;
            if (this.state.cart[productId].qty <= 0) {
                delete this.state.cart[productId];
            }
        }
    }

    setCartQuantity(product, ev) {
        let newQty = parseFloat(ev.target.value);
        if (isNaN(newQty) || newQty <= 0) {
            delete this.state.cart[product.product_id];
            return;
        }

        if (newQty > product.remaining) {
            newQty = product.remaining;
        }

        if (this.state.cart[product.product_id]) {
            this.state.cart[product.product_id].qty = newQty;
        } else {
            this.state.cart[product.product_id] = { qty: newQty, product: product, custom_price: product.price };
        }
    }

    setCartPrice(product, ev) {
        let newPrice = parseFloat(ev.target.value);
        if (isNaN(newPrice) || newPrice < 0) {
            newPrice = product.price; // fallback to default
        }
        if (this.state.cart[product.product_id]) {
            this.state.cart[product.product_id].custom_price = newPrice;
        }
    }

    goToCheckout() {
        if (this.cartItems.length > 0) {
            this.state.screen = 'checkout';
        }
    }

    async submitOrder() {
        this.state.loading = true;
        const lines = this.cartItems.map(item => ({
            product_id: item.product.product_id,
            qty: item.qty,
            price: item.custom_price
        }));

        try {
            const result = await rpc("/van/pos/submit_order", {
                partner_id: this.state.selectedClient.id,
                lines: lines
            });

            if (result.success) {
                this.state.newNasiyaId = result.nasiya_id;
                this.state.nasiyaAmount = result.nasiya_amount;
                this.state.kirimAmount = result.nasiya_amount; // Default kirim to total sum
                this.state.screen = 'kirim';
            } else {
                this.state.error = result.error || "Savdo amalga oshmadi.";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: Savdo amalga oshmadi.";
        }
        this.state.loading = false;
    }

    setKirimAmount(ev) {
        this.state.kirimAmount = parseFloat(ev.target.value) || 0;
    }

    async submitKirim(paymentMethod = 'cash') {
        if (this.state.kirimAmount > 0) {
            this.state.loading = true;
            try {
                await rpc("/van/pos/submit_kirim", {
                    nasiya_id: this.state.newNasiyaId,
                    amount: this.state.kirimAmount,
                    payment_method: paymentMethod
                });
            } catch (e) {
                console.error("Kirim failed", e);
            }
        }
        this.resetToStart();
    }

    resetToStart() {
        this.state.screen = 'products';
        this.state.selectedClient = { id: false, name: 'Naqt savdo', total_due: 0 };
        this.state.cart = {};
        this.state.newNasiyaId = null;
        this.state.searchQuery = '';
        this.state.productSearchQuery = '';
        this.state.showQuickAction = false;
        this.state.showActionMenu = false;
        this.state.showRequestPopup = false;
        this.loadClients();
    }

    // --- QUICK ACTIONS ---
    openQuickAction(type) {
        this.state.quickActionType = type;
        this.state.quickActionAmount = '';
        this.state.quickActionNote = '';
        this.state.quickActionPartnerId = '';
        this.state.showQuickAction = true;
    }

    closeQuickAction() {
        this.state.showQuickAction = false;
    }

    async submitQuickAction() {
        const amount = parseFloat(this.state.quickActionAmount);
        if (isNaN(amount) || amount <= 0) {
            this.state.error = "Iltimos summani to'g'ri kiriting.";
            return;
        }

        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/submit_quick_action", {
                type: this.state.quickActionType,
                amount: amount,
                note: this.state.quickActionNote,
                partner_id: this.state.screen === 'products' ? this.state.selectedClient.id : (this.state.quickActionPartnerId ? parseInt(this.state.quickActionPartnerId) : null)
            });

            if (result.success) {
                this.closeQuickAction();
                // Optionally show a success toast here
            } else {
                this.state.error = result.error || "Amaliyot saqlanmadi.";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: Amaliyot saqlanmadi.";
        }
        this.state.loading = false;
    }

    // --- REQUESTS (SO'ROVLAR) ---
    async submitRequest() {
        if (!this.state.requestPartnerId) {
            this.state.error = "Iltimos mijozni tanlang.";
            return;
        }

        const qty = parseFloat(this.state.requestQty);
        if (isNaN(qty) || qty <= 0) {
            this.state.error = "Iltimos miqdorni to'g'ri kiriting.";
            return;
        }

        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/submit_request", {
                partner_id: parseInt(this.state.requestPartnerId),
                product_id: parseInt(this.state.requestProductId) || false,
                qty: qty,
                notes: this.state.requestNote
            });

            if (result.success) {
                this.state.showRequestPopup = false;
                this.state.requestPartnerId = '';
                this.state.requestProductId = '';
                this.state.requestQty = '';
                this.state.requestNote = '';
            } else {
                this.state.error = result.error || "So'rov saqlanmadi.";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: So'rov saqlanmadi.";
        }
        this.state.loading = false;
    }

    goBack() {
        if (this.state.screen === 'clients') {
            this.state.screen = 'products';
        } else if (this.state.screen === 'checkout') {
            this.state.screen = 'products';
        }
    }

    closePos() {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'reload',
        });
    }
}

VanMobilePos.template = "van_sales_pharma.VanMobilePos";
registry.category("actions").add("van_sales_pharma.MobilePosClientAction", VanMobilePos);
