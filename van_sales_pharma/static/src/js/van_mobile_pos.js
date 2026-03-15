/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onWillDestroy, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";

export class VanMobilePos extends Component {
    setup() {
        this.action = useService("action");
        this.session = session;
        this.notification = useService("notification");

        useExternalListener(window, "click", this.onWindowClick);

        this.state = useState({
            screen: 'products', // clients, products, checkout, kirim
            error: null,

            // Data
            clients: [],
            inventory: [],
            allProducts: [],

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
            quickActionExpenseType: 'daily',

            // Action Menu (3-dots)
            showActionMenu: false,

            // Agent Picker (admin)
            showAgentPicker: false,
            agentsList: [],

            // Requests (So'rovlar)
            requestsList: [],
            requestFilter: 'draft',
            requestPartnerId: '',
            requestPartnerName: '',
            requestNote: '',
            requestCart: {},

            // Picker Modals for newRequest form
            showClientPickerModal: false,
            clientSearchModal: '',

            // Mahsulot Yuklash (Trip Load) features
            currentAgent: null,
            taminotchis: [],
            selectedTaminotchiId: null,
            tripsList: [],
            activeTrip: null,
            tripDate: new Date().toISOString().split('T')[0], // Defaults to today
            tripNote: '',
            tripCart: {},

            pollingInterval: null,

            // Offline Support
            isOnline: navigator.onLine,
            syncQueue: [],
            isSyncing: false,
        });

        // Initialize connection listeners
        useExternalListener(window, "online", this.onOnline.bind(this));
        useExternalListener(window, "offline", this.onOffline.bind(this));

        onWillStart(async () => {
            // Setup AGGRESSIVE history trap for hardware back buttons
            // Push many states upfront so the history stack is deep
            for (let i = 0; i < 50; i++) {
                window.history.pushState({ van_pos: true }, '', window.location.href);
            }

            this.popStateHandler = () => {
                // Immediately re-fill the stack so it never drains
                for (let i = 0; i < 10; i++) {
                    window.history.pushState({ van_pos: true }, '', window.location.href);
                }
                this.goBack();
            };
            window.addEventListener('popstate', this.popStateHandler);

            // Also guard against page unload/navigation
            this.beforeUnloadHandler = (ev) => {
                ev.preventDefault();
                ev.returnValue = '';
            };
            window.addEventListener('beforeunload', this.beforeUnloadHandler);

            // CRITICAL: wait for IDB to be ready BEFORE loading data
            // Without this, this.db is null and all IDB reads return empty
            await this.initIDB();

            await this.loadCurrentAgent();

            await Promise.all([
                this.loadClients(),
                this.loadInventory(),
                this.loadAllProducts(),
                this.loadTaminotchis()
            ]);

            this.state.pollingInterval = setInterval(() => {
                if (this.state.isOnline) this.loadInventorySilent();
            }, 15000);

            // Hide Odoo Navbar for standalone app experience
            this.posStyle = document.createElement('style');
            this.posStyle.id = 'van-pos-fullscreen-style';
            this.posStyle.innerHTML = `
                .o_main_navbar { display: none !important; }
                .o_web_client { padding-top: 0 !important; }
                .o_content { overflow: auto !important; height: 100vh !important; }
            `;
            document.head.appendChild(this.posStyle);
            document.body.classList.add('van-pos-active');
        });

        onWillDestroy(() => {
            window.removeEventListener('popstate', this.popStateHandler);
            window.removeEventListener('beforeunload', this.beforeUnloadHandler);
            if (this.state.pollingInterval) {
                clearInterval(this.state.pollingInterval);
            }
            if (this.posStyle) {
                this.posStyle.remove();
            }
            document.body.classList.remove('van-pos-active');
        });
    }

    onOnline() {
        this.state.isOnline = true;
        document.body.style.overscrollBehavior = 'auto';
        this.showToast("Internet tiklandi. Ma'lumotlar sinxronlanmoqda...", "success");
        // Refresh data from server now that we're back online
        Promise.all([
            this.loadClients(),
            this.loadInventory(),
            this.loadCurrentAgent(),
            this.loadTaminotchis(),
        ]);
        this.syncOfflineTransactions();
    }

    onOffline() {
        this.state.isOnline = false;
        document.body.style.overscrollBehavior = 'none';
        this.showToast("Internetdan uzildi. Offline rejimda ishlayapsiz.", "warning");
    }

