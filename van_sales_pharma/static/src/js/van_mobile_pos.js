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

            // Requests (So'rovlar)
            requestsList: [],
            requestFilter: 'draft',
            requestPartnerId: '',
            requestPartnerName: '',
            requestNote: '',
            newRequestLines: [],

            // Picker Modals for newRequest form
            showClientPickerModal: false,
            clientSearchModal: '',
            showProductPickerModal: false,
            productSearchModal: '',
            tempSelectedProducts: new Set(),

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

        // Initialize IDB
        this.initIDB();

        onWillStart(async () => {
            // Setup history trap for hardware back buttons
            window.history.pushState(null, null, window.location.href);
            this.popStateHandler = () => {
                window.history.pushState(null, null, window.location.href); // Keep trapping
                this.goBack();
            };
            window.addEventListener('popstate', this.popStateHandler);

            await this.loadCurrentAgent();

            await Promise.all([
                this.loadClients(),
                this.loadInventory(),
                this.loadAllProducts(),
                this.loadTaminotchis()
            ]);

            this.state.pollingInterval = setInterval(() => {
                this.loadInventorySilent();
            }, 15000);
        });

        onWillDestroy(() => {
            window.removeEventListener('popstate', this.popStateHandler);
            if (this.state.pollingInterval) {
                clearInterval(this.state.pollingInterval);
            }
        });
    }

    onOnline() {
        this.state.isOnline = true;
        this.showToast("Internet tiklandi. Ma'lumotlar sinxronlanmoqda...", "success");
        this.syncOfflineTransactions();
    }

    onOffline() {
        this.state.isOnline = false;
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

    async loadClients() {
        this.state.loading = true;
        try {
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_clients", {});
                this.state.clients = result;
                await this.saveToIDB('clients', result);
            } else {
                this.state.clients = await this.getFromIDB('clients');
                if (!this.state.clients.length) this.showToast("Offline rejimda mijozlar topilmadi.", "warning");
            }
        } catch (e) {
            console.error(e);
            this.state.clients = await this.getFromIDB('clients');
            if (this.state.isOnline) this.showToast("Mijozlarni yuklashda xatolik. Offline bazadan foydalanilmoqda.", "error");
        }
        this.state.loading = false;
    }

    async loadInventory() {
        try {
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_inventory", {});
                this.state.inventory = result;
                await this.saveToIDB('inventory', result);
            } else {
                this.state.inventory = await this.getFromIDB('inventory');
            }
        } catch (e) {
            console.error(e);
            this.state.inventory = await this.getFromIDB('inventory');
            if (this.state.error) this.state.error = "Ombor yuklashda muammo, offline ma'lumot qullanilmoqda";
        }
    }

    async loadCurrentAgent() {
        try {
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_current_agent", {});
                this.state.currentAgent = result;
                await this.saveToIDB('agent', [result], false); // Save as array of 1, isArray=false
            } else {
                const agents = await this.getFromIDB('agent');
                if (agents && agents.length > 0) {
                    this.state.currentAgent = agents[0];
                }
            }
        } catch (e) {
            console.error(e);
            const agents = await this.getFromIDB('agent');
            if (agents && agents.length > 0) this.state.currentAgent = agents[0];
        }
    }

    async loadTaminotchis() {
        try {
            if (this.state.isOnline) {
                const result = await rpc("/van/pos/get_taminotchilar", {});
                this.state.taminotchis = result;
                await this.saveToIDB('taminotchis', result);
            } else {
                this.state.taminotchis = await this.getFromIDB('taminotchis');
            }
            if (this.state.taminotchis && this.state.taminotchis.length > 0) {
                // If currentAgent has a default_taminotchi_id, use it, otherwise default to the first one
                if (this.state.currentAgent && this.state.currentAgent.default_taminotchi_id) {
                    this.state.selectedTaminotchiId = this.state.currentAgent.default_taminotchi_id;
                } else {
                    this.state.selectedTaminotchiId = this.state.taminotchis[0].id;
                }
            }
        } catch (e) {
            console.error(e);
            this.state.taminotchis = await this.getFromIDB('taminotchis');
        }
    }

    async loadAllProducts() {
        try {
            const result = await rpc("/van/pos/get_all_products", {});
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
            const freshInventory = await rpc("/van/pos/get_inventory", {});
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

    get filteredModalProducts() {
        let base = this.state.allProducts;
        if (!this.state.productSearchModal) {
            return base;
        }
        const search = this.state.productSearchModal.toLowerCase();
        return base.filter(prod =>
            prod.name.toLowerCase().includes(search)
        );
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

    openProductPicker() {
        this.state.productSearchModal = '';
        // Pre-fill temp selection based on active screen
        if (this.state.screen === 'mahsulot_yuklash_form') {
            this.state.tempSelectedProducts = new Set(this.state.newTripLines.map(l => l.product_id));
        } else {
            this.state.tempSelectedProducts = new Set(this.state.newRequestLines.map(l => l.product_id));
        }
        this.state.showProductPickerModal = true;
    }

    closeProductPicker() {
        this.state.showProductPickerModal = false;
    }

    toggleProductSelection(product_id) {
        if (this.state.tempSelectedProducts.has(product_id)) {
            this.state.tempSelectedProducts.delete(product_id);
        } else {
            this.state.tempSelectedProducts.add(product_id);
        }
        // Force Owl update for Set
        this.state.tempSelectedProducts = new Set(this.state.tempSelectedProducts);
    }

    confirmProductSelection() {
        const currentLinesMap = new Map();
        const activeContainer = this.state.screen === 'mahsulot_yuklash_form' ? this.state.newTripLines : this.state.newRequestLines;

        activeContainer.forEach(l => {
            currentLinesMap.set(l.product_id, l);
        });

        // Rebuild lines
        const newLines = [];
        for (const product_id of this.state.tempSelectedProducts) {
            const product = this.state.allProducts.find(p => p.product_id === product_id);
            if (!product) continue;

            if (currentLinesMap.has(product_id)) {
                newLines.push(currentLinesMap.get(product_id));
            } else {
                newLines.push({
                    product_id: product_id,
                    product_name: product.name,
                    price: product.price,
                    qty: 1
                });
            }
        }

        if (this.state.screen === 'mahsulot_yuklash_form') {
            this.state.newTripLines = newLines;
        } else {
            this.state.newRequestLines = newLines;
        }

        this.closeProductPicker();
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
                // We'll just ask for kirim using the offline_id as reference or skip to products.
                // UX decision: skip directly to home and show warning, kirim can be done separately if they want,
                // or we can allow a partial kirim linked to this offline_id. Easiest: return to start for offline.
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
        if (this.state.kirimAmount > 0) {
            this.state.loading = true;
            if (this.state.isOnline && this.state.newNasiyaId) {
                try {
                    await rpc("/van/pos/submit_kirim", {
                        nasiya_id: this.state.newNasiyaId,
                        amount: this.state.kirimAmount,
                        payment_method: paymentMethod
                    });
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
            if (this.state.quickActionType === 'kirim') tx.type = 'kirim';

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
                this.state.newRequestLines = [];
                this.state.activeRequest = null;
            } else {
                this.state.error = result.error || "So'rovlarni o'qishda xatolik";
            }
        } catch (e) {
            this.state.error = "Tarmoqda xatolik";
        }
        this.state.loading = false;
    }

    addRequestLine() {
        // Obsolete function, replaced by multi-select modal confirmProductSelection
    }

    removeRequestLine(index) {
        if (this.state.newRequestLines.length > 1) {
            this.state.newRequestLines.splice(index, 1);
        }
    }

    updateRequestLineProduct(index, ev) {
        this.state.newRequestLines[index].product_id = ev.target.value;
    }

    updateRequestLineQty(index, ev) {
        this.state.newRequestLines[index].qty = ev.target.value;
    }

    updateTripLineQty(index, ev) {
        this.state.newTripLines[index].qty = ev.target.value;
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

        const validLines = this.state.newRequestLines.filter(l => l.product_id && parseFloat(l.qty) > 0);

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