    // --- Toast Notification ---
    showToast(message, type = "info") {
        if (this.notification) {
            this.notification.add(message, { type: type });
        } else {
            console.log(`[Toast ${type}]: ${message}`);
        }
    }

    // --- IndexedDB Wrapper ---
    async initIDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open('VanSalesAppDB', 1);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains('clients')) {
                    db.createObjectStore('clients', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('inventory')) {
                    db.createObjectStore('inventory', { keyPath: 'product_id' });
                }
                if (!db.objectStoreNames.contains('allProducts')) {
                    db.createObjectStore('allProducts', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('agent')) {
                    db.createObjectStore('agent', { keyPath: 'id' }); // Dummy id 1
                }
                if (!db.objectStoreNames.contains('taminotchis')) {
                    db.createObjectStore('taminotchis', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('syncQueue')) {
                    db.createObjectStore('syncQueue', { keyPath: 'offline_id' });
                }
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                this.loadQueueFromIDB();
                resolve();
            };

            request.onerror = (event) => {
                console.error("IndexedDB error:", event.target.error);
                reject(event.target.error);
            };
        });
    }

    async saveToIDB(storeName, data, isArray = true) {
        if (!this.db) return;
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);

            // Clear existing data before bulk save
            store.clear();

            // Deep clone to remove Owl Proxies to prevent DataCloneError
            const cleanData = JSON.parse(JSON.stringify(data));

            if (isArray) {
                cleanData.forEach(item => store.put(item));
            } else {
                store.put(cleanData);
            }

            transaction.oncomplete = () => resolve();
            transaction.onerror = (e) => reject(e.target.error);
        });
    }

    async getFromIDB(storeName) {
        if (!this.db) return [];
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();

            request.onsuccess = () => resolve(request.result);
            request.onerror = (e) => reject(e.target.error);
        });
    }

    // Single item IDB ops for Queue
    async saveQueueItem(item) {
        if (!this.db) return;
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['syncQueue'], 'readwrite');
            const store = transaction.objectStore('syncQueue');
            // Remove Proxy
            const cleanItem = JSON.parse(JSON.stringify(item));
            store.put(cleanItem);
            transaction.oncomplete = () => resolve();
            transaction.onerror = (e) => reject(e.target.error);
        });
    }

    async deleteQueueItem(offlineId) {
        if (!this.db) return;
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['syncQueue'], 'readwrite');
            const store = transaction.objectStore('syncQueue');
            store.delete(offlineId);
            transaction.oncomplete = () => resolve();
            transaction.onerror = (e) => reject(e.target.error);
        });
    }

    async loadQueueFromIDB() {
        try {
            const queue = await this.getFromIDB('syncQueue');
            this.state.syncQueue = queue || [];
        } catch (e) {
            console.error("Failed loading queue from IDB", e);
        }
    }

    // Add unique UUID generator
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            const r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    // --- End Offline Wrappers ---

    onWindowClick = (ev) => {
        if (!this.state.showActionMenu) return;

        const menu = document.getElementById('dots-menu');
        const dotsButton = document.getElementById('dots-button');

        if (menu && dotsButton) {
            if (!menu.contains(event.target) && !dotsButton.contains(event.target)) {
                this.state.showActionMenu = false;
            }
        }
    }

    async openAgentPicker() {
        if (!this.state.currentAgent || !this.state.currentAgent.is_admin) return;
        try {
            const agents = await rpc('/van/pos/get_agents', {});
            this.state.agentsList = agents || [];
            this.state.showAgentPicker = true;
        } catch (e) {
            this.showToast("Agentlar ro'yxatini yuklashda xatolik", "danger");
        }
    }

    async selectAgentFromModal(agentId) {
        try {
            await rpc('/van/pos/set_agent_session', { agent_id: agentId });
            this.state.showAgentPicker = false;
            // Refresh agent info and inventory with newly selected agent
            await this.loadCurrentAgent();
            await this.loadInventory();
            this.showToast("Agent o'zgartirildi", "success");
        } catch (e) {
            this.showToast("Agent almashtirishda xatolik", "danger");
        }
    }

    async loadClients() {
        this.state.loading = true;
        try {
            // Always load from IDB cache first so offline reloads work immediately
            const cached = await this.getFromIDB('clients');
            if (cached && cached.length > 0) {
                this.state.clients = cached;
            }
            // Then refresh from server if online
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_clients", {});
                this.state.clients = result;
                await this.saveToIDB('clients', result);
            } else if (!this.state.clients.length) {
                // Only warn if cache was also empty
                this.showToast("Offline rejimda mijozlar keshi bo'sh. Avval onlayn ulanib cache qiling.", "warning");
            }
        } catch (e) {
            console.error(e);
            const cached = await this.getFromIDB('clients');
            if (cached && cached.length > 0) this.state.clients = cached;
        }
        this.state.loading = false;
    }

    async loadInventory() {
        try {
            // Always load from IDB cache first so offline reloads work immediately
            const cached = await this.getFromIDB('inventory');
            if (cached && cached.length > 0) {
                this.state.inventory = cached;
            }
            // Then refresh from server if online
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_inventory?t=" + Date.now(), {});
                this.state.inventory = result;
                await this.saveToIDB('inventory', result);
            }
        } catch (e) {
            console.error(e);
            const cached = await this.getFromIDB('inventory');
            if (cached && cached.length > 0) this.state.inventory = cached;
        }
    }

    async loadCurrentAgent() {
        // Always load from IDB cache first
        try {
            const cached = await this.getFromIDB('agent');
            if (cached && cached.length > 0) {
                this.state.currentAgent = cached[0];
            }
        } catch (e) {
            console.error("Failed to load agent from IDB:", e);
        }

        if (!this.state.isOnline) {
            // If offline and no cached agent, we can't proceed
            if (!this.state.currentAgent) {
                this.showToast("Offline rejimda agent ma'lumotlari mavjud emas.", "warning");
            }
            return;
        }

        try {
            const result = await rpc('/van/pos/get_current_agent');
            if (result) {
                this.state.currentAgent = result;
                await this.saveToIDB('agent', [result], false); // Save as array for consistency with getFromIDB
            }
        } catch (e) {
            console.error("Agent yuklashda xatolik:", e);
            // If online fetch fails, rely on cached data if available
            if (!this.state.currentAgent) {
                this.showToast("Agent ma'lumotlarini yuklashda xatolik. Offline rejimga o'tildi.", "danger");
            }
        }
    }



    async loadTaminotchis() {
        try {
            // Always load from IDB cache first
            const cached = await this.getFromIDB('taminotchis');
            if (cached && cached.length > 0) {
                this.state.taminotchis = cached;
            }
            // Then refresh from server if online
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_taminotchis", {});
                this.state.taminotchis = result;
                await this.saveToIDB('taminotchis', result);
            }
            if (this.state.taminotchis && this.state.taminotchis.length > 0) {
                if (this.state.currentAgent && this.state.currentAgent.default_taminotchi_id) {
                    this.state.selectedTaminotchiId = this.state.currentAgent.default_taminotchi_id;
                } else {
                    this.state.selectedTaminotchiId = this.state.taminotchis[0].id;
                }
            }
        } catch (e) {
            console.error("Taminotchi rpc error:", e);
            const cached = await this.getFromIDB('taminotchis');
            if (cached && cached.length > 0) {
                this.state.taminotchis = cached;
                if (this.state.currentAgent && this.state.currentAgent.default_taminotchi_id) {
                    this.state.selectedTaminotchiId = this.state.currentAgent.default_taminotchi_id;
                } else {
                    this.state.selectedTaminotchiId = cached[0].id;
                }
            }
        }
    }

    async loadAllProducts() {
        try {
            const result = await rpc("/van/pos/get_all_products?t=" + Date.now(), {});
            this.state.allProducts = result;
        } catch (e) {
            console.error("Xatolik: Barcha mahsulotlarni yuklash imkonsiz.", e);
        }
    }

    async openTripsList() {
        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/get_trips", {});
            if (result.success) {
                this.state.tripsList = result.trips || [];
                this.state.screen = 'trips_list';

                // reset trip creation form
                this.state.tripDate = new Date().toISOString().split('T')[0];
                this.state.tripNote = '';
                this.state.tripCart = {};
                this.state.activeTrip = null;
            } else {
                this.state.error = result.error || "Sayohatlarni o'qishda xatolik";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: Sayohatlarni o'qish xatosi";
        }
        this.state.loading = false;
    }

    async loadInventorySilent() {
        try {
            const freshInventory = await rpc("/van/pos/get_inventory?t=" + Date.now(), {});
            this.state.inventory = freshInventory;

            // Reconcile and clean up cart if stock dropped unexpectedly
            for (const [productIdStr, item] of Object.entries(this.state.cart)) {
                const pId = parseInt(productIdStr);
                const freshProduct = freshInventory.find(p => p.product_id === pId);

                if (!freshProduct || freshProduct.remaining <= 0) {
                    delete this.state.cart[pId]; // Item vanished or solid out
                } else if (item.qty > freshProduct.remaining) {
                    this.state.cart[pId].qty = freshProduct.remaining; // Cap maximum to new limit
                    this.state.cart[pId].product.remaining = freshProduct.remaining;
                } else {
                    this.state.cart[pId].product.remaining = freshProduct.remaining; // Update strictly for UI
                }
            }
        } catch (e) {
            console.error("Silent stock polling failed:", e);
        }
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
        let base = this.state.inventory.filter(p => p.remaining > 0);
        if (!this.state.productSearchQuery) return base;
        return base.filter(p => p.name.toLowerCase().includes(this.state.productSearchQuery.toLowerCase()));
    }

    get filteredAllProducts() {
        let base = this.state.allProducts;
        if (!this.state.productSearchQuery) return base;
        return base.filter(p => p.name.toLowerCase().includes(this.state.productSearchQuery.toLowerCase()));
    }

    get filteredRequests() {
        if (this.state.requestFilter === 'all') {
            return this.state.requestsList;
        }
        return this.state.requestsList.filter(req => req.state === this.state.requestFilter);
    }

    get filteredModalClients() {
        if (!this.state.clientSearchModal) {
            return this.state.clients;
        }
        const search = this.state.clientSearchModal.toLowerCase();
        return this.state.clients.filter(client =>
            client.name.toLowerCase().includes(search)
        );
    }

    get requestCartTotal() {
        return Object.values(this.state.requestCart).reduce((sum, item) => sum + (item.qty * item.price), 0);
    }

    changeRequestLineQty(product, delta) {
        if (!this.state.requestCart) this.state.requestCart = {};
        const pId = product.product_id;
        if (!this.state.requestCart[pId]) {
            if (delta > 0) {
                this.state.requestCart[pId] = { product_id: pId, qty: delta, price: product.price };
            }
        } else {
            this.state.requestCart[pId].qty += delta;
            if (this.state.requestCart[pId].qty <= 0) {
                delete this.state.requestCart[pId];
            }
        }
    }

    setRequestLineQty(product, ev) {
        if (!this.state.requestCart) this.state.requestCart = {};
        const pId = product.product_id;
        let newQty = parseInt(ev.target.value);
        if (isNaN(newQty) || newQty <= 0) {
            delete this.state.requestCart[pId];
            ev.target.value = 0;
        } else {
            if (!this.state.requestCart[pId]) {
                this.state.requestCart[pId] = { product_id: pId, qty: newQty, price: product.price };
            } else {
                this.state.requestCart[pId].qty = newQty;
            }
            ev.target.value = newQty;
        }
    }

    get tripCartTotal() {
        return Object.values(this.state.tripCart).reduce((sum, item) => sum + (item.qty * item.price), 0);
    }

    changeTripLineQty(product, delta) {
        if (!this.state.tripCart) this.state.tripCart = {};
        const pId = product.product_id;
        if (!this.state.tripCart[pId]) {
            if (delta > 0) {
                this.state.tripCart[pId] = { product_id: pId, qty: delta, price: product.price };
            }
        } else {
            this.state.tripCart[pId].qty += delta;
            if (this.state.tripCart[pId].qty <= 0) {
                delete this.state.tripCart[pId];
            }
        }
    }

    setTripLineQty(product, ev) {
        if (!this.state.tripCart) this.state.tripCart = {};
        const pId = product.product_id;
        let newQty = parseInt(ev.target.value);
        if (isNaN(newQty) || newQty <= 0) {
            delete this.state.tripCart[pId];
            ev.target.value = 0;
        } else {
            if (!this.state.tripCart[pId]) {
                this.state.tripCart[pId] = { product_id: pId, qty: newQty, price: product.price };
            } else {
                this.state.tripCart[pId].qty = newQty;
            }
            ev.target.value = newQty;
        }
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

    // --- LOCAL CACHE UPDATERS ---
    updateLocalClientBalance(partnerId, deltaAmount) {
        if (!partnerId || deltaAmount === 0) return;
        const client = this.state.clients.find(c => c.id === partnerId);
        if (client) {
            client.total_due = (client.total_due || 0) + deltaAmount;
            // Background save to cache so it reflects immediately
            this.saveToIDB('clients', this.state.clients);
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

        const isNasiya = (this.state.selectedClient.id !== false);
        const data = {
            partner_id: this.state.selectedClient.id,
            lines: lines,
            isNasiya: isNasiya
        };

        if (this.state.isOnline) {
            try {
                const result = await rpc("/van/pos/submit_order", data);

                if (result.success) {
                    this.loadInventorySilent(); // Trigger immediate stock update

                    if (!isNasiya) {
                        // Naqt savdo: money is already received, skip payment screen.
                        this.resetToStart();
                        this.showToast("Savdo muvaffaqiyatli saqlandi!", "success");
                    } else {
                        // Nasiya: prompt for partial/full payment.
                        this.state.newNasiyaId = result.nasiya_id;
                        this.state.nasiyaAmount = result.nasiya_amount;
                        this.state.kirimAmount = result.nasiya_amount;
                        // DO NOT update balance locally yet, submitKirim will handle it.
                        this.state.screen = 'kirim';
                        this.showToast("Nasiya saqlandi. To'lovni kiriting.", "success");
                    }
                } else {
                    this.state.error = result.error || "Savdo amalga oshmadi.";
                }
            } catch (e) {
                this.state.error = "Tarmoqda xatolik: Savdo amalga oshmadi.";
            }
        } else {
            // OFFLINE SAVE
            const offline_id = this.generateUUID();
            const tx = {
                offline_id: offline_id,
                type: 'sale',
                timestamp: new Date().toISOString(),
                data: data
            };
            await this.saveQueueItem(tx);
            this.state.syncQueue.push(tx);

            // Local deduct logic (UX)
            for (let item of this.cartItems) {
                let invLine = this.state.inventory.find(i => i.product_id === item.product.product_id);
                if (invLine) invLine.remaining -= item.qty;
            }
            await this.saveToIDB('inventory', this.state.inventory);

            if (!isNasiya) {
                this.resetToStart();
                this.showToast("Offline saqlandi. Internet bo'lganda sinxronlanadi.", "warning");
            } else {
                // For Nasiya, offline we can't get a real nasiya_id. 
                // Add the whole cart amount to local client balance
                const orderAmount = this.cartItems.reduce((acc, item) => acc + (item.qty * item.custom_price), 0);
                this.updateLocalClientBalance(this.state.selectedClient.id, orderAmount);

                this.resetToStart();
                this.showToast("Offline Nasiya saqlandi (Kirim uchun alohida amaliyot ishlating).", "warning");
            }
        }
        this.state.loading = false;
    }

    setKirimAmount(ev) {
        this.state.kirimAmount = parseFloat(ev.target.value) || 0;
    }

    async submitKirim(paymentMethod = 'cash') {
        const amount = this.state.kirimAmount;
        if (amount >= 0) {
            this.state.loading = true;
            if (this.state.isOnline && this.state.newNasiyaId) {
                try {
                    await rpc("/van/pos/submit_kirim", {
                        nasiya_id: this.state.newNasiyaId,
                        amount: amount,
                        payment_method: paymentMethod
                    });

                    // Locally update balance: (Total Nasiya - Paid Kirim)
                    const delta = this.state.nasiyaAmount - amount;
                    this.updateLocalClientBalance(this.state.selectedClient.id, delta);

                    this.showToast("To'lov saqlandi", "success");
                } catch (e) {
                    console.error("Kirim failed", e);
                }
            } else if (!this.state.isOnline) {
                this.showToast("Nasiyaga offline qisman to'lov hozircha amalga oshirib bo'lmaydi. Uni mijoz oynasidan Kirim qiling", "error");
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
        this.state.requestsList = [];
        this.loadClients();
    }

    // --- QUICK ACTIONS ---
    openQuickAction(type) {
        this.state.quickActionType = type;
        this.state.quickActionAmount = '';
        this.state.quickActionNote = '';
        this.state.quickActionPartnerId = '';
        this.state.quickActionExpenseType = 'daily';
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

        const data = {
            type: this.state.quickActionType,
            amount: amount,
            note: this.state.quickActionNote,
            partner_id: this.state.screen === 'products' ? this.state.selectedClient.id : (this.state.quickActionPartnerId ? parseInt(this.state.quickActionPartnerId) : null),
            expense_type: this.state.quickActionExpenseType
        };

        this.state.loading = true;

        if (this.state.isOnline) {
            try {
                const result = await rpc("/van/pos/submit_quick_action", data);

                if (result.success) {
                    // Locally update balance if this was a kirim from a client
                    if (this.state.quickActionType === 'kirim' && data.partner_id) {
                        this.updateLocalClientBalance(data.partner_id, -amount);
                    }

                    this.loadCurrentAgent(); // Refresh agent balance if it was a salary withdrawal
                    this.closeQuickAction();
                    this.showToast("Amaliyot saqlandi!", "success");
                } else {
                    this.state.error = result.error || "Amaliyot saqlanmadi.";
                }
            } catch (e) {
                this.state.error = "Tarmoqda xatolik: Amaliyot saqlanmadi.";
            }
        } else {
            // OFFLINE SAVE
            const offline_id = this.generateUUID();
            const tx = {
                offline_id: offline_id,
                type: 'chiqim', // Assuming quickAction is generally Chiqim unless type is 'kirim' handled above
                timestamp: new Date().toISOString(),
                data: data
            };

            if (this.state.quickActionType === 'kirim') {
                tx.type = 'kirim';
                if (data.partner_id) {
                    this.updateLocalClientBalance(data.partner_id, -amount);
                }
            }

            await this.saveQueueItem(tx);
            this.state.syncQueue.push(tx);

            this.closeQuickAction();
            this.showToast("Offline saqlandi. Internet bo'lganda sinxronlanadi.", "warning");
        }

        this.state.loading = false;
    }

    // --- OFFLINE SYNC LOGIC ---
    async syncOfflineTransactions() {
        if (!this.state.isOnline || this.state.syncQueue.length === 0 || this.state.isSyncing) return;

        this.state.isSyncing = true;
        this.showToast(`Sinxronlanmoqda... (${this.state.syncQueue.length} ta amaliyot)`, "info");

        try {
            // Only send the ones currently in queue
            const transactionsToSend = [...this.state.syncQueue];

            const result = await rpc("/van/pos/sync_offline", {
                transactions: transactionsToSend
            });

            if (result.status === 'success' || result.status === 'partial_success') {
                // Remove synced items
                for (let syncedId of result.synced) {
                    await this.deleteQueueItem(syncedId);
                    this.state.syncQueue = this.state.syncQueue.filter(t => t.offline_id !== syncedId);
                }

                if (result.errors && result.errors.length > 0) {
                    this.showToast("Ba'zi amaliyotlar sinxronlanmadi. Buxgalteriyaga murojaat qiling.", "error");
                    console.error("Sync Errors:", result.errors);
                } else {
                    this.showToast("Barcha ma'lumotlar sinxronlandi ✅", "success");
                }

                // Refresh data if possible
                this.loadInventorySilent();
                this.loadClients();
                this.loadCurrentAgent();
            }
        } catch (e) {
            console.error("Sinxronlashda xato:", e);
            this.showToast("Sinxronlashda tarmoq xatosi.", "error");
        }

        this.state.isSyncing = false;
    }

    goToOfflineQueue() {
        this.state.screen = 'offline_queue';
        this.state.showActionMenu = false;
    }

    // --- REQUESTS (SO'ROVLAR) ---
    async openRequestsList() {
        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/get_requests", {});
            if (result.success) {
                this.state.requestsList = result.requests || [];
                this.state.screen = 'requests_list';
                this.state.requestFilter = 'draft';
                this.state.requestPartnerId = '';
                this.state.requestNote = '';
                this.state.requestCart = {};
                this.state.activeRequest = null;
            } else {
                this.state.error = result.error || "So'rovlarni o'qishda xatolik";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik";
        }
        this.state.loading = false;
    }

    // Modal Picker Handlers
    openClientPicker() {
        this.state.clientSearchModal = '';
        this.state.showClientPickerModal = true;
    }

    closeClientPicker() {
        this.state.showClientPickerModal = false;
    }

    selectRequestClient(client) {
        this.state.requestPartnerId = client.id;
        this.state.requestPartnerName = client.name;
        this.closeClientPicker();
    }

    async updateRequestState(requestId, newState) {
        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/update_request_state", {
                request_id: requestId,
                state: newState
            });
            if (result.success) {
                await this.openRequestsList();
            } else {
                this.state.error = result.error || "Holatni o'zgartirish muvaffaqiyatsiz bo'ldi";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik";
        }
        this.state.loading = false;
    }

    async submitRequest() {
        if (!this.state.requestPartnerId) {
            this.state.error = "Iltimos mijozni tanlang.";
            return;
        }

        const validLines = Object.values(this.state.requestCart).filter(l => l.qty > 0);

        if (validLines.length === 0) {
            this.state.error = "Iltimos kamida bitta mahsulot va uning sonini kiriting.";
            return;
        }

        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/submit_request", {
                partner_id: parseInt(this.state.requestPartnerId),
                lines: validLines,
                notes: this.state.requestNote
            });

            if (result.success) {
                // Refresh list and go backward
                await this.openRequestsList();
            } else {
                this.state.error = result.error || "So'rov saqlanmadi.";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: So'rov saqlanmadi.";
        }
        this.state.loading = false;
    }

    viewRequestDetails(req) {
        this.state.activeRequest = req;
        this.state.screen = 'request_details';
    }

    viewTripDetails(trip) {
        this.state.activeTrip = trip;
        this.state.screen = 'trip_details';
    }

    async submitTrip() {
        if (!this.state.currentAgent) {
            this.state.error = "Sizning akkauntingizga agent biriktirilmagan.";
            return;
        }

        const validLines = Object.values(this.state.tripCart).filter(l => l.qty > 0);

        if (validLines.length === 0) {
            this.state.error = "Iltimos kamida bitta mahsulot tanlang.";
            return;
        }

        this.state.loading = true;
        try {
            const result = await rpc("/van/pos/submit_trip", {
                agent_id: parseInt(this.state.currentAgent.id),
                taminotchi_id: this.state.selectedTaminotchiId,
                date: this.state.tripDate,
                note: this.state.tripNote,
                lines: validLines
            });

            if (result.success) {
                this.loadInventorySilent(); // Trigger stock push to UI
                await this.openTripsList();
            } else {
                this.state.error = result.error || "Sayohatni saqlash muvaffaqiyatsiz.";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik: Sayohat saqlanmadi.";
        }
        this.state.loading = false;
    }

    goBack() {
        if (this.state.screen === 'clients') {
            this.state.screen = 'products';
        } else if (this.state.screen === 'checkout') {
            this.state.screen = 'products';
        } else if (this.state.screen === 'requests_list') {
            this.state.screen = 'products';
        } else if (this.state.screen === 'new_request_form') {
            this.state.screen = 'requests_list';
        } else if (this.state.screen === 'request_details') {
            this.state.activeRequest = null;
            this.state.screen = 'requests_list';
        } else if (this.state.screen === 'trips_list') {
            this.state.screen = 'products';
        } else if (this.state.screen === 'mahsulot_yuklash_form') {
            this.state.screen = 'trips_list';
        } else if (this.state.screen === 'trip_details') {
            this.state.activeTrip = null;
            this.state.screen = 'trips_list';
        } else {
            // Already on root screen (products) — keep the history trap active so
            // the hardware back button never navigates away from the POS.
            window.history.pushState(null, null, window.location.href);
        }
    }

    openAgentSummary() {
        if (!this.state.currentAgent) {
            this.state.error = "Akkauntingizga agent biriktirilmagan.";
            return;
        }

        // Remove popstate listener briefly so standard Odoo back buttons work
        if (this.popStateHandler) {
            window.removeEventListener('popstate', this.popStateHandler);
        }

        // Directly open the agent summary form view for the current agent
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Agent Hisoboti',
            res_model: 'van.agent.summary',
            res_id: this.state.currentAgent.summary_id,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current',
        });
    }

    closePos() {
        if (this.popStateHandler) {
            window.removeEventListener('popstate', this.popStateHandler);
        }
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'reload',
        });
    }

    logout() {
        window.location.href = '/web/session/logout';
    }

    goToDashboard() {
        this.action.doAction('van_sales_pharma.action_van_sales_dashboard');
    }
}

VanMobilePos.template = "van_sales_pharma.VanMobilePos";
registry.category("actions").add("van_sales_pharma.MobilePosClientAction", VanMobilePos);
