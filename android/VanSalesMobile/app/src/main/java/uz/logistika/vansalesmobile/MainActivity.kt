package uz.logistika.vansalesmobile

import android.app.Activity
import android.app.AlertDialog
import android.app.DatePickerDialog
import android.net.ConnectivityManager
import android.net.Network
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.PopupWindow
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import uz.logistika.vansalesmobile.data.LocalDatabase
import uz.logistika.vansalesmobile.data.SessionStore
import uz.logistika.vansalesmobile.sync.SyncRepository
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.UUID

class MainActivity : Activity() {
    private enum class ScreenState {
        LOGIN,
        POS,
        MENU,
        CLIENT_SELECTION,
        CLIENT_REPORT,
        AGENT_REPORT,
        REQUEST_LIST,
        REQUEST_FORM,
        REQUEST_DETAILS,
        REQUEST_ADD_PRODUCT,
        KIRIM_HISTORY,
        CHIQIM_HISTORY,
        TRIP_LIST,
        TRIP_DETAILS,
        TRIP_FORM
    }

    private lateinit var db: LocalDatabase
    private lateinit var session: SessionStore
    private lateinit var repository: SyncRepository
    private lateinit var status: TextView
    private val cart = linkedMapOf<Long, CartLine>()
    private var selectedClientId: Long = 0
    private var selectedClientName: String = "Naqt savdo"
    private var productSearchQuery: String = ""
    private var clientSearchQuery: String = ""
    private var currentScreenState: ScreenState = ScreenState.LOGIN
    private var refreshInFlight = false
    private var lastAutoRefreshAt = 0L
    private var editingReportTxnKey: String? = null
    private var editKirimAmountText = ""
    private var reportDateFrom: String = ""
    private var reportDateTo: String = ""
    private var activeReportClientId: Long = 0L
    private var agentReportDateFrom: String = SimpleDateFormat("dd.MM.yyyy", Locale.US).format(Date())
    private var agentReportDateTo: String = SimpleDateFormat("dd.MM.yyyy", Locale.US).format(Date())
    private var agentReportInputDateFrom: String = agentReportDateFrom
    private var agentReportInputDateTo: String = agentReportDateTo
    private var agentReportTab: String = "sales"
    private var agentReportScrollY: Int = 0
    private var clientReportScrollY: Int = 0
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var activeTripId: Long = 0L
    private var tripDate: String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
    private var tripNote: String = ""
    private var tripProductSearchQuery: String = ""
    private val tripCart = linkedMapOf<Long, TripDraftLine>()
    private var requestFilter: String = "draft"
    private var requestPartnerId: Long = 0L
    private var requestPartnerName: String = ""
    private var requestNote: String = ""
    private var requestProductSearchQuery: String = ""
    private val requestCart = linkedMapOf<Long, RequestDraftLine>()
    private var activeRequestId: Long = 0L
    private var sourceRequestId: Long = 0L
    private var activeRequestName: String = ""
    private var activeRequestPartnerId: Long = 0L
    private var activeRequestPartnerName: String = ""
    private var activeRequestDate: String = ""
    private var activeRequestState: String = "draft"
    private var activeRequestNotes: String = ""
    private val activeRequestDraftLines = mutableListOf<RequestEditLine>()
    private val expandedReportTxnKeys = mutableSetOf<String>()
    private val editSaleQty = mutableMapOf<Long, Double>()
    private val editSalePrice = mutableMapOf<Long, Double>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        db = LocalDatabase(this)
        session = SessionStore(this)
        repository = SyncRepository(db, session)
        selectedClientId = session.selectedClientId
        selectedClientName = session.selectedClientName
        reportDateFrom = session.lastReportDateFrom
        reportDateTo = session.lastReportDateTo
        activeReportClientId = session.lastReportClientId
        agentReportDateFrom = session.lastAgentReportDateFrom.ifBlank { SimpleDateFormat("dd.MM.yyyy", Locale.US).format(Date()) }
        agentReportDateTo = session.lastAgentReportDateTo.ifBlank { SimpleDateFormat("dd.MM.yyyy", Locale.US).format(Date()) }
        agentReportInputDateFrom = agentReportDateFrom
        agentReportInputDateTo = agentReportDateTo
        agentReportTab = session.lastAgentReportTab.ifBlank { "sales" }
        registerNetworkCallback()

        if (session.token.isBlank()) {
            renderLogin()
        } else {
            restoreLastScreen()
        }
    }

    override fun onResume() {
        super.onResume()
        if (::session.isInitialized && session.token.isNotBlank()) {
            refreshOfflineData()
        }
    }

    override fun onDestroy() {
        unregisterNetworkCallback()
        db.close()
        super.onDestroy()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        when (currentScreenState) {
            ScreenState.LOGIN -> moveTaskToBack(true)
            ScreenState.POS -> moveTaskToBack(true)
            ScreenState.MENU -> renderPos()
            ScreenState.CLIENT_SELECTION -> renderPos()
            ScreenState.CLIENT_REPORT -> renderClientSelection()
            ScreenState.AGENT_REPORT -> renderPos()
            ScreenState.REQUEST_LIST -> renderPos()
            ScreenState.REQUEST_FORM -> renderRequestsList()
            ScreenState.REQUEST_DETAILS -> renderRequestsList()
            ScreenState.REQUEST_ADD_PRODUCT -> renderRequestsList()
            ScreenState.KIRIM_HISTORY -> renderPos()
            ScreenState.CHIQIM_HISTORY -> renderPos()
            ScreenState.TRIP_LIST -> renderPos()
            ScreenState.TRIP_DETAILS -> renderTripList()
            ScreenState.TRIP_FORM -> renderTripList()
        }
    }

    private fun renderLogin() {
        rememberNavigation(ScreenState.LOGIN)
        val baseUrlInput = editText("Odoo URL", session.baseUrl.ifBlank { "https://your-odoo-domain.com" })
        val databaseInput = editText("Database name", session.database)
        val loginInput = editText("Login", session.login)
        val passwordInput = editText("Password", "", password = true)
        status = text("Enter server details to open Mobile POS", 14)

        val root = verticalRoot().apply {
            addView(text("Van Sales Native", 24, bold = true))
            addView(text("Server URL, database, login, password", 14))
            addView(space())
            addView(baseUrlInput)
            addView(databaseInput)
            addView(loginInput)
            addView(passwordInput)
            addView(button("Enter Mobile POS") {
                runNetwork("Logging in and downloading offline data...") {
                    repository.login(
                        baseUrlInput.text.toString(),
                        databaseInput.text.toString(),
                        loginInput.text.toString(),
                        passwordInput.text.toString()
                    )
                    runOnUiThread { renderPos() }
                    "Mobile POS ready"
                }
            })
            addView(status)
        }

        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun renderPos() {
        rememberNavigation(ScreenState.POS)
        val clients = db.rows("clients", "is_cash_sale DESC, name ASC")
        val inventory = db.rows("inventory", "name ASC")
        if (session.token.isNotBlank()) {
            refreshOfflineData()
        }
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color("#f1f3f6"))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(10), dp(10), dp(110))
            setBackgroundColor(color("#f1f3f6"))
        }

        val clientItems = mutableListOf<ClientItem>()
        for (i in 0 until clients.length()) {
            val client = clients.getJSONObject(i)
            clientItems.add(ClientItem(client.optLong("id"), client.optString("name")))
        }
        if (clientItems.isEmpty()) {
            clientItems.add(ClientItem(0, "Naqt savdo (Mijozisiz)"))
        }
        if (clientItems.none { it.id == selectedClientId }) {
            selectedClientId = 0
            selectedClientName = "Naqt savdo"
        }
        status = text("", 12).apply { setTextColor(color("#64748b")) }
        page.addView(posNavbar("POS", clientItems))
        root.addView(searchBox())
        root.addView(status)

        if (inventory.length() == 0) {
            root.addView(emptyCard("Hozircha mahsulot topilmadi. Internet bo'lganda yangilang."))
        } else {
            val grid = GridLayout(this).apply {
                columnCount = 2
                useDefaultMargins = false
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
            }
            for (i in 0 until inventory.length()) {
                val product = inventory.getJSONObject(i)
                if (productSearchQuery.isNotBlank() && !product.optString("name").contains(productSearchQuery, ignoreCase = true)) {
                    continue
                }
                grid.addView(productCard(product) {
                    addProduct(product)
                    renderPos()
                })
            }
            if (grid.childCount == 0) {
                root.addView(emptyCard("Qidiruv bo'yicha mahsulot topilmadi."))
            } else {
                root.addView(grid)
            }
        }

        page.addView(ScrollView(this).apply { addView(root) }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f
        ))
        if (cart.isNotEmpty()) {
            page.addView(bottomCartBar())
        }
        setContentView(page)
    }

    private fun renderPayment(type: String) {
        rememberNavigation(ScreenState.MENU)
        val clients = db.rows("clients", "is_cash_sale DESC, name ASC")
        val clientItems = mutableListOf<ClientItem>()
        for (i in 0 until clients.length()) {
            val client = clients.getJSONObject(i)
            clientItems.add(ClientItem(client.optLong("id"), client.optString("name")))
        }
        val clientSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, clientItems)
            visibility = if (type == "kirim") View.VISIBLE else View.GONE
        }
        val amountInput = editText("Summa", "")
        amountInput.inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        val noteInput = editText("Izoh", "")
        status = text(if (type == "kirim") "Kirim Qabul Qilish" else "Chiqim Qilish", 14)

        val root = verticalRoot().apply {
            addView(header(if (type == "kirim") "Kirim" else "Chiqim"))
            addView(status)
            if (type == "kirim") {
                addView(label("Mijoz"))
                addView(clientSpinner)
            }
            addView(label("Summa"))
            addView(amountInput)
            addView(label("Izoh"))
            addView(noteInput)
            addView(button("Saqlash") {
                val amount = amountInput.text.toString().replace(",", "").toDoubleOrNull() ?: 0.0
                if (amount <= 0) {
                    status.text = "Summani to'g'ri kiriting"
                    return@button
                }
                val selected = clientItems.getOrNull(clientSpinner.selectedItemPosition)
                val payload = JSONObject()
                    .put("amount", amount)
                    .put("note", noteInput.text.toString())
                    .put("payment_method", "cash")
                if (type == "kirim") {
                    payload.put("partner_id", selected?.id ?: false)
                } else {
                    payload.put("expense_type", "daily")
                }
                db.enqueueTransaction(type, UUID.randomUUID().toString(), payload)
                status.text = "Offline saqlandi. Internet bo'lganda sinxronlanadi."
                renderPos()
            })
            addView(button("Orqaga") { renderPos() })
        }
        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun renderCachedList(title: String, table: String) {
        rememberNavigation(ScreenState.MENU)
        val items = db.rows(table, "id DESC")
        val root = verticalRoot().apply {
            addView(header(title))
            addView(button("Orqaga") { renderPos() })
            if (items.length() == 0) {
                addView(text("Cached data empty. Refresh when online.", 14))
            } else {
                for (i in 0 until items.length()) {
                    val item = items.getJSONObject(i)
                    addView(text(describeCachedItem(table, item), 14).apply { setPadding(0, 10, 0, 10) })
                }
            }
        }
        setContentView(ScrollView(this).apply { addView(root) })
    }

    private fun renderRequestsList() {
        rememberNavigation(ScreenState.REQUEST_LIST)
        val page = screenPage("So'rovlar Ro'yxati")
        val body = page.findViewWithTag<LinearLayout>("body")
        val requests = db.rows("requests", "id DESC")
        val filtered = mutableListOf<JSONObject>()
        for (i in 0 until requests.length()) {
            val req = requests.getJSONObject(i)
            if (requestFilter != "all" && req.optString("state") != requestFilter) continue
            filtered += req
        }

        body.addView(row {
            addView(primaryButton("+ Yangi") {
                requestPartnerId = 0L
                requestPartnerName = ""
                requestNote = ""
                requestProductSearchQuery = ""
                requestCart.clear()
                renderRequestForm()
            }.apply {
                layoutParams = LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                    setMargins(0, 0, dp(10), 0)
                }
            })
            val filterSpinner = Spinner(this@MainActivity).apply {
                val options = listOf("Kutilmoqda", "Bajarildi", "Bekor qilingan", "Barchasi")
                adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, options)
                setSelection(
                    when (requestFilter) {
                        "done" -> 1
                        "cancel" -> 2
                        "all" -> 3
                        else -> 0
                    }
                )
                layoutParams = LinearLayout.LayoutParams(dp(140), dp(46))
                onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                    override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                        val next = when (position) {
                            1 -> "done"
                            2 -> "cancel"
                            3 -> "all"
                            else -> "draft"
                        }
                        if (next != requestFilter) {
                            requestFilter = next
                            renderRequestsList()
                        }
                    }
                    override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
                }
            }
            addView(filterSpinner)
        })

        if (filtered.isEmpty()) {
            body.addView(emptyCard("Ushbu holatda hech qanday so'rovlar topilmadi."))
        } else {
            filtered.forEach { req ->
                body.addView(requestSummaryCard(req))
            }
        }
        setContentView(page)
    }

    private fun requestSummaryCard(req: JSONObject): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(10), strokeColor = "#bfdbfe")
            setPadding(dp(14), dp(14), dp(14), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(12)) }
            setOnClickListener { renderRequestDetails(req, resetDraft = true) }

            addView(row {
                addView(text(req.optString("name"), 13, bold = true).apply {
                    setTextColor(color("#64748b"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(navBadge(requestStateLabel(req.optString("state")), requestStateBg(req.optString("state")), requestStateFg(req.optString("state"))))
            })
            addView(text(req.optString("partner_name").ifBlank { "Mijozsiz" }, 16, bold = true).apply {
                setTextColor(color("#1f2937"))
                setPadding(0, dp(6), 0, 0)
            })
            req.optString("date").takeIf { it.isNotBlank() }?.let { date ->
                addView(text(date, 12).apply {
                    setTextColor(color("#64748b"))
                    setPadding(0, dp(8), 0, 0)
                })
            }
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = rounded("#f8fafc", dp(8), strokeColor = "#e2e8f0")
                setPadding(dp(10), dp(10), dp(10), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(10), 0, 0) }
                addView(text("Jami Summa:", 14, bold = true).apply {
                    setTextColor(color("#475569"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(text("${formatAmount(req.optDouble("total_amount"))} so'm", 16, bold = true).apply {
                    setTextColor(color("#1e40af"))
                })
            })
        }
    }

    private fun loadActiveRequestDraft(req: JSONObject) {
        activeRequestId = req.optLong("id")
        activeRequestName = req.optString("name")
        activeRequestPartnerId = req.optLong("partner_id")
        activeRequestPartnerName = req.optString("partner_name")
        activeRequestDate = req.optString("date")
        activeRequestState = req.optString("state").ifBlank { "draft" }
        activeRequestNotes = req.optString("notes")
        activeRequestDraftLines.clear()
        val lines = req.optJSONArray("lines") ?: JSONArray()
        for (i in 0 until lines.length()) {
            val line = lines.getJSONObject(i)
            activeRequestDraftLines += RequestEditLine(
                productId = line.optLong("product_id"),
                productName = line.optString("product_name"),
                qty = line.optDouble("qty").toInt(),
                price = line.optDouble("price"),
                imageUrl = line.optString("image_url")
            )
        }
    }

    private fun activeRequestTotal(): Double {
        return activeRequestDraftLines.sumOf { it.qty * it.price }
    }

    private fun renderRequestForm() {
        rememberNavigation(ScreenState.REQUEST_FORM)
        val page = screenPage("Yangi So'rov")
        val body = page.findViewWithTag<LinearLayout>("body")
        val products = db.rows("products", "name ASC")
        lateinit var totalTextView: TextView
        lateinit var saveButton: Button
        val refreshTotals = {
            totalTextView.text = "Jami: ${formatAmount(requestCartTotal())} so'm"
            saveButton.text = "SO'ROVNI SAQLASH (${formatAmount(requestCartTotal())} so'm)"
        }
        val statusText = text("", 13).apply { setTextColor(color("#dc2626")) }

        body.addView(card {
            addView(label("Mijoz"))
            addView(Button(this@MainActivity).apply {
                text = if (requestPartnerId > 0) requestPartnerName else "-- Mijozni tanlang (Majburiy) --"
                isAllCaps = false
                textSize = 15f
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                setTextColor(color(if (requestPartnerId > 0) "#111827" else "#9ca3af"))
                background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
                setPadding(dp(12), 0, dp(12), 0)
                setOnClickListener { openRequestClientPicker() }
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(54))
            })
            addView(text("Barcha Mahsulotlar", 16, bold = true).apply {
                setTextColor(color("#374151"))
                setPadding(0, dp(20), 0, dp(8))
            })
            addView(EditText(this@MainActivity).apply {
                hint = "Mahsulot izlash..."
                setText(requestProductSearchQuery)
                background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
                setPadding(dp(12), dp(12), dp(12), dp(12))
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        val next = s?.toString().orEmpty()
                        if (next != requestProductSearchQuery) {
                            requestProductSearchQuery = next
                            renderRequestForm()
                        }
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
            })
        })

        val grid = GridLayout(this).apply {
            columnCount = 2
            useDefaultMargins = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        for (i in 0 until products.length()) {
            val product = products.getJSONObject(i)
            if (requestProductSearchQuery.isNotBlank() && !product.optString("name").contains(requestProductSearchQuery, ignoreCase = true)) {
                continue
            }
            grid.addView(requestProductCard(product, refreshTotals))
        }
        if (grid.childCount == 0) {
            body.addView(emptyCard("Qidiruv bo'yicha mahsulot topilmadi."))
        } else {
            body.addView(grid)
        }

        body.addView(card {
            addView(label("Umumiy Izoh"))
            addView(EditText(this@MainActivity).apply {
                hint = "Aloxida talab bo'lsa..."
                setText(requestNote)
                minLines = 4
                gravity = Gravity.TOP or Gravity.START
                background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
                setPadding(dp(12), dp(12), dp(12), dp(12))
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        requestNote = s?.toString().orEmpty()
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
            })
        }.apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(14), 0, 0) }
        })

        totalTextView = text("Jami: ${formatAmount(requestCartTotal())} so'm", 16, bold = true).apply {
            setTextColor(color("#059669"))
            gravity = Gravity.END
            setPadding(0, dp(16), 0, dp(10))
        }
        body.addView(totalTextView)
        body.addView(statusText)
        saveButton = Button(this).apply {
            text = "SO'ROVNI SAQLASH (${formatAmount(requestCartTotal())} so'm)"
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = rounded("#10b981", dp(8))
            setOnClickListener {
                if (requestPartnerId <= 0L) {
                    statusText.text = "Iltimos mijozni tanlang."
                    return@setOnClickListener
                }
                val validLines = requestCart.values.filter { it.qty > 0 }
                if (validLines.isEmpty() && requestNote.isBlank()) {
                    statusText.text = "Iltimos mahsulot tanlang yoki izoh kiriting."
                    return@setOnClickListener
                }
                if (session.token.isBlank()) {
                    statusText.text = "So'rov saqlash uchun online login kerak."
                    return@setOnClickListener
                }
                statusText.text = "Saqlanmoqda..."
                Thread {
                    val error = try {
                        val linePayload = JSONArray()
                        validLines.forEach { line ->
                            linePayload.put(
                                JSONObject()
                                    .put("product_id", line.productId)
                                    .put("qty", line.qty)
                                    .put("price", line.price)
                            )
                        }
                        repository.createRequest(requestPartnerId, linePayload, requestNote)
                        null
                    } catch (e: Exception) {
                        e.message ?: "Tarmoq xatosi"
                    }
                    runOnUiThread {
                        if (error == null) {
                            requestPartnerId = 0L
                            requestPartnerName = ""
                            requestNote = ""
                            requestProductSearchQuery = ""
                            requestCart.clear()
                            renderRequestsList()
                        } else {
                            statusText.text = error
                        }
                    }
                }.start()
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(56)
            )
        }
        body.addView(saveButton)
        setContentView(page)
    }

    private fun openRequestClientPicker() {
        val clients = db.rows("clients", "updated_at DESC")
        val listContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val searchInput = EditText(this).apply {
            hint = "Mijozni qidirish..."
            setSingleLine(true)
            textSize = 15f
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        var pickerDialog: AlertDialog? = null
        fun renderList(query: String) {
            listContainer.removeAllViews()
            var count = 0
            for (i in 0 until clients.length()) {
                val client = clients.getJSONObject(i)
                if (client.optLong("id") == 0L) continue
                val haystack = "${client.optString("name")} ${client.optString("phone")}"
                if (query.isNotBlank() && !haystack.contains(query, ignoreCase = true)) continue
                count += 1
                listContainer.addView(kirimPickerOption(
                    client.optString("name"),
                    "Qarz: ${formatAmount(client.optDouble("total_due"))} so'm",
                    "#dc2626",
                    "#ffffff"
                ) {
                    requestPartnerId = client.optLong("id")
                    requestPartnerName = client.optString("name")
                    pickerDialog?.dismiss()
                    renderRequestForm()
                })
            }
            if (count == 0) {
                listContainer.addView(emptyCard("Mijoz topilmadi."))
            }
        }
        searchInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                renderList(s?.toString().orEmpty())
            }
            override fun afterTextChanged(s: Editable?) = Unit
        })
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(12))
            addView(text("Mijoz Tanlash", 20, bold = true).apply { setTextColor(Color.BLACK) })
            addView(searchInput.apply { setPadding(dp(12), dp(10), dp(12), dp(10)) })
            addView(ScrollView(this@MainActivity).apply {
                addView(listContainer)
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(420)
                ).apply { setMargins(0, dp(12), 0, 0) }
            })
        }
        pickerDialog = AlertDialog.Builder(this)
            .setView(content)
            .setNegativeButton("Yopish", null)
            .create()
        renderList("")
        pickerDialog.show()
    }

    private fun requestProductCard(product: JSONObject, onCartChanged: () -> Unit): LinearLayout {
        val productId = product.optLong("product_id")
        val line = requestCart[productId]
        val cardWidth = ((resources.displayMetrics.widthPixels - dp(42)) / 2).coerceAtLeast(dp(154))
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(if (line != null) "#eff6ff" else "#ffffff", dp(12), strokeColor = if (line != null) "#2563eb" else "#e5e7eb")
            setPadding(dp(10), dp(10), dp(10), dp(10))
            layoutParams = GridLayout.LayoutParams().apply {
                width = cardWidth
                height = GridLayout.LayoutParams.WRAP_CONTENT
                setMargins(dp(4), dp(4), dp(4), dp(10))
            }
            addView(View(this@MainActivity).apply {
                background = rounded("#eef2ff", dp(12))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(86)
                ).apply { setMargins(0, 0, 0, dp(10)) }
            })
            addView(text(product.optString("name"), 14, bold = true).apply {
                setTextColor(color("#0f172a"))
                maxLines = 2
            })
            addView(text("${formatAmount(product.optDouble("sale_price", product.optDouble("price")))} UZS", 13, bold = true).apply {
                setTextColor(color("#059669"))
                setPadding(0, dp(6), 0, dp(8))
            })
            addView(requestQuantityEditor(product, onCartChanged))
        }
    }

    private fun requestQuantityEditor(product: JSONObject, onCartChanged: () -> Unit): LinearLayout {
        val productId = product.optLong("product_id")
        val current = requestCart[productId]?.qty ?: 0
        fun setRequestQty(qty: Int) {
            if (qty <= 0) {
                requestCart.remove(productId)
                return
            }
            val existing = requestCart[productId]
            if (existing != null) {
                requestCart[productId] = existing.copy(qty = qty, price = product.optDouble("sale_price", product.optDouble("price")))
            } else {
                requestCart[productId] = RequestDraftLine(
                    productId = productId,
                    name = product.optString("name"),
                    qty = qty,
                    price = product.optDouble("sale_price", product.optDouble("price")),
                )
            }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded("#ffffff", dp(10), strokeColor = "#cbd5e1")
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(48)
            )
            val qtyField = EditText(this@MainActivity)
            val removeButton = TextView(this@MainActivity)
            removeButton.apply {
                text = if (current <= 1) "x" else "-"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color("#ef4444"))
                background = rounded("#fff1f2", dp(8), strokeColor = "#fecdd3")
                setOnClickListener {
                    val latest = requestCart[productId]?.qty ?: 0
                    if (latest <= 1) {
                        requestCart.remove(productId)
                        qtyField.setText("")
                        text = "x"
                    } else {
                        setRequestQty(latest - 1)
                        qtyField.setText((latest - 1).toString())
                        qtyField.setSelection(qtyField.text.length)
                        text = if (latest - 1 <= 1) "x" else "-"
                    }
                    onCartChanged()
                }
                layoutParams = LinearLayout.LayoutParams(dp(42), dp(38)).apply {
                    setMargins(dp(3), dp(5), dp(4), dp(5))
                }
            }
            addView(removeButton)
            qtyField.apply {
                setText(if (current == 0) "" else current.toString())
                textSize = 15f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                inputType = InputType.TYPE_CLASS_NUMBER
                setSingleLine(true)
                background = rounded("#f8fafc", dp(8), strokeColor = "#dbe3ef")
                setTextColor(color("#0f172a"))
                includeFontPadding = false
                setPadding(0, dp(2), 0, 0)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        val qty = s?.toString()?.toIntOrNull() ?: 0
                        setRequestQty(qty)
                        removeButton.text = if (qty <= 1) "x" else "-"
                        onCartChanged()
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
                layoutParams = LinearLayout.LayoutParams(0, dp(38), 1f).apply {
                    setMargins(0, dp(5), 0, dp(5))
                }
            }
            addView(qtyField)
            addView(TextView(this@MainActivity).apply {
                text = "+"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
                background = rounded("#2563eb", dp(8))
                setOnClickListener {
                    val next = (requestCart[productId]?.qty ?: 0) + 1
                    setRequestQty(next)
                    qtyField.setText(next.toString())
                    qtyField.setSelection(qtyField.text.length)
                    removeButton.text = if (next <= 1) "x" else "-"
                    onCartChanged()
                }
                layoutParams = LinearLayout.LayoutParams(dp(42), dp(38)).apply {
                    setMargins(dp(4), dp(5), dp(3), dp(5))
                }
            })
        }
    }

    private fun renderRequestDetails(req: JSONObject, resetDraft: Boolean = true) {
        if (resetDraft || activeRequestId != req.optLong("id") || activeRequestDraftLines.isEmpty()) {
            loadActiveRequestDraft(req)
        } else {
            activeRequestId = req.optLong("id")
            activeRequestName = req.optString("name")
            activeRequestPartnerId = req.optLong("partner_id")
            activeRequestPartnerName = req.optString("partner_name")
            activeRequestDate = req.optString("date")
            activeRequestState = req.optString("state").ifBlank { "draft" }
            activeRequestNotes = req.optString("notes")
        }
        rememberNavigation(ScreenState.REQUEST_DETAILS)
        val page = screenPage("So'rov Tafsilotlari")
        val body = page.findViewWithTag<LinearLayout>("body")
        body.addView(card {
            addView(row {
                addView(text(activeRequestName, 18, bold = true).apply {
                    setTextColor(color("#111827"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(navBadge(requestStateLabel(activeRequestState), requestStateBg(activeRequestState), requestStateFg(activeRequestState)))
            })
            addView(text(activeRequestPartnerName.ifBlank { "Mijozsiz" }, 15, bold = true).apply {
                setTextColor(color("#374151"))
                setPadding(0, dp(10), 0, 0)
            })
            activeRequestDate.takeIf { it.isNotBlank() }?.let { date ->
                addView(text(date, 14).apply {
                    setTextColor(color("#6b7280"))
                    setPadding(0, dp(8), 0, 0)
                })
            }
            activeRequestNotes.takeIf { it.isNotBlank() }?.let { note ->
                addView(text("Izoh: $note", 14).apply {
                    setTextColor(color("#4b5563"))
                    background = rounded("#f9fafb", dp(6), strokeColor = "#e5e7eb")
                    setPadding(dp(10), dp(10), dp(10), dp(10))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, dp(10), 0, 0) }
                })
            }
        })

        lateinit var totalTextView: TextView
        lateinit var saveButton: Button
        lateinit var checkoutButton: Button
        val refreshTotals = {
            totalTextView.text = "${formatAmount(activeRequestTotal())} so'm"
            saveButton.text = "SAQLASH"
            checkoutButton.text = "XARID QILISH"
        }

        body.addView(card {
            addView(text("Buyurtma qilingan mahsulotlar (${activeRequestDraftLines.size})", 15, bold = true).apply {
                setTextColor(color("#475569"))
            })
            if (activeRequestDraftLines.isEmpty()) {
                addView(emptyCard("Mahsulot qo'shilmagan."))
            } else {
                for (line in activeRequestDraftLines.toList()) {
                    if (activeRequestState == "draft") {
                        val rowLayout = LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.HORIZONTAL
                            gravity = Gravity.CENTER_VERTICAL
                            setPadding(0, dp(10), 0, dp(10))
                        }
                        val subtotalText = text("${formatAmount(line.qty * line.price)} so'm", 14, bold = true).apply {
                            setTextColor(color("#059669"))
                            gravity = Gravity.END
                        }
                        rowLayout.addView(text(line.productName, 14, bold = true).apply {
                            setTextColor(color("#1e293b"))
                            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.25f)
                        })
                        rowLayout.addView(smallNumberInput(formatAmount(line.qty.toDouble())) { next ->
                            line.qty = parseAmount(next).toInt()
                            subtotalText.text = "${formatAmount(line.qty * line.price)} so'm"
                            refreshTotals()
                        }.apply {
                            gravity = Gravity.CENTER
                            inputType = InputType.TYPE_CLASS_NUMBER
                            layoutParams = LinearLayout.LayoutParams(dp(74), dp(40)).apply {
                                setMargins(dp(8), 0, dp(8), 0)
                            }
                        })
                        rowLayout.addView(smallNumberInput(formatAmount(line.price)) { next ->
                            line.price = parseAmount(next)
                            subtotalText.text = "${formatAmount(line.qty * line.price)} so'm"
                            refreshTotals()
                        }.apply {
                            layoutParams = LinearLayout.LayoutParams(dp(92), dp(40)).apply {
                                setMargins(0, 0, dp(8), 0)
                            }
                        })
                        rowLayout.addView(subtotalText.apply {
                            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.85f)
                        })
                        rowLayout.addView(text("🗑", 16, bold = true).apply {
                            setTextColor(color("#ef4444"))
                            gravity = Gravity.CENTER
                            setPadding(dp(8), dp(8), dp(8), dp(8))
                            setOnClickListener {
                                activeRequestDraftLines.removeAll { it.productId == line.productId }
                                renderRequestDetails(req, resetDraft = false)
                            }
                        })
                        addView(rowLayout)
                    } else {
                        addView(row {
                            addView(text(line.productName, 14, bold = true).apply {
                                setTextColor(color("#1e293b"))
                                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                            })
                            addView(text("${formatAmount(line.qty.toDouble())} ta x ${formatAmount(line.price)} so'm", 13).apply {
                                setTextColor(color("#64748b"))
                            })
                            addView(text("${formatAmount(line.qty * line.price)} so'm", 14, bold = true).apply {
                                setTextColor(color("#059669"))
                                setPadding(dp(10), 0, 0, 0)
                            })
                        })
                    }
                }
            }

            if (activeRequestState == "draft") {
                addView(TextView(this@MainActivity).apply {
                    text = "+ Mahsulot qo'shish"
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    gravity = Gravity.CENTER
                    setTextColor(color("#3b82f6"))
                    background = rounded("#f8fbff", dp(8), strokeColor = "#60a5fa")
                    setPadding(dp(12), dp(12), dp(12), dp(12))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, dp(10), 0, dp(4)) }
                    setOnClickListener { openRequestAddProductDialog(req) }
                })
            }

            addView(row {
                addView(text("JAMI SUMMA:", 16, bold = true).apply {
                    setTextColor(color("#1e3a8a"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                totalTextView = text("${formatAmount(activeRequestTotal())} so'm", 18, bold = true).apply {
                    setTextColor(color("#dc2626"))
                }
                addView(totalTextView)
            }.apply {
                setPadding(0, dp(8), 0, 0)
            })
        }.apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(12), 0, 0) }
        })

        status = text("", 13).apply {
            setTextColor(color("#dc2626"))
            setPadding(0, dp(10), 0, 0)
        }
        body.addView(status)

        if (activeRequestState == "draft") {
            body.addView(row {
                addView(Button(this@MainActivity).apply {
                    text = "SAQLASH"
                    textSize = 16f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#f59e0b", dp(8))
                    setOnClickListener { saveActiveRequestEdits() }
                    layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply { setMargins(0, 0, dp(6), 0) }
                }.also { saveButton = it })
                addView(Button(this@MainActivity).apply {
                    text = "XARID QILISH"
                    textSize = 16f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#10b981", dp(8))
                    setOnClickListener { fulfillRequestIntoPos(req) }
                    layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply { setMargins(dp(6), 0, 0, 0) }
                }.also { checkoutButton = it })
            })
        } else {
            saveButton = Button(this@MainActivity)
            checkoutButton = Button(this@MainActivity)
        }

        if (activeRequestState != "draft") {
            body.addView(row {
                addView(Button(this@MainActivity).apply {
                    text = "XARID QILISH"
                    textSize = 16f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#10b981", dp(8))
                    setOnClickListener { fulfillRequestIntoPos(req) }
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        dp(52)
                    )
                })
            })
        }

        setContentView(page)
    }

    private fun openRequestAddProductDialog(req: JSONObject) {
        if (activeRequestId != req.optLong("id") || activeRequestDraftLines.isEmpty()) {
            loadActiveRequestDraft(req)
        }
        val products = db.rows("products", "name ASC")
        val listContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val searchInput = EditText(this).apply {
            hint = "Mahsulot izlash..."
            setSingleLine(true)
            textSize = 15f
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        var pickerDialog: AlertDialog? = null

        fun addProduct(product: JSONObject) {
            val productId = product.optLong("product_id")
            if (productId <= 0L) return
            val existing = activeRequestDraftLines.firstOrNull { it.productId == productId }
            if (existing != null) {
                existing.qty += 1
            } else {
                activeRequestDraftLines += RequestEditLine(
                    productId = productId,
                    productName = product.optString("name"),
                    qty = 1,
                    price = product.optDouble("sale_price", product.optDouble("price")),
                    imageUrl = product.optString("image_url")
                )
            }
            pickerDialog?.dismiss()
            renderRequestDetails(req, resetDraft = false)
        }

        fun renderList(query: String) {
            listContainer.removeAllViews()
            var count = 0
            for (i in 0 until products.length()) {
                val product = products.getJSONObject(i)
                if (query.isNotBlank() && !product.optString("name").contains(query, ignoreCase = true)) continue
                count += 1
                val productId = product.optLong("product_id")
                val existingQty = activeRequestDraftLines.firstOrNull { it.productId == productId }?.qty ?: 0
                listContainer.addView(LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    background = rounded("#ffffff", dp(10), strokeColor = "#dbe3ef")
                    setPadding(dp(14), dp(12), dp(14), dp(12))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, 0, 0, dp(10)) }
                    setOnClickListener { addProduct(product) }
                    addView(row {
                        addView(text(product.optString("name"), 15, bold = true).apply {
                            setTextColor(color("#111827"))
                            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                        })
                        addView(text("${formatAmount(product.optDouble("sale_price", product.optDouble("price")))} so'm", 14, bold = true).apply {
                            setTextColor(color("#059669"))
                        })
                    })
                    addView(text(if (existingQty > 0) "Tanlangan: ${formatAmount(existingQty.toDouble())} ta" else "Qo'shish uchun bosing", 13).apply {
                        setTextColor(color(if (existingQty > 0) "#2563eb" else "#64748b"))
                        setPadding(0, dp(6), 0, 0)
                    })
                })
            }
            if (count == 0) {
                listContainer.addView(emptyCard("Mahsulot topilmadi."))
            }
        }

        searchInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                renderList(s?.toString().orEmpty())
            }
            override fun afterTextChanged(s: Editable?) = Unit
        })

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(12))
            addView(text("Mahsulot qo'shish", 20, bold = true).apply { setTextColor(Color.BLACK) })
            addView(searchInput)
            addView(ScrollView(this@MainActivity).apply {
                addView(listContainer)
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(420)
                ).apply { setMargins(0, dp(12), 0, 0) }
            })
        }

        pickerDialog = AlertDialog.Builder(this)
            .setView(content)
            .setNegativeButton("Yopish", null)
            .create()
        renderList("")
        pickerDialog.show()
    }

    private fun saveActiveRequestEdits(onSuccess: (() -> Unit)? = null) {
        if (activeRequestId <= 0L) {
            if (::status.isInitialized) status.text = "So'rov topilmadi."
            return
        }
        if (session.token.isBlank()) {
            if (::status.isInitialized) status.text = "So'rovni saqlash uchun online login kerak."
            return
        }
        val validLines = activeRequestDraftLines.filter { it.qty > 0 && it.price >= 0.0 }
        if (validLines.isEmpty()) {
            if (::status.isInitialized) status.text = "Kamida bitta mahsulot qoldiring."
            return
        }
        if (::status.isInitialized) status.text = "Saqlanmoqda..."
        Thread {
            val error = try {
                val linePayload = JSONArray()
                validLines.forEach { line ->
                    linePayload.put(
                        JSONObject()
                            .put("product_id", line.productId)
                            .put("qty", line.qty)
                            .put("price", line.price)
                    )
                }
                repository.updateRequest(activeRequestId, linePayload)
                null
            } catch (e: Exception) {
                e.message ?: "Tarmoq xatosi"
            }
            runOnUiThread {
                if (error == null) {
                    activeRequestDraftLines.removeAll { it.qty <= 0 }
                    val updated = db.rows("requests", "id DESC").let { rows ->
                        (0 until rows.length())
                            .map { rows.getJSONObject(it) }
                            .firstOrNull { it.optLong("id") == activeRequestId }
                    }
                    if (updated != null) {
                        loadActiveRequestDraft(updated)
                    }
                    if (onSuccess != null) {
                        onSuccess()
                    } else if (updated != null) {
                        status.text = "Saqlandi."
                        renderRequestDetails(updated, resetDraft = true)
                    } else {
                        renderRequestsList()
                    }
                } else if (::status.isInitialized) {
                    status.text = error
                }
            }
        }.start()
    }

    private fun updateRequestState(requestId: Long, nextState: String) {
        if (session.token.isBlank()) {
            if (::status.isInitialized) status.text = "Online login kerak."
            return
        }
        Thread {
            val error = try {
                repository.updateRequestState(requestId, nextState)
                null
            } catch (e: Exception) {
                e.message ?: "Tarmoq xatosi"
            }
            runOnUiThread {
                if (error == null) {
                    renderRequestsList()
                } else if (::status.isInitialized) {
                    status.text = error
                }
            }
        }.start()
    }

    private fun fulfillRequestIntoPos(req: JSONObject) {
        cart.clear()
        if (activeRequestId == req.optLong("id") && activeRequestDraftLines.isNotEmpty()) {
            activeRequestDraftLines.filter { it.qty > 0 }.forEach { line ->
                cart[line.productId] = CartLine(
                    productId = line.productId,
                    name = line.productName,
                    qty = line.qty.toDouble(),
                    price = line.price
                )
            }
        } else {
            val lines = req.optJSONArray("lines") ?: JSONArray()
            for (i in 0 until lines.length()) {
                val line = lines.getJSONObject(i)
                val productId = line.optLong("product_id")
                if (productId <= 0L) continue
                cart[productId] = CartLine(
                    productId = productId,
                    name = line.optString("product_name"),
                    qty = line.optDouble("qty"),
                    price = line.optDouble("price")
                )
            }
        }
        if (cart.isEmpty()) {
            if (::status.isInitialized) status.text = "Kamida bitta mahsulot qoldiring."
            return
        }
        selectedClientId = req.optLong("partner_id")
        selectedClientName = req.optString("partner_name").ifBlank { "Naqt savdo" }
        sourceRequestId = req.optLong("id")
        renderCheckout()
    }

    private fun requestCartTotal(): Double {
        return requestCart.values.sumOf { it.qty * it.price }
    }

    private fun renderTripList() {
        rememberNavigation(ScreenState.TRIP_LIST)
        val page = screenPage("Mahsulot Yuklash")
        val body = page.findViewWithTag<LinearLayout>("body")
        val trips = db.rows("trips", "id DESC")

        body.addView(row {
            addView(text("Mahsulot Yuklash Tarixi", 18, bold = true).apply {
                setTextColor(color("#1e3a8a"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            })
            addView(primaryButton("+ Yangi Yuklash") { renderTripForm() }.apply {
                layoutParams = LinearLayout.LayoutParams(dp(132), dp(42))
            })
        })

        if (trips.length() == 0) {
            body.addView(emptyCard("Hozircha hech qanday mahsulot yuklanmagan."))
        } else {
            for (i in 0 until trips.length()) {
                body.addView(tripSummaryCard(trips.getJSONObject(i)))
            }
        }

        setContentView(page)
    }

    private fun tripSummaryCard(trip: JSONObject): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(10), strokeColor = "#bbf7d0")
            setPadding(dp(14), dp(14), dp(14), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(14)) }
            setOnClickListener { renderTripDetails(trip) }

            addView(row {
                addView(text(trip.optString("name"), 16, bold = true).apply {
                    setTextColor(Color.BLACK)
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(navBadge(tripStateLabel(trip.optString("state")), tripStateBg(trip.optString("state")), tripStateFg(trip.optString("state"))))
            })
            addView(text(trip.optString("agent_name"), 14, bold = true).apply {
                setTextColor(color("#334155"))
                setPadding(0, dp(4), 0, 0)
            })
            addView(text(formatTripDateLabel(trip.optString("date")), 13).apply {
                setTextColor(color("#64748b"))
                setPadding(0, dp(6), 0, dp(12))
            })
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = rounded("#f8fafc", dp(8), strokeColor = "#dbe3ef")
                setPadding(dp(10), dp(12), dp(10), dp(12))
                addView(text("Jami:", 14, bold = true).apply {
                    setTextColor(color("#475569"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(text("${formatAmount(trip.optDouble("total_cost"))} so'm", 16, bold = true).apply {
                    setTextColor(color("#059669"))
                })
            })
        }
    }

    private fun renderTripDetails(trip: JSONObject) {
        activeTripId = trip.optLong("id")
        rememberNavigation(ScreenState.TRIP_DETAILS)
        val page = screenPage("Yuklash Tafsilotlari")
        val body = page.findViewWithTag<LinearLayout>("body")
        val lines = trip.optJSONArray("lines") ?: JSONArray()

        body.addView(row {
            addView(secondaryButton("← Ortga") { renderTripList() }.apply {
                layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f)
            })
            addView(navBadge(tripStateLabel(trip.optString("state")), tripStateBg(trip.optString("state")), tripStateFg(trip.optString("state"))))
        })

        body.addView(card {
            addView(text(trip.optString("name"), 18, bold = true).apply {
                setTextColor(Color.BLACK)
            })
            addView(text(trip.optString("agent_name"), 15, bold = true).apply {
                setTextColor(color("#334155"))
                setPadding(0, dp(10), 0, 0)
            })
            addView(text(formatTripDateLabel(trip.optString("date")), 14).apply {
                setTextColor(color("#64748b"))
                setPadding(0, dp(8), 0, 0)
            })
            if (trip.optString("note").isNotBlank()) {
                addView(text("Izoh: ${trip.optString("note")}", 13).apply {
                    setTextColor(color("#475569"))
                    background = rounded("#f8fafc", dp(8))
                    setPadding(dp(10), dp(10), dp(10), dp(10))
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT
                    ).apply { setMargins(0, dp(10), 0, 0) }
                })
            }
        })

        body.addView(card {
            addView(row {
                addView(text("MAHSULOT", 11, bold = true).apply {
                    setTextColor(color("#334155"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.8f)
                })
                addView(text("MIQDOR", 11, bold = true).apply {
                    setTextColor(color("#334155"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.7f)
                })
                addView(text("NARXI", 11, bold = true).apply {
                    setTextColor(color("#334155"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.8f)
                })
                addView(text("SUMMASI", 11, bold = true).apply {
                    setTextColor(color("#334155"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.9f)
                })
            })
            addView(View(this@MainActivity).apply {
                setBackgroundColor(color("#e5e7eb"))
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(1)).apply {
                    setMargins(0, dp(8), 0, dp(8))
                }
            })
            for (i in 0 until lines.length()) {
                addView(tripDetailRow(lines.getJSONObject(i)))
            }
            addView(View(this@MainActivity).apply {
                setBackgroundColor(color("#10b981"))
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(1)).apply {
                    setMargins(0, dp(8), 0, dp(8))
                }
            })
            addView(row {
                addView(text("JAMI:", 15, bold = true).apply {
                    setTextColor(color("#065f46"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 3.3f)
                })
                addView(text("${formatAmount(trip.optDouble("total_cost"))} so'm", 16, bold = true).apply {
                    setTextColor(color("#047857"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.9f)
                })
            })
        })

        setContentView(page)
    }

    private fun tripDetailRow(line: JSONObject): LinearLayout {
        return row {
            addView(text(line.optString("product_name"), 14).apply {
                setTextColor(Color.BLACK)
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.8f)
            })
            addView(text(formatAmount(line.optDouble("qty")), 14, bold = true).apply {
                setTextColor(color("#1e3a8a"))
                gravity = Gravity.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.7f)
            })
            addView(text(formatAmount(line.optDouble("price")), 13).apply {
                setTextColor(color("#64748b"))
                gravity = Gravity.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.8f)
            })
            addView(text(formatAmount(line.optDouble("subtotal")), 14, bold = true).apply {
                setTextColor(color("#059669"))
                gravity = Gravity.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.9f)
            })
        }
    }

    private fun renderTripForm() {
        rememberNavigation(ScreenState.TRIP_FORM)
        if (tripDate.isBlank()) {
            tripDate = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
        }
        val page = screenPage("Yangi Yuklash")
        val body = page.findViewWithTag<LinearLayout>("body")
        val scrollView = page.findViewWithTag<ScrollView>("scroll_container")
        val products = db.rows("products", "name ASC")
        val agent = db.rows("agent", "id DESC").optJSONObject(0)
        val statusText = text("", 13).apply { setTextColor(color("#dc2626")) }
        lateinit var totalTextView: TextView
        lateinit var saveButton: Button
        val refreshTotals = {
            totalTextView.text = "Jami: ${formatAmount(tripCartTotal())} so'm"
            saveButton.text = "MAHSULOTNI YUKLASH (${formatAmount(tripCartTotal())} so'm)"
        }

        body.addView(card {
            addView(row {
                addView(text("Yangi Yuklash", 18, bold = true).apply {
                    setTextColor(color("#1e3a8a"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(secondaryButton("Bekor") {
                    tripCart.clear()
                    tripNote = ""
                    tripProductSearchQuery = ""
                    renderTripList()
                }.apply {
                    layoutParams = LinearLayout.LayoutParams(dp(92), dp(40))
                })
            })
            addView(label("Sana"))
            addView(dateField(tripDate) { value ->
                tripDate = value
                renderTripForm()
            })
            addView(label("Agent").apply { setPadding(0, dp(12), 0, dp(4)) })
            addView(text(agent?.optString("name").orEmpty().ifBlank { "-" }, 14, bold = true).apply {
                setTextColor(color("#334155"))
                background = rounded("#f8fafc", dp(8), strokeColor = "#dbe3ef")
                setPadding(dp(12), dp(12), dp(12), dp(12))
            })
            addView(label("Taminotchi").apply { setPadding(0, dp(12), 0, dp(4)) })
            addView(text(agent?.optString("default_taminotchi_name").orEmpty().ifBlank { "Biriktirilmagan" }, 14).apply {
                setTextColor(color("#334155"))
                background = rounded("#f8fafc", dp(8), strokeColor = "#dbe3ef")
                setPadding(dp(12), dp(12), dp(12), dp(12))
            })
            addView(label("Izoh").apply { setPadding(0, dp(12), 0, dp(4)) })
            addView(EditText(this@MainActivity).apply {
                setText(tripNote)
                minLines = 2
                textSize = 14f
                setTextColor(color("#0f172a"))
                gravity = Gravity.TOP or Gravity.START
                background = rounded("#ffffff", dp(8), strokeColor = "#dbe3ef")
                setPadding(dp(12), dp(12), dp(12), dp(12))
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        tripNote = s?.toString().orEmpty()
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
            })
        })

        body.setPadding(dp(10), dp(10), dp(10), dp(132))

        body.addView(EditText(this).apply {
            hint = "Mahsulot qidirish..."
            setText(tripProductSearchQuery)
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(12), dp(12), dp(12))
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    val next = s?.toString().orEmpty()
                    if (next != tripProductSearchQuery) {
                        tripProductSearchQuery = next
                        renderTripForm()
                    }
                }
                override fun afterTextChanged(s: Editable?) = Unit
            })
        })

        val grid = GridLayout(this).apply {
            columnCount = 2
            useDefaultMargins = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        for (i in 0 until products.length()) {
            val product = products.getJSONObject(i)
            if (tripProductSearchQuery.isNotBlank() && !product.optString("name").contains(tripProductSearchQuery, ignoreCase = true)) {
                continue
            }
            grid.addView(tripProductCard(product, refreshTotals))
        }
        if (grid.childCount == 0) {
            body.addView(emptyCard("Qidiruv bo'yicha mahsulot topilmadi."))
        } else {
            body.addView(grid)
        }

        totalTextView = text("Jami: ${formatAmount(tripCartTotal())} so'm", 16, bold = true).apply {
            setTextColor(color("#1e3a8a"))
            setPadding(0, 0, 0, dp(6))
            gravity = Gravity.END
        }
        saveButton = primaryButton("MAHSULOTNI YUKLASH (${formatAmount(tripCartTotal())} so'm)") {
            val selectedLines = tripCart.values.filter { it.qty > 0 }
            if (selectedLines.isEmpty()) {
                statusText.text = "Iltimos kamida bitta mahsulot tanlang."
                return@primaryButton
            }
            if (session.token.isBlank()) {
                statusText.text = "Yuklashni saqlash uchun online login kerak."
                return@primaryButton
            }
            openTripConfirmDialog(agent, statusText)
        }.apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(54)
            )
        }
        page.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", 0, strokeColor = "#dbe3ef")
            setPadding(dp(10), dp(10), dp(10), dp(12))
            elevation = dp(3).toFloat()
            addView(totalTextView)
            addView(statusText.apply {
                setPadding(0, 0, 0, dp(8))
            })
            addView(saveButton)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        })

        setContentView(page)
        scrollView?.post {
            scrollView.fullScroll(View.FOCUS_UP)
        }
    }

    private fun tripProductCard(product: JSONObject, onCartChanged: () -> Unit): LinearLayout {
        val productId = product.optLong("product_id")
        val line = tripCart[productId]
        val cardWidth = ((resources.displayMetrics.widthPixels - dp(42)) / 2).coerceAtLeast(dp(154))
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(if (line != null) "#eff6ff" else "#ffffff", dp(12), strokeColor = if (line != null) "#2563eb" else "#e5e7eb")
            setPadding(dp(10), dp(10), dp(10), dp(10))
            layoutParams = GridLayout.LayoutParams().apply {
                width = cardWidth
                height = GridLayout.LayoutParams.WRAP_CONTENT
                setMargins(dp(4), dp(4), dp(4), dp(10))
            }

            addView(View(this@MainActivity).apply {
                background = rounded("#eef2ff", dp(12))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(86)
                ).apply { setMargins(0, 0, 0, dp(10)) }
            })
            addView(text(product.optString("name"), 14, bold = true).apply {
                setTextColor(color("#0f172a"))
                maxLines = 2
            })
            addView(text("${formatAmount(product.optDouble("cost_price"))} so'm", 13, bold = true).apply {
                setTextColor(color("#059669"))
                setPadding(0, dp(6), 0, dp(8))
            })
            addView(tripQuantityEditor(product, onCartChanged))
        }
    }

    private fun tripQuantityEditor(product: JSONObject, onCartChanged: () -> Unit): LinearLayout {
        val productId = product.optLong("product_id")
        val current = tripCart[productId]?.qty ?: 0
        fun setTripQty(product: JSONObject, qty: Int) {
            if (qty <= 0) {
                tripCart.remove(product.optLong("product_id"))
                return
            }
            val productId = product.optLong("product_id")
            val existing = tripCart[productId]
            if (existing != null) {
                tripCart[productId] = existing.copy(qty = qty, price = product.optDouble("cost_price"))
            } else {
                tripCart[productId] = TripDraftLine(
                    productId = productId,
                    name = product.optString("name"),
                    qty = qty,
                    price = product.optDouble("cost_price"),
                )
            }
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded("#ffffff", dp(10), strokeColor = "#cbd5e1")
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(48)
            )
            val quantityField = EditText(this@MainActivity)
            val removeButton = TextView(this@MainActivity)
            removeButton.apply {
                text = if (current <= 1) "x" else "-"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color("#ef4444"))
                background = rounded("#fff1f2", dp(8), strokeColor = "#fecdd3")
                setOnClickListener {
                    val latestQty = tripCart[productId]?.qty ?: 0
                    if (latestQty <= 1) {
                        tripCart.remove(productId)
                        quantityField.setText("")
                        removeButton.text = "x"
                    } else {
                        tripCart[productId] = tripCart[productId]!!.copy(qty = latestQty - 1)
                        quantityField.setText((latestQty - 1).toString())
                        quantityField.setSelection(quantityField.text.length)
                        removeButton.text = if (latestQty - 1 <= 1) "x" else "-"
                    }
                    onCartChanged()
                }
                layoutParams = LinearLayout.LayoutParams(dp(42), dp(38)).apply {
                    setMargins(dp(3), dp(5), dp(4), dp(5))
                }
            }
            addView(removeButton)
            quantityField.apply {
                setText(if (current == 0) "" else current.toString())
                textSize = 15f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                inputType = InputType.TYPE_CLASS_NUMBER
                setSingleLine(true)
                background = rounded("#f8fafc", dp(8), strokeColor = "#dbe3ef")
                setTextColor(color("#0f172a"))
                includeFontPadding = false
                setPadding(0, dp(2), 0, 0)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        val qty = s?.toString()?.toIntOrNull() ?: 0
                        setTripQty(product, qty)
                        removeButton.text = if (qty <= 1) "x" else "-"
                        onCartChanged()
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
                layoutParams = LinearLayout.LayoutParams(0, dp(38), 1f).apply {
                    setMargins(0, dp(5), 0, dp(5))
                }
            }
            addView(quantityField)
            addView(TextView(this@MainActivity).apply {
                text = "+"
                textSize = 17f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(Color.WHITE)
                background = rounded("#2563eb", dp(8))
                setOnClickListener {
                    val next = (tripCart[productId]?.qty ?: 0) + 1
                    setTripQty(product, next)
                    quantityField.setText(next.toString())
                    quantityField.setSelection(quantityField.text.length)
                    removeButton.text = if (next <= 1) "x" else "-"
                    onCartChanged()
                }
                layoutParams = LinearLayout.LayoutParams(dp(42), dp(38)).apply {
                    setMargins(dp(4), dp(5), dp(3), dp(5))
                }
            })
        }
    }

    private fun tripCartTotal(): Double {
        return tripCart.values.sumOf { it.qty * it.price }
    }

    private fun openTripConfirmDialog(agent: JSONObject?, statusText: TextView) {
        val selectedLines = tripCart.values.filter { it.qty > 0 }
        if (selectedLines.isEmpty()) {
            statusText.text = "Iltimos kamida bitta mahsulot tanlang."
            return
        }

        val dialogContent = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(18))
        }
        val rowsContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        lateinit var totalTextView: TextView
        lateinit var confirmButton: Button
        val refreshDialogTotals = {
            totalTextView.text = "JAMI: ${formatAmount(tripCartTotal())} so'm"
            confirmButton.text = "TASDIQLASH"
        }

        val dialog = AlertDialog.Builder(this)
            .setView(ScrollView(this).apply { addView(dialogContent) })
            .create()

        fun addTripConfirmRow(line: TripDraftLine) {
            val rowLayout = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(10), 0, dp(10))
            }
            val subtotalText = text("${formatAmount(line.qty * line.price)}", 14, bold = true).apply {
                setTextColor(color("#0f172a"))
                gravity = Gravity.END
            }
            val deleteButton = text("🗑", 16, bold = true).apply {
                setTextColor(color("#ef4444"))
                gravity = Gravity.CENTER
                setPadding(dp(8), dp(8), dp(8), dp(8))
                setOnClickListener {
                    tripCart.remove(line.productId)
                    rowsContainer.removeView(rowLayout)
                    refreshDialogTotals()
                    if (rowsContainer.childCount == 0) {
                        dialog.dismiss()
                        renderTripForm()
                    }
                }
            }
            rowLayout.addView(text(line.name, 14).apply {
                setTextColor(color("#334155"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.4f)
            })
            rowLayout.addView(smallNumberInput(line.qty.toString()) { next ->
                val qty = next.toIntOrNull() ?: 0
                if (qty <= 0) {
                    tripCart.remove(line.productId)
                    rowsContainer.removeView(rowLayout)
                    refreshDialogTotals()
                    if (rowsContainer.childCount == 0) {
                        dialog.dismiss()
                        renderTripForm()
                    }
                } else {
                    val existing = tripCart[line.productId] ?: return@smallNumberInput
                    tripCart[line.productId] = existing.copy(qty = qty)
                    subtotalText.text = formatAmount(qty * (tripCart[line.productId]?.price ?: existing.price))
                    refreshDialogTotals()
                }
            }.apply {
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(dp(70), dp(36)).apply {
                    setMargins(dp(8), 0, dp(8), 0)
                }
            })
            rowLayout.addView(smallNumberInput(formatAmount(line.price)) { next ->
                val price = parseAmount(next)
                val existing = tripCart[line.productId] ?: return@smallNumberInput
                tripCart[line.productId] = existing.copy(price = price)
                subtotalText.text = formatAmount(existing.qty * price)
                refreshDialogTotals()
            }.apply {
                layoutParams = LinearLayout.LayoutParams(dp(88), dp(36)).apply {
                    setMargins(0, 0, dp(8), 0)
                }
            })
            rowLayout.addView(subtotalText.apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.9f)
            })
            rowLayout.addView(deleteButton)
            rowsContainer.addView(rowLayout)
        }

        dialogContent.addView(row {
            addView(text("Yuklashni Tasdiqlash", 20, bold = true).apply {
                setTextColor(color("#1f2937"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            })
            addView(text("×", 24, bold = true).apply {
                setTextColor(color("#64748b"))
                setOnClickListener {
                    dialog.dismiss()
                    renderTripForm()
                }
            })
        })
        dialogContent.addView(card {
            addView(text("Taminotchi: ${agent?.optString("default_taminotchi_name").orEmpty().ifBlank { "Biriktirilmagan" }}", 15, bold = true).apply {
                setTextColor(color("#334155"))
            })
            addView(text("Agent: ${agent?.optString("name").orEmpty().ifBlank { "-" }}", 14).apply {
                setTextColor(color("#475569"))
                setPadding(0, dp(8), 0, 0)
            })
            addView(text("Sana: $tripDate", 14).apply {
                setTextColor(color("#475569"))
                setPadding(0, dp(6), 0, 0)
            })
        }.apply {
            setPadding(dp(14), dp(14), dp(14), dp(14))
        })
        dialogContent.addView(text("Mahsulotlar", 16, bold = true).apply {
            setTextColor(color("#334155"))
            setPadding(0, dp(16), 0, dp(10))
        })
        dialogContent.addView(row {
            setPadding(0, 0, 0, dp(8))
            addView(text("Mahsulot", 13).apply {
                setTextColor(color("#64748b"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.4f)
            })
            addView(text("Miqdor", 13).apply {
                setTextColor(color("#64748b"))
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(dp(78), LinearLayout.LayoutParams.WRAP_CONTENT)
            })
            addView(text("Kelish Narxi", 13).apply {
                setTextColor(color("#64748b"))
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(dp(96), LinearLayout.LayoutParams.WRAP_CONTENT)
            })
            addView(text("Summasi", 13).apply {
                setTextColor(color("#64748b"))
                gravity = Gravity.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.9f)
            })
            addView(space().apply {
                layoutParams = LinearLayout.LayoutParams(dp(28), 1)
            })
        })
        dialogContent.addView(rowsContainer)
        selectedLines.forEach { addTripConfirmRow(it) }
        totalTextView = text("JAMI: ${formatAmount(tripCartTotal())} so'm", 16, bold = true).apply {
            setTextColor(color("#2563eb"))
            gravity = Gravity.END
            setPadding(0, dp(14), 0, dp(16))
        }
        dialogContent.addView(totalTextView)
        dialogContent.addView(row {
            addView(secondaryButton("Bekor qilish") {
                dialog.dismiss()
                renderTripForm()
            })
            confirmButton = Button(this@MainActivity).apply {
                text = "TASDIQLASH"
                textSize = 15f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.WHITE)
                background = rounded("#10b981", dp(10))
                layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply {
                    setMargins(dp(4), 0, 0, 0)
                }
                setOnClickListener {
                    if (session.token.isBlank()) {
                        statusText.text = "Yuklashni saqlash uchun online login kerak."
                        dialog.dismiss()
                        return@setOnClickListener
                    }
                    val currentLines = tripCart.values.filter { it.qty > 0 }
                    if (currentLines.isEmpty()) {
                        statusText.text = "Iltimos kamida bitta mahsulot tanlang."
                        dialog.dismiss()
                        renderTripForm()
                        return@setOnClickListener
                    }
                    statusText.text = "Saqlanmoqda..."
                    isEnabled = false
                    Thread {
                        val error = try {
                            val linePayload = JSONArray()
                            currentLines.forEach { currentLine ->
                                linePayload.put(
                                    JSONObject()
                                        .put("product_id", currentLine.productId)
                                        .put("qty", currentLine.qty)
                                        .put("price_unit", currentLine.price)
                                )
                            }
                            val supplierId = agent?.optLong("default_taminotchi_id")?.takeIf { it > 0 }
                            repository.createTrip(tripDate, tripNote, linePayload, supplierId)
                            null
                        } catch (e: Exception) {
                            e.message ?: "Tarmoq xatosi"
                        }
                        runOnUiThread {
                            if (error == null) {
                                tripCart.clear()
                                tripNote = ""
                                tripProductSearchQuery = ""
                                dialog.dismiss()
                                renderTripList()
                            } else {
                                statusText.text = error
                                dialog.dismiss()
                                renderTripForm()
                            }
                        }
                    }.start()
                }
            }
            addView(confirmButton)
        })

        refreshDialogTotals()
        dialog.show()
    }

    private fun renderKirimHistory() {
        rememberNavigation(ScreenState.KIRIM_HISTORY)
        val page = screenPage("Kirimlar Tarixi")
        val body = page.findViewWithTag<LinearLayout>("body")
        val items = loadKirimHistory()

        body.addView(row {
            addView(View(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(0, 0, 1f)
            })
            addView(primaryButton("+ Yangi") { openKirimClientPicker() }.apply {
                layoutParams = LinearLayout.LayoutParams(dp(86), dp(42))
            })
        })

        if (items.isEmpty()) {
            body.addView(emptyCard("Tarix bo'sh. Hech qanday ma'lumot topilmadi."))
        } else {
            items.forEach { item ->
                body.addView(kirimHistoryCard(item))
            }
        }

        setContentView(page)
    }

    private fun loadKirimHistory(): List<KirimHistoryItem> {
        val reports = db.rows("client_reports", "updated_at DESC")
        val result = mutableListOf<KirimHistoryItem>()
        for (i in 0 until reports.length()) {
            val report = reports.getJSONObject(i)
            val clientId = report.optLong("client_id")
            val clientName = report.optString("client_name").ifBlank { "Turli Tushum" }
            val txs = report.optJSONArray("transactions") ?: JSONArray()
            for (j in 0 until txs.length()) {
                val tx = txs.getJSONObject(j)
                if (tx.optString("turi") != "kirim") continue
                result += KirimHistoryItem(
                    id = tx.optLong("id"),
                    clientId = clientId,
                    clientName = clientName,
                    dateLabel = tx.optString("date_label"),
                    amount = tx.optDouble("summa"),
                    balance = tx.optDouble("balance"),
                    sortTime = parseTransactionDate(tx.optString("date_label"))?.time ?: 0L,
                )
            }
        }
        val pending = db.pendingTransactions()
        for (i in 0 until pending.length()) {
            val entry = pending.getJSONObject(i)
            if (entry.optString("type") != "kirim") continue
            val payload = entry.optJSONObject("data") ?: JSONObject()
            val clientId = payload.optLong("partner_id")
            val clientName = when {
                payload.isNull("partner_id") || clientId == 0L -> "Turli Tushum"
                else -> db.client(clientId)?.optString("name").orEmpty().ifBlank { "Mijoz #$clientId" }
            }
            result += KirimHistoryItem(
                id = -(i + 1L),
                offlineId = entry.optString("offline_id"),
                clientId = clientId,
                clientName = clientName,
                dateLabel = formatPendingTransactionDate(entry.optLong("timestamp")),
                amount = payload.optDouble("amount"),
                balance = db.client(clientId)?.optDouble("balance") ?: 0.0,
                isPending = true,
                sortTime = entry.optLong("timestamp"),
            )
        }
        return result.sortedByDescending { it.sortTime }
    }

    private fun kirimHistoryCard(item: KirimHistoryItem): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(12), strokeColor = "#d9f99d")
            setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(12)) }

            addView(row {
                addView(text("Kirim", 13, bold = true).apply {
                    setTextColor(color("#166534"))
                    background = rounded("#dcfce7", dp(16))
                    setPadding(dp(12), dp(8), dp(12), dp(8))
                })
                addView(text("${formatAmount(item.amount)} so'm", 17, bold = true).apply {
                    gravity = Gravity.END
                    setTextColor(color("#16a34a"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
            })

              addView(LinearLayout(this@MainActivity).apply {
                  orientation = LinearLayout.VERTICAL
                  background = rounded("#f8fafc", dp(10))
                  setPadding(dp(12), dp(10), dp(12), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(10), 0, dp(12)) }

                  addView(text(item.clientName, 15, bold = true).apply { setTextColor(Color.BLACK) })
                  addView(text(item.dateLabel, 12).apply {
                      setTextColor(color("#64748b"))
                      setPadding(0, dp(6), 0, 0)
                  })
                  if (item.isPending) {
                      addView(text("Sinxronlanmagan", 12, bold = true).apply {
                          setTextColor(color("#d97706"))
                          setPadding(0, dp(6), 0, 0)
                      })
                  }
              })

            addView(row {
                addView(Button(this@MainActivity).apply {
                    text = "Tahrirlash"
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#1d4ed8", dp(8))
                    setOnClickListener { openEditKirimDialog(item) }
                    layoutParams = LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                        setMargins(0, 0, dp(6), 0)
                    }
                })
                addView(Button(this@MainActivity).apply {
                    text = "O'chirish"
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#dc2626", dp(8))
                    setOnClickListener { confirmDeleteKirimFromHistory(item) }
                    layoutParams = LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                        setMargins(dp(6), 0, 0, 0)
                    }
                })
            })
        }
    }

    private fun openKirimClientPicker() {
        val clientsRaw = db.rows("clients", "updated_at DESC")
        val clients = mutableListOf<JSONObject>()
        for (i in 0 until clientsRaw.length()) {
            val client = clientsRaw.getJSONObject(i)
            if (client.optLong("id") != 0L) clients += client
        }
        clients.sortWith(compareBy<JSONObject> { it.optInt("sort_order", Int.MAX_VALUE) }.thenBy { it.optString("name") })

        val searchInput = EditText(this).apply {
            hint = "Mijoz qidirish..."
            setSingleLine(true)
            textSize = 15f
            background = rounded("#f8fafc", dp(10), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val listContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        var pickerDialog: AlertDialog? = null
        fun renderList(query: String) {
            listContainer.removeAllViews()
            listContainer.addView(kirimPickerOption("Turli Tushum", "Mijozisiz tushum", "#92400e", "#fef3c7") {
                pickerDialog?.dismiss()
                openKirimEntryDialog(0L, "Turli Tushum")
            })
            listContainer.addView(text("AGENT MIJOZLARI", 12, bold = true).apply {
                setTextColor(color("#64748b"))
                gravity = Gravity.CENTER
                setPadding(0, dp(14), 0, dp(10))
            })
            val filtered = clients.filter {
                query.isBlank() || buildString {
                    append(it.optString("name"))
                    append(" ")
                    append(it.optString("phone"))
                }.contains(query, ignoreCase = true)
            }
            if (filtered.isEmpty()) {
                listContainer.addView(emptyCard("Mijoz topilmadi."))
                return
            }
            filtered.forEach { client ->
                val debt = client.optDouble("balance")
                listContainer.addView(kirimPickerOption(
                    client.optString("name"),
                    "Qarz: ${if (debt < 0) "-" else ""}${formatAmount(kotlin.math.abs(debt))} so'm",
                    if (debt > 0) "#dc2626" else "#16a34a",
                    "#ffffff"
                ) {
                    pickerDialog?.dismiss()
                    openKirimEntryDialog(client.optLong("id"), client.optString("name"))
                })
            }
        }
        searchInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                renderList(s?.toString().orEmpty())
            }
            override fun afterTextChanged(s: Editable?) = Unit
        })

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(12))
            addView(text("Mijoz Tanlash", 20, bold = true).apply {
                setTextColor(Color.BLACK)
            })
            addView(text("Kirimni qaysi mijoz nomidan qabul qilasiz?", 13).apply {
                setTextColor(color("#475569"))
                setPadding(0, dp(4), 0, dp(12))
            })
            addView(searchInput)
            addView(ScrollView(this@MainActivity).apply {
                addView(listContainer)
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(380)
                ).apply { setMargins(0, dp(12), 0, 0) }
            })
        }
        pickerDialog = AlertDialog.Builder(this)
            .setView(content)
            .setNegativeButton("Yopish", null)
            .create()
        renderList("")
        pickerDialog.show()
    }

    private fun kirimPickerOption(title: String, subtitle: String, subtitleColor: String, bgColor: String, onClick: () -> Unit): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded(bgColor, dp(12), strokeColor = "#e2e8f0")
            setPadding(dp(14), dp(14), dp(14), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(10)) }
            setOnClickListener { onClick() }
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                addView(text(title, 16, bold = true).apply { setTextColor(Color.BLACK) })
                addView(text(subtitle, 13, bold = true).apply {
                    setTextColor(color(subtitleColor))
                    setPadding(0, dp(6), 0, 0)
                })
            })
            addView(text("›", 26, bold = true).apply {
                setTextColor(color("#3b82f6"))
            })
        }
    }

    private fun openKirimEntryDialog(clientId: Long, clientName: String) {
        val amountInput = EditText(this).apply {
            hint = "Summa"
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            textSize = 16f
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val noteInput = EditText(this).apply {
            hint = "Izoh"
            setSingleLine(true)
            textSize = 15f
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val errorText = text("", 13).apply { setTextColor(color("#dc2626")) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(8))
            addView(text(clientName, 18, bold = true).apply { setTextColor(Color.BLACK) })
            addView(label("Summa").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(amountInput)
            addView(label("Izoh").apply { setPadding(0, dp(12), 0, dp(6)) })
            addView(noteInput)
            addView(errorText.apply { setPadding(0, dp(12), 0, 0) })
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Yangi Kirim")
            .setView(content)
            .setNegativeButton("Bekor qilish", null)
            .setPositiveButton("Saqlash", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val amount = amountInput.text.toString().replace(",", "").toDoubleOrNull() ?: 0.0
                if (amount <= 0) {
                    errorText.text = "Summani to'g'ri kiriting"
                    return@setOnClickListener
                }
                val payload = JSONObject()
                    .put("amount", amount)
                    .put("note", noteInput.text.toString().trim())
                    .put("payment_method", "cash")
                    .put("partner_id", if (clientId == 0L) false else clientId)
                db.enqueueTransaction("kirim", UUID.randomUUID().toString(), payload)
                dialog.dismiss()
                syncPendingInBackground(refreshPosAfterSync = false)
                renderKirimHistory()
            }
        }
        dialog.show()
    }

    private fun openEditKirimDialog(item: KirimHistoryItem) {
        val amountInput = EditText(this).apply {
            setText(formatAmount(item.amount))
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            textSize = 16f
            background = rounded("#ffffff", dp(8), strokeColor = "#2563eb")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val errorText = text("", 13).apply { setTextColor(color("#dc2626")) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(12), dp(18), dp(8))
            addView(text(item.clientName, 16, bold = true).apply { setTextColor(Color.BLACK) })
            addView(label("Kirim summasi").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(amountInput)
            addView(errorText.apply { setPadding(0, dp(10), 0, 0) })
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Kirimni tahrirlash")
            .setView(content)
            .setNegativeButton("Bekor qilish", null)
            .setPositiveButton("Saqlash", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val amount = parseAmount(amountInput.text.toString())
                if (amount <= 0) {
                    errorText.text = "Summani to'g'ri kiriting"
                    return@setOnClickListener
                }
                  dialog.dismiss()
                  Thread {
                      val error = try {
                          if (item.isPending && item.offlineId.isNotBlank()) {
                              db.updatePendingTransactionAmount(item.offlineId, amount)
                          } else {
                              repository.editKirim(item.id, amount)
                          }
                          null
                      } catch (e: Exception) {
                          e.message ?: "Tarmoq xatosi"
                      }
                    runOnUiThread {
                        if (error == null) {
                            renderKirimHistory()
                        } else {
                            status.text = "Error: $error"
                        }
                    }
                }.start()
            }
        }
        dialog.show()
    }

    private fun confirmDeleteKirimFromHistory(item: KirimHistoryItem) {
        AlertDialog.Builder(this)
              .setMessage("Haqiqatan ham ushbu kirimni o'chirmoqchimisiz?")
              .setNegativeButton("Bekor", null)
              .setPositiveButton("O'chirish") { _, _ ->
                  Thread {
                      val error = try {
                          if (item.isPending && item.offlineId.isNotBlank()) {
                              db.deletePendingTransaction(item.offlineId)
                          } else {
                              repository.deleteKirim(item.id)
                          }
                          null
                      } catch (e: Exception) {
                          e.message ?: "Tarmoq xatosi"
                      }
                    runOnUiThread {
                        if (error == null) {
                            renderKirimHistory()
                        } else {
                            status.text = "Error: $error"
                        }
                    }
                }.start()
            }
            .show()
    }

    private fun renderChiqimHistory() {
        rememberNavigation(ScreenState.CHIQIM_HISTORY)
        val page = screenPage("Chiqimlar Tarixi")
        val body = page.findViewWithTag<LinearLayout>("body")
        val items = loadChiqimHistory()

        body.addView(row {
            addView(View(this@MainActivity).apply {
                layoutParams = LinearLayout.LayoutParams(0, 0, 1f)
            })
            addView(primaryButton("+ Yangi") { openChiqimEntryDialog() }.apply {
                layoutParams = LinearLayout.LayoutParams(dp(86), dp(42))
            })
        })

        if (items.isEmpty()) {
            body.addView(emptyCard("Tarix bo'sh. Hech qanday ma'lumot topilmadi."))
        } else {
            items.forEach { item ->
                body.addView(chiqimHistoryCard(item))
            }
        }

        setContentView(page)
    }

    private fun loadChiqimHistory(): List<ChiqimHistoryItem> {
        val rows = db.rows("payments", "updated_at DESC")
        val result = mutableListOf<ChiqimHistoryItem>()
        for (i in 0 until rows.length()) {
            val payment = rows.getJSONObject(i)
            if (payment.optString("payment_type") != "out") continue
            result += ChiqimHistoryItem(
                id = payment.optLong("id"),
                dateLabel = payment.optString("date"),
                amount = payment.optDouble("amount"),
                note = payment.optString("note"),
                expenseType = payment.optString("expense_type").ifBlank { "daily" },
                sortTime = parseTransactionDate(payment.optString("date"))?.time ?: 0L,
            )
        }
        val pending = db.pendingTransactions()
        for (i in 0 until pending.length()) {
            val entry = pending.getJSONObject(i)
            if (entry.optString("type") != "chiqim") continue
            val payload = entry.optJSONObject("data") ?: JSONObject()
            result += ChiqimHistoryItem(
                id = -(i + 1L),
                offlineId = entry.optString("offline_id"),
                dateLabel = formatPendingTransactionDate(entry.optLong("timestamp")),
                amount = payload.optDouble("amount"),
                note = payload.optString("note"),
                expenseType = payload.optString("expense_type").ifBlank { "daily" },
                isPending = true,
                sortTime = entry.optLong("timestamp"),
            )
        }
        return result.sortedByDescending { it.sortTime }
    }

    private fun chiqimHistoryCard(item: ChiqimHistoryItem): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(12), strokeColor = "#fecaca")
            setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(12)) }

            addView(row {
                addView(text(chiqimExpenseLabel(item.expenseType), 13, bold = true).apply {
                    setTextColor(color("#7f1d1d"))
                    background = rounded("#fee2e2", dp(16))
                    setPadding(dp(12), dp(8), dp(12), dp(8))
                })
                addView(text("${formatAmount(item.amount)} so'm", 17, bold = true).apply {
                    gravity = Gravity.END
                    setTextColor(color("#ef4444"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
            })

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                background = rounded("#f8fafc", dp(10))
                setPadding(dp(12), dp(10), dp(12), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(10), 0, dp(12)) }
                addView(text(item.dateLabel, 12).apply {
                    setTextColor(color("#64748b"))
                })
                if (item.note.isNotBlank()) {
                    addView(text(item.note, 13).apply {
                        setTextColor(color("#334155"))
                        setPadding(0, dp(8), 0, 0)
                    })
                }
                if (item.isPending) {
                    addView(text("Sinxronlanmagan", 12, bold = true).apply {
                        setTextColor(color("#d97706"))
                        setPadding(0, dp(8), 0, 0)
                    })
                }
            })

            addView(row {
                addView(Button(this@MainActivity).apply {
                    text = "Tahrirlash"
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#1d4ed8", dp(8))
                    setOnClickListener { openEditChiqimDialog(item) }
                    layoutParams = LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                        setMargins(0, 0, dp(6), 0)
                    }
                })
                addView(Button(this@MainActivity).apply {
                    text = "O'chirish"
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(Color.WHITE)
                    background = rounded("#dc2626", dp(8))
                    setOnClickListener { confirmDeleteChiqimFromHistory(item) }
                    layoutParams = LinearLayout.LayoutParams(0, dp(46), 1f).apply {
                        setMargins(dp(6), 0, 0, 0)
                    }
                })
            })
        }
    }

    private fun openChiqimEntryDialog() {
        val amountInput = EditText(this).apply {
            hint = "0"
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            textSize = 18f
            gravity = Gravity.END
            background = rounded("#ffffff", dp(10), strokeColor = "#ef4444")
            setPadding(dp(12), dp(14), dp(12), dp(14))
        }
        val noteInput = EditText(this).apply {
            hint = "Nima uchun..."
            minLines = 3
            gravity = Gravity.TOP or Gravity.START
            textSize = 15f
            background = rounded("#ffffff", dp(10), strokeColor = "#60a5fa")
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        val dailyRadio = android.widget.RadioButton(this).apply {
            text = "Kunlik chiqim (Biznes xarajat)"
            id = View.generateViewId()
            isChecked = true
        }
        val salaryRadio = android.widget.RadioButton(this).apply {
            text = "Oylik chiqim (Oylikdan)"
            id = View.generateViewId()
        }
        val radioGroup = android.widget.RadioGroup(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(dailyRadio)
            addView(salaryRadio)
        }
        val errorText = text("", 13).apply { setTextColor(color("#dc2626")) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(8))
            addView(text("Chiqim Olish", 20, bold = true).apply { setTextColor(Color.BLACK) })
            addView(text("Xarajat turini tanlang va chiqimni tasdiqlang.", 13).apply {
                setTextColor(color("#475569"))
                setPadding(0, dp(4), 0, dp(14))
            })
            addView(label("Chiqim Turi"))
            addView(radioGroup)
            addView(label("Summa (So'm)").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(amountInput)
            addView(label("Izoh (Ixtiyoriy)").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(noteInput)
            addView(errorText.apply { setPadding(0, dp(12), 0, 0) })
        }
        val dialog = AlertDialog.Builder(this)
            .setView(content)
            .setNegativeButton("Bekor qilish", null)
            .setPositiveButton("Chiqimni Saqlash", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val amount = parseAmount(amountInput.text.toString())
                if (amount <= 0) {
                    errorText.text = "Summani to'g'ri kiriting"
                    return@setOnClickListener
                }
                val payload = JSONObject()
                    .put("amount", amount)
                    .put("note", noteInput.text.toString().trim())
                    .put("payment_method", "cash")
                    .put("expense_type", if (salaryRadio.isChecked) "salary" else "daily")
                db.enqueueTransaction("chiqim", UUID.randomUUID().toString(), payload)
                dialog.dismiss()
                syncPendingInBackground(refreshPosAfterSync = false)
                renderChiqimHistory()
            }
        }
        dialog.show()
    }

    private fun openEditChiqimDialog(item: ChiqimHistoryItem) {
        val amountInput = EditText(this).apply {
            setText(formatAmount(item.amount))
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            textSize = 18f
            gravity = Gravity.END
            background = rounded("#ffffff", dp(10), strokeColor = "#ef4444")
            setPadding(dp(12), dp(14), dp(12), dp(14))
        }
        val noteInput = EditText(this).apply {
            setText(item.note)
            minLines = 3
            gravity = Gravity.TOP or Gravity.START
            textSize = 15f
            background = rounded("#ffffff", dp(10), strokeColor = "#60a5fa")
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        val dailyRadio = android.widget.RadioButton(this).apply {
            text = "Kunlik chiqim (Biznes xarajat)"
            id = View.generateViewId()
            isChecked = item.expenseType != "salary"
        }
        val salaryRadio = android.widget.RadioButton(this).apply {
            text = "Oylik chiqim (Oylikdan)"
            id = View.generateViewId()
            isChecked = item.expenseType == "salary"
        }
        val radioGroup = android.widget.RadioGroup(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(dailyRadio)
            addView(salaryRadio)
        }
        val errorText = text("", 13).apply { setTextColor(color("#dc2626")) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(8))
            addView(text("Chiqimni tahrirlash", 18, bold = true).apply { setTextColor(Color.BLACK) })
            addView(label("Chiqim Turi").apply { setPadding(0, dp(12), 0, dp(6)) })
            addView(radioGroup)
            addView(label("Summa (So'm)").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(amountInput)
            addView(label("Izoh").apply { setPadding(0, dp(14), 0, dp(6)) })
            addView(noteInput)
            addView(errorText.apply { setPadding(0, dp(12), 0, 0) })
        }
        val dialog = AlertDialog.Builder(this)
            .setView(content)
            .setNegativeButton("Bekor qilish", null)
            .setPositiveButton("Saqlash", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val amount = parseAmount(amountInput.text.toString())
                if (amount <= 0) {
                    errorText.text = "Summani to'g'ri kiriting"
                    return@setOnClickListener
                }
                val note = noteInput.text.toString().trim()
                val expenseType = if (salaryRadio.isChecked) "salary" else "daily"
                dialog.dismiss()
                Thread {
                    val error = try {
                        if (item.isPending && item.offlineId.isNotBlank()) {
                            db.updatePendingPayment(item.offlineId, amount, note, expenseType)
                        } else {
                            repository.editChiqim(item.id, amount, note, expenseType)
                        }
                        null
                    } catch (e: Exception) {
                        e.message ?: "Tarmoq xatosi"
                    }
                    runOnUiThread {
                        if (error == null) {
                            renderChiqimHistory()
                        } else {
                            status.text = "Error: $error"
                        }
                    }
                }.start()
            }
        }
        dialog.show()
    }

    private fun confirmDeleteChiqimFromHistory(item: ChiqimHistoryItem) {
        AlertDialog.Builder(this)
            .setMessage("Haqiqatan ham ushbu chiqimni o'chirmoqchimisiz?")
            .setNegativeButton("Bekor", null)
            .setPositiveButton("O'chirish") { _, _ ->
                Thread {
                    val error = try {
                        if (item.isPending && item.offlineId.isNotBlank()) {
                            db.deletePendingTransaction(item.offlineId)
                        } else {
                            repository.deleteChiqim(item.id)
                        }
                        null
                    } catch (e: Exception) {
                        e.message ?: "Tarmoq xatosi"
                    }
                    runOnUiThread {
                        if (error == null) {
                            renderChiqimHistory()
                        } else {
                            status.text = "Error: $error"
                        }
                    }
                }.start()
            }
            .show()
    }

    private fun renderClientReport() {
        renderAgentReport()
    }

    private fun renderAgentReport() {
        rememberNavigation(ScreenState.AGENT_REPORT)
        val agent = db.rows("agent", "id DESC").optJSONObject(0)
        val page = screenPage("Agent Hisoboti", showMenu = true)
        val body = page.findViewWithTag<LinearLayout>("body")
        val scrollView = page.findViewWithTag<ScrollView>("scroll_container")
        status = text("", 13).apply { setTextColor(color("#64748b")) }
        if (agentReportInputDateFrom.isBlank()) agentReportInputDateFrom = agentReportDateFrom
        if (agentReportInputDateTo.isBlank()) agentReportInputDateTo = agentReportDateTo

        if (agent == null) {
            body.addView(emptyCard("Agent ma'lumotlari topilmadi. Internet bo'lganda yangilang."))
            body.addView(status)
            setContentView(page)
            return
        }

        val snapshot = buildAgentReportSnapshot(agent)
        val todayLabel = SimpleDateFormat("dd.MM.yyyy", Locale.US).format(Date())

        body.addView(Button(this).apply {
            text = "Inventarni Qayta Tiklash"
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            setTextColor(Color.BLACK)
            background = rounded("#f59e0b", dp(8))
            setOnClickListener { rebuildAgentInventory() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                dp(42)
            ).apply { setMargins(0, 0, 0, dp(10)) }
        })

        body.addView(card {
            addView(text(agent.optString("name").ifBlank { "Agent" }, 20, bold = true).apply {
                setTextColor(color("#4c1d95"))
            })
            addView(text(agent.optString("phone").ifBlank { "Telefon kiritilmagan" }, 13).apply {
                setTextColor(color("#64748b"))
                setPadding(0, dp(6), 0, 0)
            })
        })

        body.addView(card {
            addView(row {
                addView(dateField(agentReportInputDateFrom) { value ->
                    captureAgentReportScroll()
                    agentReportInputDateFrom = value
                    agentReportDateFrom = value
                    rememberNavigation(ScreenState.AGENT_REPORT)
                    renderAgentReport()
                }.apply {
                    hint = "Dan"
                    layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f)
                })
                addView(text("dan", 13).apply {
                    setTextColor(color("#64748b"))
                    setPadding(dp(8), 0, dp(8), 0)
                })
                addView(dateField(agentReportInputDateTo) { value ->
                    captureAgentReportScroll()
                    agentReportInputDateTo = value
                    agentReportDateTo = value
                    rememberNavigation(ScreenState.AGENT_REPORT)
                    renderAgentReport()
                }.apply {
                    hint = "Gacha"
                    layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f)
                })
            })
            addView(row {
                addView(compactSecondaryButton("Filtrlash") {
                    agentReportDateFrom = agentReportInputDateFrom
                    agentReportDateTo = agentReportInputDateTo
                    agentReportScrollY = 0
                    rememberNavigation(ScreenState.AGENT_REPORT)
                    renderAgentReport()
                })
                addView(compactSecondaryButton("Tozalash") {
                    agentReportDateFrom = todayLabel
                    agentReportDateTo = todayLabel
                    agentReportInputDateFrom = todayLabel
                    agentReportInputDateTo = todayLabel
                    agentReportScrollY = 0
                    rememberNavigation(ScreenState.AGENT_REPORT)
                    renderAgentReport()
                })
                addView(compactSecondaryButton("Yangilash") { refreshAgentReportData() })
            })
        }.apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(10), 0, 0) }
        })

        val metricsGrid = GridLayout(this).apply {
            columnCount = 2
            useDefaultMargins = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(10), 0, 0) }
        }
        val metrics = listOf(
            AgentMetric("Sotuvlar", snapshot.salesCount.toString(), "#2563eb", "#eff6ff"),
            AgentMetric("Jami Sotuv", "${formatAmount(snapshot.totalSales)} so'm", "#059669", "#ecfdf5"),
            AgentMetric("Naqt", "${formatAmount(snapshot.totalCash)} so'm", "#16a34a", "#f0fdf4"),
            AgentMetric("Nasiya", "${formatAmount(snapshot.totalNasiya)} so'm", "#d97706", "#fff7ed"),
            AgentMetric("Jami Nasiya", "${formatAmount(snapshot.jamiNasiya)} so'm", "#dc2626", "#fef2f2"),
            AgentMetric("Chiqim", "${formatAmount(snapshot.totalChiqim)} so'm", "#dc2626", "#fef2f2"),
            AgentMetric("Sof Balans", "${formatAmount(snapshot.sofBalans)} so'm", "#0284c7", "#f0f9ff"),
            AgentMetric("Yalpi (Kassa)", "${formatAmount(snapshot.yalpiBalans)} so'm", "#0f766e", "#ecfeff"),
            AgentMetric("Foyda", "${formatAmount(snapshot.totalFoyda)} so'm", "#059669", "#f0fdf4"),
            AgentMetric("Ishlab Topilgan Oylik", "${formatAmount(snapshot.earnedSalary)} so'm", "#4338ca", "#eef2ff"),
            AgentMetric("Oylik Olindi", "${formatAmount(snapshot.salaryTaken)} so'm", "#b91c1c", "#fef2f2"),
            AgentMetric("Oylik Qoldig'i", "${formatAmount(snapshot.salaryLeft)} so'm", "#047857", "#ecfdf5"),
            AgentMetric("Agentdan qoladigan", "${formatAmount(snapshot.agentKeeps)} so'm", "#7c3aed", "#f5f3ff")
        )
        metrics.forEach { metric ->
            metricsGrid.addView(agentMetricCard(metric))
        }
        body.addView(metricsGrid)

        body.addView(row {
            addView(agentReportTabButton("Mobil POS Sotuvlar", "sales"))
            addView(agentReportTabButton("Kirimlar", "kirim"))
            addView(agentReportTabButton("Chiqimlar", "chiqim"))
            addView(agentReportTabButton("Oylik To'lovlar", "salary"))
        }.apply {
            setPadding(0, dp(12), 0, dp(4))
        })

        body.addView(
            when (agentReportTab) {
                "kirim" -> agentPaymentListCard("Kirimlar", snapshot.kirims, "#10b981")
                "chiqim" -> agentPaymentListCard("Chiqimlar", snapshot.chiqims, "#ef4444")
                "salary" -> agentPaymentListCard("Oylik To'lovlar", snapshot.salaryPayments, "#7c3aed")
                else -> agentSalesListCard(snapshot.sales)
            }
        )
        body.addView(status)
        setContentView(page)
        scrollView?.setOnScrollChangeListener { _, _, scrollY, _, _ ->
            agentReportScrollY = scrollY
        }
        scrollView?.post {
            scrollView.scrollTo(0, agentReportScrollY)
        }
    }

    private fun buildAgentReportSnapshot(agent: JSONObject): AgentReportSnapshot {
        val products = db.rows("products", "name ASC")
        val productCosts = mutableMapOf<Long, Double>()
        for (i in 0 until products.length()) {
            val product = products.getJSONObject(i)
            productCosts[product.optLong("product_id")] = product.optDouble("cost_price")
        }

        val fromDate = parseFilterDate(agentReportDateFrom)
        val toDate = parseFilterDate(agentReportDateTo)
        fun inRange(date: Date?): Boolean {
            date ?: return false
            if (fromDate != null && date.before(startOfDay(fromDate))) return false
            if (toDate != null && date.after(endOfDay(toDate))) return false
            return true
        }

        val sales = mutableListOf<AgentSaleItem>()
        val kirims = mutableListOf<AgentPaymentItem>()
        val seenSales = mutableSetOf<Long>()
        val seenKirims = mutableSetOf<Long>()
        val reports = db.rows("client_reports", "updated_at DESC")
        for (i in 0 until reports.length()) {
            val report = reports.getJSONObject(i)
            val clientName = report.optString("client_name").ifBlank { "Naqt savdo (Mijozisiz)" }
            val isCash = report.optLong("client_id") == 0L
            val txs = report.optJSONArray("transactions") ?: JSONArray()
            for (j in 0 until txs.length()) {
                val tx = txs.getJSONObject(j)
                val txDate = parseTransactionDate(tx.optString("date_label"))
                if (!inRange(txDate)) continue
                when (tx.optString("turi")) {
                    "sotuv" -> {
                        val txId = tx.optLong("id")
                        if (!seenSales.add(txId)) continue
                        var profit = 0.0
                        val lines = tx.optJSONArray("lines") ?: JSONArray()
                        for (k in 0 until lines.length()) {
                            val line = lines.getJSONObject(k)
                            val qty = line.optDouble("qty")
                            val price = line.optDouble("price")
                            val cost = productCosts[line.optLong("product_id")] ?: 0.0
                            profit += (price - cost) * qty
                        }
                        sales += AgentSaleItem(
                            id = txId,
                            name = tx.optString("name").ifBlank { "VPOS/$txId" },
                            dateLabel = tx.optString("date_label"),
                            clientName = tx.optString("partner_name").ifBlank { clientName },
                            amount = tx.optDouble("summa"),
                            state = tx.optString("state").ifBlank { "done" },
                            isCash = isCash,
                            profit = profit,
                            sortTime = txDate?.time ?: 0L,
                        )
                    }
                    "kirim" -> {
                        val txId = tx.optLong("id")
                        if (!seenKirims.add(txId)) continue
                        kirims += AgentPaymentItem(
                            id = txId,
                            name = tx.optString("name").ifBlank { "KIR/$txId" },
                            dateLabel = tx.optString("date_label"),
                            partnerName = tx.optString("partner_name").ifBlank { clientName },
                            amount = tx.optDouble("summa"),
                            state = tx.optString("state").ifBlank { "done" },
                            note = tx.optString("note"),
                            paymentMethod = tx.optString("payment_method"),
                            expenseType = "in",
                            sortTime = txDate?.time ?: 0L,
                        )
                    }
                }
            }
        }

        val chiqims = mutableListOf<AgentPaymentItem>()
        val salaryPayments = mutableListOf<AgentPaymentItem>()
        val outPayments = db.rows("payments", "updated_at DESC")
        for (i in 0 until outPayments.length()) {
            val payment = outPayments.getJSONObject(i)
            if (payment.optString("payment_type") != "out") continue
            val date = parseTransactionDate(payment.optString("date"))
            if (!inRange(date)) continue
            val item = AgentPaymentItem(
                id = payment.optLong("id"),
                name = payment.optString("name").ifBlank { "PAY/${payment.optLong("id")}" },
                dateLabel = payment.optString("date"),
                partnerName = payment.optString("partner_name"),
                amount = payment.optDouble("amount"),
                state = payment.optString("state").ifBlank { "done" },
                note = payment.optString("note"),
                paymentMethod = payment.optString("payment_method"),
                expenseType = payment.optString("expense_type"),
                sortTime = date?.time ?: 0L,
            )
            if (item.expenseType == "salary" || item.expenseType == "payout") {
                salaryPayments += item
            } else {
                chiqims += item
            }
        }

        sales.sortByDescending { it.sortTime }
        kirims.sortByDescending { it.sortTime }
        chiqims.sortByDescending { it.sortTime }
        salaryPayments.sortByDescending { it.sortTime }

        val currentClients = db.rows("clients", "updated_at DESC")
        var jamiNasiya = 0.0
        for (i in 0 until currentClients.length()) {
            val client = currentClients.getJSONObject(i)
            if (client.optBoolean("is_cash_sale") || client.optLong("id") == 0L) continue
            jamiNasiya += client.optDouble("total_due")
        }

        val cashSales = sales.filter { it.isCash }.sumOf { it.amount }
        val nasiyaSales = sales.filter { !it.isCash }.sumOf { it.amount }
        val kirimTotal = kirims.sumOf { it.amount }
        val dailyChiqim = chiqims.sumOf { it.amount }
        val salaryTaken = salaryPayments.sumOf { it.amount }
        val totalCash = cashSales + kirimTotal
        val yalpiBalans = totalCash - dailyChiqim
        val sofBalans = yalpiBalans - salaryTaken
        val totalSales = sales.sumOf { it.amount }
        val totalFoyda = sales.sumOf { it.profit }
        val earnedSalary = yalpiBalans * (agent.optDouble("komissiya_foizi") / 100.0)
        val salaryLeft = earnedSalary - salaryTaken
        val agentKeeps = totalFoyda - earnedSalary

        return AgentReportSnapshot(
            sales = sales,
            kirims = kirims,
            chiqims = chiqims,
            salaryPayments = salaryPayments,
            salesCount = sales.size,
            totalSales = totalSales,
            totalCash = totalCash,
            totalNasiya = nasiyaSales - kirimTotal,
            jamiNasiya = jamiNasiya,
            totalChiqim = dailyChiqim,
            sofBalans = sofBalans,
            yalpiBalans = yalpiBalans,
            totalFoyda = totalFoyda,
            earnedSalary = earnedSalary,
            salaryTaken = salaryTaken,
            salaryLeft = salaryLeft,
            agentKeeps = agentKeeps,
        )
    }

    private fun agentMetricCard(metric: AgentMetric): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(metric.bg, dp(10), strokeColor = "#dbe3ef")
            setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = GridLayout.LayoutParams().apply {
                width = 0
                columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                setMargins(dp(4), dp(4), dp(4), dp(4))
            }
            addView(text(metric.label, 13).apply {
                setTextColor(color("#64748b"))
            })
            addView(text(metric.value, 18, bold = true).apply {
                setTextColor(color(metric.fg))
                setPadding(0, dp(6), 0, 0)
            })
        }
    }

    private fun agentReportTabButton(label: String, key: String): Button {
        val active = agentReportTab == key
        return Button(this).apply {
            text = label
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            setTextColor(color(if (active) "#ffffff" else "#334155"))
            background = rounded(if (active) "#2563eb" else "#ffffff", dp(8), strokeColor = if (active) "#2563eb" else "#cbd5e1")
            setOnClickListener {
                captureAgentReportScroll()
                agentReportTab = key
                rememberNavigation(ScreenState.AGENT_REPORT)
                renderAgentReport()
            }
            layoutParams = LinearLayout.LayoutParams(0, dp(40), 1f).apply {
                setMargins(dp(3), 0, dp(3), 0)
            }
        }
    }

    private fun agentSalesListCard(items: List<AgentSaleItem>): LinearLayout {
        return card {
            if (items.isEmpty()) {
                addView(emptyCard("Tanlangan oraliqda sotuv topilmadi."))
            } else {
                items.forEach { item ->
                    addView(row {
                        addView(LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.VERTICAL
                            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                            addView(text(item.name, 14, bold = true).apply { setTextColor(Color.BLACK) })
                            addView(text(item.dateLabel, 12).apply {
                                setTextColor(color("#64748b"))
                                setPadding(0, dp(4), 0, 0)
                            })
                            addView(text(item.clientName.ifBlank { "Naqt savdo" }, 13).apply {
                                setTextColor(color("#334155"))
                                setPadding(0, dp(4), 0, 0)
                            })
                        })
                        addView(LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.VERTICAL
                            gravity = Gravity.END
                            addView(text("${formatAmount(item.amount)} so'm", 14, bold = true).apply {
                                setTextColor(color("#0f766e"))
                                gravity = Gravity.END
                            })
                            addView(navBadge(if (item.state == "done") "Bajarilgan" else item.state, if (item.state == "done") "#dcfce7" else "#eff6ff", if (item.state == "done") "#16a34a" else "#2563eb").apply {
                                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                                    setMargins(0, dp(6), 0, 0)
                                }
                            })
                        })
                    })
                    addView(View(this@MainActivity).apply {
                        setBackgroundColor(color("#e5e7eb"))
                        layoutParams = LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            dp(1)
                        ).apply { setMargins(0, dp(4), 0, dp(4)) }
                    })
                }
            }
        }
    }

    private fun agentPaymentListCard(title: String, items: List<AgentPaymentItem>, accent: String): LinearLayout {
        return card {
            addView(text(title, 16, bold = true).apply {
                setTextColor(color("#334155"))
                setPadding(0, 0, 0, dp(8))
            })
            if (items.isEmpty()) {
                addView(emptyCard("Tanlangan oraliqda ma'lumot topilmadi."))
            } else {
                items.forEach { item ->
                    addView(row {
                        addView(LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.VERTICAL
                            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                            addView(text(item.name, 14, bold = true).apply { setTextColor(Color.BLACK) })
                            addView(text(item.dateLabel, 12).apply {
                                setTextColor(color("#64748b"))
                                setPadding(0, dp(4), 0, 0)
                            })
                            item.partnerName.takeIf { it.isNotBlank() }?.let { partner ->
                                addView(text(partner, 13).apply {
                                    setTextColor(color("#334155"))
                                    setPadding(0, dp(4), 0, 0)
                                })
                            }
                            buildString {
                                if (item.paymentMethod.isNotBlank()) append(item.paymentMethod)
                                if (item.note.isNotBlank()) {
                                    if (isNotBlank()) append(" • ")
                                    append(item.note)
                                }
                            }.takeIf { it.isNotBlank() }?.let { detail ->
                                addView(text(detail, 12).apply {
                                    setTextColor(color("#6b7280"))
                                    setPadding(0, dp(4), 0, 0)
                                })
                            }
                        })
                        addView(LinearLayout(this@MainActivity).apply {
                            orientation = LinearLayout.VERTICAL
                            gravity = Gravity.END
                            addView(text("${formatAmount(item.amount)} so'm", 14, bold = true).apply {
                                setTextColor(color(accent))
                                gravity = Gravity.END
                            })
                            addView(navBadge(if (item.state == "done") "Bajarilgan" else item.state, "#f8fafc", "#475569").apply {
                                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                                    setMargins(0, dp(6), 0, 0)
                                }
                            })
                        })
                    })
                    addView(View(this@MainActivity).apply {
                        setBackgroundColor(color("#e5e7eb"))
                        layoutParams = LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            dp(1)
                        ).apply { setMargins(0, dp(4), 0, dp(4)) }
                    })
                }
            }
        }
    }

    private fun refreshAgentReportData() {
        if (session.token.isBlank()) {
            if (::status.isInitialized) status.text = "Online login kerak."
            return
        }
        agentReportDateFrom = agentReportInputDateFrom
        agentReportDateTo = agentReportInputDateTo
        rememberNavigation(ScreenState.AGENT_REPORT)
        if (::status.isInitialized) status.text = "Yangilanmoqda..."
        Thread {
            val error = try {
                repository.syncPending()
                repository.bootstrap()
                null
            } catch (e: Exception) {
                e.message ?: "Tarmoq xatosi"
            }
            runOnUiThread {
                if (error == null) {
                    renderAgentReport()
                    if (::status.isInitialized) status.text = "Yangilandi."
                } else if (::status.isInitialized) {
                    status.text = error
                }
            }
        }.start()
    }

    private fun rebuildAgentInventory() {
        if (session.token.isBlank()) {
            if (::status.isInitialized) status.text = "Online login kerak."
            return
        }
        if (::status.isInitialized) status.text = "Inventar qayta tiklanmoqda..."
        Thread {
            val error = try {
                repository.rebuildInventory()
                null
            } catch (e: Exception) {
                e.message ?: "Tarmoq xatosi"
            }
            runOnUiThread {
                if (error == null) {
                    renderAgentReport()
                    if (::status.isInitialized) status.text = "Inventar qayta tiklandi."
                } else if (::status.isInitialized) {
                    status.text = error
                }
            }
        }.start()
    }

    private fun captureAgentReportScroll() {
        val rootView = window?.decorView?.findViewById<View>(android.R.id.content) ?: return
        val scroll = findTaggedScrollView(rootView)
        if (scroll != null) {
            agentReportScrollY = scroll.scrollY
        }
    }

    private fun captureClientReportScroll() {
        val rootView = window?.decorView?.findViewById<View>(android.R.id.content) ?: return
        val scroll = findTaggedScrollView(rootView)
        if (scroll != null) {
            clientReportScrollY = scroll.scrollY
        }
    }

    private fun findTaggedScrollView(view: View): ScrollView? {
        if (view.tag == "scroll_container" && view is ScrollView) return view
        if (view is android.view.ViewGroup) {
            for (i in 0 until view.childCount) {
                val found = findTaggedScrollView(view.getChildAt(i))
                if (found != null) return found
            }
        }
        return null
    }

    private fun describeCachedItem(table: String, item: JSONObject): String {
        return when (table) {
            "requests" -> {
                "${item.optString("name")} | ${item.optString("partner_name")}\nHolat: ${item.optString("state")} | Jami: ${item.optDouble("total_amount").toLong()} so'm"
            }
            "trips" -> {
                "${item.optString("name")}\nHolat: ${item.optString("state")} | Soni: ${item.optDouble("total_qty").toLong()} | Tan narx: ${item.optDouble("total_cost").toLong()} so'm"
            }
            else -> item.toString()
        }
    }

    private fun addProduct(product: JSONObject) {
        val id = product.optLong("product_id")
        val existing = cart[id]
        if (existing == null) {
            cart[id] = CartLine(
                productId = id,
                name = product.optString("name"),
                qty = 1.0,
                price = product.optDouble("price")
            )
        } else {
            existing.qty += 1.0
        }
    }

    private fun submitLocalSale() {
        if (cart.isEmpty()) {
            status.text = "Savatcha bo'sh"
            return
        }

        val lines = JSONArray()
        for (line in cart.values) {
            lines.put(
                JSONObject()
                    .put("product_id", line.productId)
                    .put("qty", line.qty)
                    .put("price", line.price)
            )
            db.reduceInventory(line.productId, line.qty)
        }

        val payload = JSONObject()
            .put("partner_id", if (selectedClientId == 0L) false else selectedClientId)
            .put("lines", lines)

        db.enqueueTransaction("sale", UUID.randomUUID().toString(), payload)
        cart.clear()
        status.text = "Sale saved offline. It will sync when online."
        renderPos()
    }

    private fun productCard(product: JSONObject, onAdd: () -> Unit): LinearLayout {
        val remaining = product.optDouble("remaining")
        val cardWidth = ((resources.displayMetrics.widthPixels - dp(42)) / 2).coerceAtLeast(dp(154))
        val lp = GridLayout.LayoutParams().apply {
            width = cardWidth
            height = GridLayout.LayoutParams.WRAP_CONTENT
            setMargins(dp(4), dp(4), dp(4), dp(10))
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(14), strokeColor = "#e2e8f0")
            setPadding(dp(10), dp(10), dp(10), dp(10))
            layoutParams = lp
            minimumHeight = dp(208)

            addView(View(this@MainActivity).apply {
                background = rounded("#eef2ff", dp(12))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(86)
                ).apply { setMargins(0, 0, 0, dp(10)) }
            })
            val cartLine = cart[product.optLong("product_id")]

            addView(text(product.optString("name"), 15, bold = true).apply {
                setTextColor(color("#0f172a"))
                maxLines = 2
            })
            if (cartLine == null) {
                addView(text("${formatAmount(product.optDouble("price"))} UZS", 14, bold = true).apply {
                    setTextColor(color("#059669"))
                    setPadding(0, dp(4), 0, 0)
                })
            } else {
                addView(EditText(this@MainActivity).apply {
                    setText(formatAmount(cartLine.price))
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(color("#065f46"))
                    inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                    setSingleLine(true)
                    setSelectAllOnFocus(true)
                    background = rounded("#ecfdf5", dp(8), strokeColor = "#34d399")
                    setPadding(dp(10), 0, dp(10), 0)
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        dp(38)
                    ).apply { setMargins(0, dp(4), 0, 0) }
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            val value = parseAmount(s?.toString().orEmpty())
                            if (value >= 0) cartLine.price = value
                        }
                        override fun afterTextChanged(s: Editable?) = Unit
                    })
                })
            }
            addView(text("Qoldiq: ${remaining.toLong()}", 11).apply {
                setTextColor(color("#64748b"))
                setPadding(0, dp(2), 0, dp(8))
            })
            if (cartLine == null) {
                addView(primaryButton("+ Qo'shish") { onAdd() })
            } else {
                addView(quantityEditor(product, cartLine))
            }
        }
    }

    private fun quantityEditor(product: JSONObject, line: CartLine): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded("#ffffff", dp(9), strokeColor = "#2563eb")
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
            ).apply { setMargins(0, dp(2), 0, 0) }
            addView(TextView(this@MainActivity).apply {
                text = if (line.qty <= 1.0) "×" else "-"
                text = if (line.qty <= 1.0) "x" else "-"
                textSize = 16f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color("#ef4444"))
                background = transparent()
                includeFontPadding = false
                setOnClickListener {
                    val id = product.optLong("product_id")
                    if (line.qty <= 1.0) cart.remove(id) else line.qty -= 1.0
                    renderPos()
                }
                layoutParams = LinearLayout.LayoutParams(dp(40), LinearLayout.LayoutParams.MATCH_PARENT)
            })
            addView(EditText(this@MainActivity).apply {
                setText(line.qty.toLong().toString())
                textSize = 15f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color("#1e3a8a"))
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setSingleLine(true)
                setSelectAllOnFocus(true)
                background = transparent()
                setPadding(0, 0, 0, 0)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        val value = s?.toString()?.toDoubleOrNull()
                        if (value != null && value > 0) line.qty = value.coerceAtMost(product.optDouble("remaining"))
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
            })
            addView(TextView(this@MainActivity).apply {
                text = "+"
                textSize = 18f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                setTextColor(color("#111827"))
                background = transparent()
                includeFontPadding = false
                setOnClickListener {
                    if (line.qty < product.optDouble("remaining")) {
                        line.qty += 1.0
                        renderPos()
                    }
                }
                layoutParams = LinearLayout.LayoutParams(dp(40), LinearLayout.LayoutParams.MATCH_PARENT)
            })
        }
    }

    private fun cartSummary(): TextView {
        if (cart.isEmpty()) return text("Savatcha bo'sh", 14).apply { setTextColor(color("#64748b")) }
        val total = cart.values.sumOf { it.qty * it.price }
        val lines = cart.values.joinToString("\n") {
            "${it.name}: ${it.qty.toLong()} x ${it.price.toLong()} = ${(it.qty * it.price).toLong()}"
        }
        return text("$lines\nJami: ${total.toLong()} so'm", 14, bold = true).apply { setTextColor(color("#0f172a")) }
    }

    private fun countsText(): TextView {
        val c = db.counts()
        return text(
            "Clients: ${c["clients"]} | Inventory: ${c["inventory"]} | Requests: ${c["requests"]} | Trips: ${c["trips"]} | Pending: ${c["pending"]}",
            13
        )
    }

    private fun runNetwork(message: String, work: () -> String) {
        status.text = message
        Thread {
            val result = try {
                work()
            } catch (e: Exception) {
                "Error: ${e.message}"
            }
            runOnUiThread {
                status.text = result
            }
        }.start()
    }

    private fun refreshOfflineData() {
        val now = System.currentTimeMillis()
        if (refreshInFlight || now - lastAutoRefreshAt < 3000) return
        lastAutoRefreshAt = now
        refreshInFlight = true
        Thread {
            try {
                repository.syncPending()
                repository.bootstrap()
                runOnUiThread {
                    if (cart.isEmpty()) {
                        rerenderCurrentScreen()
                    } else if (::status.isInitialized) {
                        status.text = "Server data refreshed. Cart is kept offline."
                    }
                }
            } catch (_: Exception) {
                // Offline-first: keep showing cached data if the server is unavailable.
            } finally {
                refreshInFlight = false
            }
        }.start()
    }

    private fun registerNetworkCallback() {
        if (networkCallback != null) return
        val manager = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                if (::session.isInitialized && session.token.isNotBlank()) {
                    runOnUiThread { refreshOfflineData() }
                }
            }
        }
        networkCallback = callback
        runCatching { manager.registerDefaultNetworkCallback(callback) }
    }

    private fun unregisterNetworkCallback() {
        val callback = networkCallback ?: return
        val manager = getSystemService(ConnectivityManager::class.java) ?: return
        runCatching { manager.unregisterNetworkCallback(callback) }
        networkCallback = null
    }

    private fun rerenderCurrentScreen() {
        when (currentScreenState) {
            ScreenState.LOGIN -> renderLogin()
            ScreenState.POS -> renderPos()
            ScreenState.CLIENT_SELECTION -> renderClientSelection()
            ScreenState.REQUEST_LIST -> renderRequestsList()
            ScreenState.REQUEST_FORM -> renderRequestForm()
            ScreenState.REQUEST_DETAILS -> {
                val req = db.rows("requests", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeRequestId }
                }
                if (req != null) renderRequestDetails(req, resetDraft = false) else renderRequestsList()
            }
            ScreenState.REQUEST_ADD_PRODUCT -> {
                val req = db.rows("requests", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeRequestId }
                }
                if (req != null) openRequestAddProductDialog(req) else renderRequestsList()
            }
            ScreenState.KIRIM_HISTORY -> renderKirimHistory()
            ScreenState.CHIQIM_HISTORY -> renderChiqimHistory()
            ScreenState.TRIP_LIST -> renderTripList()
            ScreenState.TRIP_DETAILS -> {
                val trip = db.rows("trips", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeTripId }
                }
                if (trip != null) renderTripDetails(trip) else renderTripList()
            }
            ScreenState.TRIP_FORM -> renderTripForm()
            ScreenState.CLIENT_REPORT -> {
                val client = db.client(activeReportClientId)
                if (client != null && activeReportClientId != 0L) {
                    renderClientReport(client)
                } else {
                    renderClientSelection()
                }
            }
            ScreenState.AGENT_REPORT -> renderAgentReport()
            ScreenState.MENU -> restoreLastScreen()
        }
    }

    private fun verticalRoot(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(32), dp(36), dp(32), dp(36))
        }
    }

    private fun row(content: LinearLayout.() -> Unit): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(8))
            content()
        }
    }

    private fun posNavbar(title: String, clientItems: List<ClientItem>): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(10), dp(8), dp(10))
            setBackgroundColor(color("#2563eb"))
            addView(text(title, 18, bold = true).apply {
                setTextColor(Color.WHITE)
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            })
            addView(Button(this@MainActivity).apply {
                text = "$selectedClientName ▾"
                textSize = 13f
                isAllCaps = false
                setTextColor(Color.WHITE)
                background = rounded("#3b82f6", dp(5), strokeColor = "#ffffff")
                setPadding(dp(8), 0, dp(8), 0)
                minHeight = dp(34)
                minimumHeight = dp(34)
                setOnClickListener { renderClientSelection() }
                layoutParams = LinearLayout.LayoutParams(0, dp(38), 1f).apply {
                    setMargins(dp(10), 0, dp(8), 0)
                }
            })
            addView(navBadge("● Online", "#dcfce7", "#16a34a"))
            addView(Button(this@MainActivity).apply {
                text = "⋮"
                textSize = 24f
                setTextColor(Color.WHITE)
                background = transparent()
                minWidth = 0
                minimumWidth = 0
                minHeight = 0
                minimumHeight = 0
                setPadding(0, 0, 0, 0)
                setOnClickListener { showActionMenu(this) }
                layoutParams = LinearLayout.LayoutParams(dp(36), dp(38))
            })
        }
    }

    private fun renderClientSelection() {
        rememberNavigation(ScreenState.CLIENT_SELECTION)
        val clientRows = db.rows("clients", "updated_at DESC")
        val clients = mutableListOf<JSONObject>()
        for (i in 0 until clientRows.length()) {
            clients += clientRows.getJSONObject(i)
        }
        clients.sortWith(
            compareBy<JSONObject> { it.optInt("sort_order", Int.MAX_VALUE) }
                .thenByDescending { it.optString("last_transaction_date") }
                .thenBy { it.optString("name") }
        )
        val page = screenPage("Mijoz Tanlash", showMenu = true)
        val body = page.findViewWithTag<LinearLayout>("body")

        body.addView(row {
            addView(EditText(this@MainActivity).apply {
                hint = "Mijozni qidirish..."
                setText(clientSearchQuery)
                setSingleLine(true)
                textSize = 14f
                setHintTextColor(color("#94a3b8"))
                background = rounded("#ffffff", dp(7), strokeColor = "#d1d5db")
                setPadding(dp(12), 0, dp(12), 0)
                layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                        val next = s?.toString().orEmpty()
                        if (next != clientSearchQuery) {
                            clientSearchQuery = next
                            renderClientSelection()
                        }
                    }
                    override fun afterTextChanged(s: Editable?) = Unit
                })
            })
            addView(Button(this@MainActivity).apply {
                text = "+"
                textSize = 26f
                gravity = Gravity.CENTER
                includeFontPadding = false
                setTextColor(color("#062018"))
                background = rounded("#10b981", dp(7))
                setPadding(0, 0, 0, 0)
                setOnClickListener { openNewClientDialog() }
                layoutParams = LinearLayout.LayoutParams(dp(48), dp(48)).apply {
                    setMargins(dp(10), 0, 0, 0)
                }
            })
        })

        var visibleClients = 0
        for (client in clients) {
            if (clientSearchQuery.isNotBlank()) {
                val q = clientSearchQuery.trim()
                val haystack = buildString {
                    append(client.optString("name"))
                    append(" ")
                    append(client.optString("phone"))
                }
                if (!haystack.contains(q, ignoreCase = true)) {
                    continue
                }
            }
            visibleClients += 1
            body.addView(clientRow(client))
        }
        if (visibleClients == 0) {
            body.addView(emptyCard("Qidiruv bo'yicha mijoz topilmadi."))
        }

        setContentView(page)
    }

    private fun clientRow(client: JSONObject): LinearLayout {
        val id = client.optLong("id")
        val name = client.optString("name")
        val debt = client.optDouble("total_due")
        val lastTransactionDate = client.optString("last_transaction_date")
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = rounded("#ffffff", dp(8), strokeColor = "#e5e7eb")
            setPadding(dp(14), dp(14), dp(10), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(5), 0, dp(10)) }
            setOnClickListener {
                selectedClientId = id
                selectedClientName = if (id == 0L) "Naqt savdo" else name
                renderPos()
            }

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                addView(text(name, 15, bold = true).apply { setTextColor(Color.BLACK) })
                addView(row {
                    setPadding(0, dp(6), 0, 0)
                    addView(text("Hozirgi qarz: ", 13).apply {
                        setTextColor(color("#1f2937"))
                    })
                    addView(text(formatAmount(debt), 13, bold = true).apply {
                        setTextColor(color("#dc2626"))
                    })
                })
                if (lastTransactionDate.isNotBlank()) {
                    addView(text("🗓 $lastTransactionDate", 12).apply {
                        setTextColor(color("#64748b"))
                        setPadding(0, dp(6), 0, 0)
                    })
                }
            })

            addView(Button(this@MainActivity).apply {
                text = "📊 Hisobot"
                isAllCaps = false
                textSize = 13f
                setTextColor(color("#334155"))
                background = rounded("#f3f4f6", dp(6))
                setOnClickListener {
                    renderClientReport(client)
                }
                layoutParams = LinearLayout.LayoutParams(dp(104), dp(42)).apply {
                    setMargins(dp(8), 0, dp(6), 0)
                }
            })
            addView(text("›", 30, bold = true).apply {
                setTextColor(color("#94a3b8"))
            })
        }
    }

    private fun openNewClientDialog() {
        if (session.token.isBlank()) {
            AlertDialog.Builder(this)
                .setMessage("Yangi mijoz qo'shish uchun online login kerak.")
                .setPositiveButton("OK", null)
                .show()
            return
        }

        val nameInput = EditText(this).apply {
            hint = "Apteka / Mijoz nomi"
            setSingleLine(true)
            textSize = 15f
            background = rounded("#ffffff", dp(7), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val phoneInput = EditText(this).apply {
            hint = "+998 xx xxx xx xx"
            setSingleLine(true)
            textSize = 15f
            inputType = InputType.TYPE_CLASS_PHONE
            background = rounded("#ffffff", dp(7), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val telegramInput = EditText(this).apply {
            hint = "Masalan: 123456789"
            setSingleLine(true)
            textSize = 15f
            background = rounded("#ffffff", dp(7), strokeColor = "#d1d5db")
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        val errorText = text("", 12).apply {
            setTextColor(color("#dc2626"))
        }

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(8), dp(6), dp(8), 0)
            addView(label("Mijoz Nomi *"))
            addView(nameInput)
            addView(label("Telefon Raqami *").apply { setPadding(0, dp(12), 0, dp(4)) })
            addView(phoneInput)
            addView(label("Telegram Chat ID (Ixtiyoriy)").apply { setPadding(0, dp(12), 0, dp(4)) })
            addView(telegramInput)
            addView(errorText.apply { setPadding(0, dp(12), 0, 0) })
        }

        val dialog = AlertDialog.Builder(this)
            .setTitle("Yangi Mijoz Qo'shish")
            .setView(content)
            .setNegativeButton("Bekor qilish", null)
            .setPositiveButton("Saqlash", null)
            .create()

        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val name = nameInput.text.toString().trim()
                val phone = phoneInput.text.toString().trim()
                val telegram = telegramInput.text.toString().trim()
                if (name.isBlank() || phone.isBlank()) {
                    errorText.text = "Iltimos, ism va telefon raqamini kiriting."
                    return@setOnClickListener
                }
                errorText.text = "Saqlanmoqda..."
                Thread {
                    val result = try {
                        repository.createClient(name, phone, telegram)
                    } catch (e: Exception) {
                        JSONObject().put("error", e.message ?: "Tarmoq xatosi")
                    }
                    runOnUiThread {
                        val error = result.optString("error")
                        if (error.isNotBlank()) {
                            errorText.text = error
                        } else {
                            val clientId = result.optLong("client_id")
                            val client = db.client(clientId)
                            if (client != null) {
                                selectedClientId = clientId
                                selectedClientName = client.optString("name").ifBlank { "Naqt savdo" }
                            }
                            clientSearchQuery = ""
                            dialog.dismiss()
                            renderPos()
                        }
                    }
                }.start()
            }
        }
        dialog.show()
    }

    private fun showClientMenu(anchor: View, clients: List<ClientItem>) {
        val menu = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(6), dp(6), dp(6), dp(6))
            background = rounded("#ffffff", dp(8), strokeColor = "#e5e7eb")
            for (client in clients) {
                addView(menuItem(client.name) {
                    selectedClientId = client.id
                    selectedClientName = client.name.ifBlank { "Naqt savdo" }
                    renderPos()
                })
            }
        }
        PopupWindow(menu, dp(260), LinearLayout.LayoutParams.WRAP_CONTENT, true).apply {
            elevation = dp(10).toFloat()
            showAsDropDown(anchor, 0, 0)
        }
    }

    private fun searchBox(): EditText {
        return EditText(this).apply {
            hint = "Tovarni qidirish..."
            setText(productSearchQuery)
            textSize = 16f
            setSingleLine(true)
            setTextColor(color("#0f172a"))
            setHintTextColor(color("#94a3b8"))
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setPadding(dp(12), 0, dp(12), 0)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(50)
            ).apply { setMargins(0, 0, 0, dp(14)) }
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    val next = s?.toString().orEmpty()
                    if (next != productSearchQuery) {
                        productSearchQuery = next
                        renderPos()
                    }
                }
                override fun afterTextChanged(s: Editable?) = Unit
            })
        }
    }

    private fun showActionMenu(anchor: View) {
        val menu = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(6), 0, dp(6))
            background = rounded("#ffffff", dp(6), strokeColor = "#e5e7eb")
        }

        var popup: PopupWindow? = null
        fun addMenuAction(icon: String, label: String, hex: String, onClick: () -> Unit) {
            menu.addView(actionMenuItem(icon, label, hex) {
                popup?.dismiss()
                onClick()
            })
        }

        addMenuAction("+", "Kirimlar", "#10b981") { renderKirimHistory() }
        addMenuAction("-", "Chiqimlar", "#ef4444") { renderChiqimHistory() }
        menu.addView(menuDivider())
        addMenuAction("▣", "Mahsulot\nYuklash", "#1e3a8a") { renderTripList() }
        addMenuAction("□", "So'rovlar", "#3b82f6") { renderRequestsList() }
        menu.addView(menuDivider())
        addMenuAction("▤", "Agent\nHisoboti", "#8b5cf6") { renderClientReport() }
        menu.addView(menuDivider())
        addMenuAction("↪", "Tizimdan\nchiqish", "#64748b") {
            session.clearAuth()
            cart.clear()
            renderLogin()
        }

        popup = PopupWindow(menu, dp(128), LinearLayout.LayoutParams.WRAP_CONTENT, true).apply {
            elevation = dp(10).toFloat()
            isOutsideTouchable = true
            showAsDropDown(anchor, -dp(120), 0)
        }
    }

    private fun bottomCartBar(): LinearLayout {
        val total = cart.values.sumOf { it.qty * it.price }.toLong()
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(12))
            background = rounded("#ffffff", 0, strokeColor = "#e5e7eb")
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                addView(text("Jami: $total so'm", 16, bold = true).apply { setTextColor(color("#dc2626")) })
                addView(text("${cart.size} turdagi mahsulot", 12).apply { setTextColor(color("#6b7280")) })
            })
            addView(primaryButton("Xarid ->") { renderCheckout() }.apply {
                layoutParams = LinearLayout.LayoutParams(dp(132), dp(48))
            })
        }
    }

    private fun renderCheckout() {
        if (cart.isEmpty()) {
            renderPos()
            return
        }
        rememberNavigation(ScreenState.MENU)

        val isCash = selectedClientId == 0L
        val total = cart.values.sumOf { it.qty * it.price }.toLong()
        val page = screenPage("Xaridni Tasdiqlash")
        val body = page.findViewWithTag<LinearLayout>("body")

        body.addView(card {
            for (line in cart.values) {
                addView(row {
                    addView(LinearLayout(this@MainActivity).apply {
                        orientation = LinearLayout.VERTICAL
                        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                        addView(text(line.name, 14, bold = true).apply { setTextColor(Color.BLACK) })
                        addView(text("${line.qty.toLong()} x ${line.price.toLong()}", 12).apply {
                            setTextColor(color("#475569"))
                            setPadding(0, dp(3), 0, 0)
                        })
                    })
                    addView(text((line.qty * line.price).toLong().toString(), 14, bold = true).apply {
                        gravity = Gravity.END
                        setTextColor(Color.BLACK)
                    })
                })
            }
            addView(View(this@MainActivity).apply {
                setBackgroundColor(color("#e5e7eb"))
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(1)).apply {
                    setMargins(0, dp(10), 0, dp(10))
                }
            })
            addView(row {
                addView(text("Jami (${if (isCash) "Naqt" else "Nasiya"}):", 16, bold = true).apply {
                    setTextColor(Color.BLACK)
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(text(total.toString(), 16, bold = true).apply {
                    setTextColor(color(if (isCash) "#10b981" else "#ef4444"))
                })
            })
        })

        body.addView(Button(this).apply {
            text = if (isCash) "NAQT SOTISH" else "NASIYA BILAN SOTISH"
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = rounded(if (isCash) "#10b981" else "#dc2626", dp(7))
            setOnClickListener {
                val savedTotal = saveSaleOffline()
                syncPendingInBackground(refreshPosAfterSync = isCash)
                if (isCash) {
                    renderPos()
                } else {
                    renderNasiyaPayment(savedTotal)
                }
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(58)
            ).apply { setMargins(0, dp(14), 0, 0) }
        })

        setContentView(page)
    }

    private fun renderNasiyaPayment(total: Double) {
        rememberNavigation(ScreenState.MENU)
        val page = screenPage("To'lov Qabul Qilish")
        val body = page.findViewWithTag<LinearLayout>("body")
        val amountInput = EditText(this).apply {
            setText(total.toLong().toString())
            textSize = 18f
            gravity = Gravity.END
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            background = rounded("#ffffff", dp(7), strokeColor = "#2563eb")
            setPadding(dp(12), 0, dp(12), 0)
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(58))
        }

        body.addView(text("✓", 34, bold = true).apply {
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            background = rounded("#10b981", dp(28))
            layoutParams = LinearLayout.LayoutParams(dp(56), dp(56)).apply {
                gravity = Gravity.CENTER_HORIZONTAL
                setMargins(0, dp(18), 0, dp(14))
            }
        })
        body.addView(text("Savdo Qabul Qilindi!", 20, bold = true).apply {
            gravity = Gravity.CENTER
            setTextColor(Color.BLACK)
        })
        body.addView(text("Xarid summasi mijoz qarziga (Nasiya) avtomatik yozildi.", 13).apply {
            gravity = Gravity.CENTER
            setTextColor(color("#64748b"))
            setPadding(0, dp(8), 0, dp(24))
        })
        body.addView(card {
            addView(text("Mijoz hozir pul to'laydimi?", 17, bold = true).apply {
                gravity = Gravity.CENTER
                setTextColor(Color.BLACK)
                setPadding(0, 0, 0, dp(16))
            })
            addView(label("To'lov summasi (Kirim):"))
            addView(amountInput)
            addView(Button(this@MainActivity).apply {
                text = "Naqt Pul Qabul Qilish (Kirim)"
                textSize = 16f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(Color.WHITE)
                background = rounded("#059669", dp(7))
                setOnClickListener {
                    val amount = amountInput.text.toString().replace(",", "").toDoubleOrNull() ?: 0.0
                    if (amount > 0) {
                        db.enqueueTransaction(
                            "kirim",
                            UUID.randomUUID().toString(),
                            JSONObject()
                                .put("amount", amount)
                                .put("partner_id", selectedClientId)
                                .put("payment_method", "cash")
                                .put("note", "Nasiya savdodan keyingi kirim")
                        )
                    }
                    resetSelectedClientToCash()
                    syncPendingInBackground(refreshPosAfterSync = true)
                    renderPos()
                }
                layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(58)).apply {
                    setMargins(0, dp(14), 0, 0)
                }
            })
        })
        body.addView(Button(this).apply {
            text = "Ayni vaqtda to'lov yo'q (O'tkazib yuborish)"
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = rounded("#dc2626", dp(7))
            setOnClickListener {
                resetSelectedClientToCash()
                syncPendingInBackground(refreshPosAfterSync = true)
                renderPos()
            }
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(58)).apply {
                setMargins(0, dp(20), 0, 0)
            }
        })

        setContentView(page)
    }

    private fun saveSaleOffline(): Double {
        val total = cart.values.sumOf { it.qty * it.price }
        val lines = JSONArray()
        for (line in cart.values) {
            lines.put(
                JSONObject()
                    .put("product_id", line.productId)
                    .put("qty", line.qty)
                    .put("price", line.price)
            )
            db.reduceInventory(line.productId, line.qty)
        }

        val payload = JSONObject()
            .put("partner_id", if (selectedClientId == 0L) false else selectedClientId)
            .put("lines", lines)
            .put("source_request_id", if (sourceRequestId > 0L) sourceRequestId else false)

        db.enqueueTransaction("sale", UUID.randomUUID().toString(), payload)
        cart.clear()
        return total
    }

    private fun syncPendingInBackground(refreshPosAfterSync: Boolean) {
        if (session.token.isBlank()) return
        Thread {
            val error = try {
                repository.syncPending()
                null
            } catch (e: Exception) {
                e.message ?: "Sinxronlashda xatolik"
            }
            runOnUiThread {
                if (error == null) {
                    if (refreshPosAfterSync) {
                        renderPos()
                    } else if (::status.isInitialized) {
                        status.text = "Sinxronlandi"
                    }
                } else if (::status.isInitialized) {
                    status.text = "Offline saqlandi. Sinxronlash: $error"
                }
            }
        }.start()
    }

    private fun renderClientReport(client: JSONObject) {
        if (activeReportClientId != client.optLong("id")) {
            clientReportScrollY = 0
        }
        activeReportClientId = client.optLong("id")
        rememberNavigation(ScreenState.CLIENT_REPORT)
        val report = db.clientReport(client.optLong("id"))
        val name = report?.optString("client_name")?.takeIf { it.isNotBlank() } ?: client.optString("name")
        val debt = report?.optDouble("total_due") ?: client.optDouble("balance", client.optDouble("total_due"))
        val phone = report?.optString("phone")?.takeIf { it.isNotBlank() } ?: client.optString("phone")
        val telegramChatId = report?.optString("telegram_chat_id") ?: client.optString("telegram_chat_id")
        val transactions = filterReportTransactions(report?.optJSONArray("transactions") ?: JSONArray())
        val page = screenPage("Mijoz Hisoboti")
        val body = page.findViewWithTag<LinearLayout>("body")
        val scrollView = page.findViewWithTag<ScrollView>("scroll_container")

        body.addView(card {
            addView(row {
                addView(text(name, 15, bold = true).apply {
                    setTextColor(Color.BLACK)
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(text("Hisob-kitob", 13).apply { setTextColor(color("#475569")) })
            })
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                background = rounded("#fffbea", dp(0), strokeColor = "#fde68a")
                setPadding(dp(10), dp(10), dp(10), dp(10))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(8), 0, dp(14)) }
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(label("Dan:"))
                    addView(dateField(reportDateFrom) { value ->
                        reportDateFrom = value
                        rememberNavigation(ScreenState.CLIENT_REPORT)
                        captureClientReportScroll()
                        renderClientReport(client)
                    }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(38)))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(label("Gacha:"))
                    addView(dateField(reportDateTo) { value ->
                        reportDateTo = value
                        rememberNavigation(ScreenState.CLIENT_REPORT)
                        captureClientReportScroll()
                        renderClientReport(client)
                    }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(38)))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                        setMargins(dp(8), 0, dp(8), 0)
                    }
                })
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    gravity = Gravity.BOTTOM
                    addView(text(" ", 12).apply {
                        visibility = View.INVISIBLE
                        setPadding(0, 0, 0, dp(4))
                    })
                    addView(compactSecondaryButton("Tozalash") {
                        reportDateFrom = ""
                        reportDateTo = ""
                        rememberNavigation(ScreenState.CLIENT_REPORT)
                        captureClientReportScroll()
                        renderClientReport(client)
                    })
                })
            })
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                background = rounded("#fff8db", dp(7), strokeColor = "#fde68a")
                setPadding(dp(12), dp(14), dp(12), dp(14))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply { setMargins(0, dp(12), 0, dp(10)) }
                addView(text("Jami Qarz:", 13).apply {
                    gravity = Gravity.CENTER
                    setTextColor(color("#92400e"))
                })
                addView(text("${formatAmount(debt)} so'm", 22, bold = true).apply {
                    gravity = Gravity.CENTER
                    setTextColor(color("#ea580c"))
                })
            })
              addView(LinearLayout(this@MainActivity).apply {
                  orientation = LinearLayout.VERTICAL
                  background = rounded("#f8fbff", dp(7), strokeColor = "#bfdbfe")
                  setPadding(dp(12), dp(12), dp(12), dp(12))
                  addView(label("Telefon Raqami"))
                  addView(TextView(this@MainActivity).apply {
                      text = if (phone.isNotBlank()) phone else "-"
                      textSize = 14f
                      setTextColor(color("#0f172a"))
                      background = rounded("#ffffff", dp(7), strokeColor = "#cbd5e1")
                      setPadding(dp(12), dp(11), dp(12), dp(11))
                      layoutParams = LinearLayout.LayoutParams(
                          LinearLayout.LayoutParams.MATCH_PARENT,
                          LinearLayout.LayoutParams.WRAP_CONTENT
                      ).apply { setMargins(0, 0, 0, dp(12)) }
                  })
                  addView(label("Telegram Chat ID"))
                  var telegramInput: EditText? = null
                  addView(row {
                      addView(EditText(this@MainActivity).apply {
                        telegramInput = this
                        hint = "Masalan: 123456789"
                        setText(telegramChatId)
                        setSingleLine(true)
                        textSize = 14f
                        background = rounded("#ffffff", dp(7), strokeColor = "#cbd5e1")
                        setPadding(dp(12), 0, dp(12), 0)
                        layoutParams = LinearLayout.LayoutParams(0, dp(42), 1f)
                    })
                    addView(primaryButton("Saqlash") {
                        saveTelegramChatId(client, telegramInput?.text?.toString().orEmpty())
                    }.apply {
                        layoutParams = LinearLayout.LayoutParams(dp(108), dp(42)).apply { setMargins(dp(8), 0, 0, 0) }
                    })
                })
            })
            addView(reportHeader())
            if (transactions.length() == 0) {
                addView(text("Ma'lumot topilmadi.", 13).apply {
                    gravity = Gravity.CENTER
                    setTextColor(color("#64748b"))
                    setPadding(0, dp(26), 0, dp(26))
                })
            } else {
                for (i in 0 until transactions.length()) {
                    val tx = transactions.getJSONObject(i)
                    addView(reportTransactionRow(client, tx))
                    val key = reportTxnKey(tx)
                    if ((expandedReportTxnKeys.contains(key) || editingReportTxnKey == key) && ((tx.optJSONArray("lines")?.length() ?: 0) > 0)) {
                        addView(reportSaleLinesPanel(client, tx))
                    }
                }
            }
        })

        setContentView(page)
        scrollView?.setOnScrollChangeListener { _, _, scrollY, _, _ ->
            clientReportScrollY = scrollY
        }
        scrollView?.post {
            scrollView.scrollTo(0, clientReportScrollY)
        }
    }

    private fun reportTransactionRow(client: JSONObject, tx: JSONObject): LinearLayout {
        val isDebt = tx.optBoolean("is_debt")
        val amount = tx.optDouble("summa") * if (isDebt) 1.0 else -1.0
        val key = reportTxnKey(tx)
        val isEditing = editingReportTxnKey == key
        val label = tx.optString("turi_label", tx.optString("turi")).ifBlank { tx.optString("turi") }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(color(if (tx.optString("turi") == "kirim") "#ecfdf5" else "#ffffff"))
            setPadding(dp(10), dp(12), dp(10), dp(12))
            setOnClickListener {
                if (!isEditing && ((tx.optJSONArray("lines")?.length() ?: 0) > 0)) {
                    if (expandedReportTxnKeys.contains(key)) expandedReportTxnKeys.remove(key) else expandedReportTxnKeys.add(key)
                    captureClientReportScroll()
                    renderClientReport(client)
                }
            }

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                addView(text(tx.optString("date_label"), 12).apply { setTextColor(color("#0f172a")) })
                if (tx.optString("turi") == "kirim" || tx.optString("turi") == "sotuv") {
                    addView(LinearLayout(this@MainActivity).apply {
                        orientation = if (isEditing) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
                        setPadding(0, dp(5), 0, 0)
                        if (isEditing) {
                            addView(miniAction("✓ Saqlash", "#059669") { saveReportEdit(client, tx) })
                            addView(miniAction("✕ Bekor", "#64748b") { cancelReportEdit(client) })
                        } else {
                            addView(miniAction("✎", "#2563eb") { startReportEdit(client, tx) })
                            addView(miniAction("🗑", "#ef4444") { confirmDeleteReportTx(client, tx) })
                        }
                    })
                }
            })
            addView(text(if ((tx.optJSONArray("lines")?.length() ?: 0) > 0) "$label ›" else label, 13).apply {
                setTextColor(color("#0f172a"))
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            })
            if (isEditing && tx.optString("turi") == "kirim") {
                addView(EditText(this@MainActivity).apply {
                    setText(editKirimAmountText)
                    setSingleLine(true)
                    inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                    gravity = Gravity.END
                    textSize = 13f
                    background = rounded("#ffffff", dp(5), strokeColor = "#2563eb")
                    setPadding(dp(6), 0, dp(6), 0)
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                            editKirimAmountText = s?.toString().orEmpty()
                        }
                        override fun afterTextChanged(s: Editable?) = Unit
                    })
                    layoutParams = LinearLayout.LayoutParams(0, dp(38), 1f)
                })
            } else {
                addView(text(formatAmount(amount), 13, bold = true).apply {
                    setTextColor(if (amount < 0) color("#0f766e") else color("#0f172a"))
                    gravity = Gravity.END
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
            }
            addView(text(formatAmount(tx.optDouble("balance")), 13, bold = true).apply {
                setTextColor(color("#0f172a"))
                gravity = Gravity.END
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            })
        }
    }

    private fun reportSaleLinesPanel(client: JSONObject, tx: JSONObject): LinearLayout {
        val lines = tx.optJSONArray("lines") ?: JSONArray()
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(8), dp(14), dp(8))
            setBackgroundColor(color("#f8fafc"))
            for (i in 0 until lines.length()) {
                val line = lines.getJSONObject(i)
                val lineId = line.optLong("id")
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(dp(4), dp(5), dp(4), dp(5))
                    addView(text(line.optString("name"), 12).apply {
                        setTextColor(color("#475569"))
                        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    })
                    if (editingReportTxnKey == reportTxnKey(tx)) {
                        addView(smallNumberInput((editSaleQty[lineId] ?: line.optDouble("qty")).toString()) {
                            editSaleQty[lineId] = parseAmount(it)
                        })
                        addView(text(" x ", 12))
                        addView(smallNumberInput(formatAmount(editSalePrice[lineId] ?: line.optDouble("price"))) {
                            editSalePrice[lineId] = parseAmount(it)
                        })
                    } else {
                        addView(text("${formatAmount(line.optDouble("qty"))} x ${formatAmount(line.optDouble("price"))} = ${formatAmount(line.optDouble("subtotal"))}", 12, bold = true).apply {
                            setTextColor(color("#1e293b"))
                        })
                    }
                })
            }
        }
    }

    private fun reportTxnKey(tx: JSONObject): String = "${tx.optString("turi")}:${tx.optLong("id")}"

    private fun miniAction(label: String, textColor: String, onClick: () -> Unit): TextView {
        return text(label, 12, bold = true).apply {
            setTextColor(color(textColor))
            setPadding(0, 0, dp(12), 0)
            setOnClickListener { onClick() }
        }
    }

    private fun smallNumberInput(value: String, onChange: (String) -> Unit): EditText {
        return EditText(this).apply {
            setText(value)
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            gravity = Gravity.CENTER_VERTICAL or Gravity.END
            textSize = 12f
            background = rounded("#ffffff", dp(4), strokeColor = "#2563eb")
            includeFontPadding = false
            setPadding(dp(6), dp(2), dp(6), 0)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = onChange(s?.toString().orEmpty())
                override fun afterTextChanged(s: Editable?) = Unit
            })
            layoutParams = LinearLayout.LayoutParams(dp(76), dp(40))
        }
    }

    private fun startReportEdit(client: JSONObject, tx: JSONObject) {
        captureClientReportScroll()
        editingReportTxnKey = reportTxnKey(tx)
        editKirimAmountText = formatAmount(tx.optDouble("summa"))
        editSaleQty.clear()
        editSalePrice.clear()
        tx.optJSONArray("lines")?.let { lines ->
            for (i in 0 until lines.length()) {
                val line = lines.getJSONObject(i)
                val lineId = line.optLong("id")
                editSaleQty[lineId] = line.optDouble("qty")
                editSalePrice[lineId] = line.optDouble("price")
            }
        }
        expandedReportTxnKeys.add(reportTxnKey(tx))
        renderClientReport(client)
    }

    private fun cancelReportEdit(client: JSONObject) {
        captureClientReportScroll()
        editingReportTxnKey = null
        editKirimAmountText = ""
        editSaleQty.clear()
        editSalePrice.clear()
        renderClientReport(client)
    }

    private fun saveReportEdit(client: JSONObject, tx: JSONObject) {
        if (tx.optString("turi") == "kirim") {
            val amount = parseAmount(editKirimAmountText)
            runReportMutation(client, "Saqlanmoqda...") {
                repository.editKirim(tx.optLong("id"), amount)
            }
            return
        }

        val linesPayload = JSONArray()
        val lines = tx.optJSONArray("lines") ?: JSONArray()
        for (i in 0 until lines.length()) {
            val line = lines.getJSONObject(i)
            val lineId = line.optLong("id")
            linesPayload.put(
                JSONObject()
                    .put("line_id", lineId)
                    .put("qty", editSaleQty[lineId] ?: line.optDouble("qty"))
                    .put("price", editSalePrice[lineId] ?: line.optDouble("price"))
            )
        }
        runReportMutation(client, "Saqlanmoqda...") {
            repository.editSotuv(tx.optLong("id"), linesPayload)
        }
    }

    private fun confirmDeleteReportTx(client: JSONObject, tx: JSONObject) {
        AlertDialog.Builder(this)
            .setMessage("Haqiqatan ham ushbu yozuvni o'chirmoqchimisiz?")
            .setNegativeButton("Bekor", null)
            .setPositiveButton("O'chirish") { _, _ ->
                runReportMutation(client, "O'chirilmoqda...") {
                    if (tx.optString("turi") == "kirim") {
                        repository.deleteKirim(tx.optLong("id"))
                    } else {
                        repository.deleteSotuv(tx.optLong("id"))
                    }
                }
            }
            .show()
    }

    private fun saveTelegramChatId(client: JSONObject, telegramChatId: String) {
        runReportMutation(client, "Telegram Chat ID saqlanmoqda...") {
            repository.updateClientTelegram(client.optLong("id"), telegramChatId)
        }
    }

    private fun runReportMutation(client: JSONObject, message: String, work: () -> Unit) {
        if (session.token.isBlank()) {
            status.text = "Online login kerak"
            return
        }
        status.text = message
        Thread {
            val error = try {
                work()
                null
            } catch (e: Exception) {
                e.message ?: "Tarmoq xatosi"
            }
            runOnUiThread {
                if (error == null) {
                    captureClientReportScroll()
                    editingReportTxnKey = null
                    editKirimAmountText = ""
                    editSaleQty.clear()
                    editSalePrice.clear()
                    status.text = "Saqlandi"
                    renderClientReport(db.client(client.optLong("id")) ?: client)
                } else {
                    status.text = "Error: $error"
                }
            }
        }.start()
    }

    private fun reportHeader(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(color("#eef2f7"))
            setPadding(dp(10), dp(10), dp(10), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(14), 0, 0) }
            listOf("SANA", "TURI", "SUMMA", "BALANS").forEach { title ->
                addView(text(title, 11, bold = true).apply {
                    setTextColor(color("#334155"))
                    layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                })
            }
        }
    }

    private fun screenPage(title: String, showMenu: Boolean = false): LinearLayout {
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color("#f1f3f6"))
        }
        page.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(10), dp(8), dp(10))
            setBackgroundColor(color("#2563eb"))
            addView(Button(this@MainActivity).apply {
                text = "←"
                textSize = 26f
                setTextColor(Color.WHITE)
                background = transparent()
                visibility = View.GONE
                setOnClickListener { renderPos() }
                layoutParams = LinearLayout.LayoutParams(0, 0)
            })
            addView(text(title, 18, bold = true).apply {
                setTextColor(Color.WHITE)
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            })
            addView(navBadge("● Online", "#1d4ed8", "#22c55e"))
            if (showMenu) {
                addView(Button(this@MainActivity).apply {
                    text = "⋮"
                    textSize = 24f
                    setTextColor(Color.WHITE)
                    background = transparent()
                    minWidth = 0
                    minimumWidth = 0
                    minHeight = 0
                    minimumHeight = 0
                    setPadding(0, 0, 0, 0)
                    setOnClickListener { showActionMenu(this) }
                    layoutParams = LinearLayout.LayoutParams(dp(36), dp(44))
                })
            } else {
                addView(View(this@MainActivity).apply { layoutParams = LinearLayout.LayoutParams(dp(44), dp(44)) })
            }
        })
        page.addView(ScrollView(this).apply {
            tag = "scroll_container"
            addView(LinearLayout(this@MainActivity).apply {
                tag = "body"
                orientation = LinearLayout.VERTICAL
                setPadding(dp(10), dp(10), dp(10), dp(24))
            })
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f
        ))
        return page
    }

    private fun emptyCard(message: String): TextView {
        return text(message, 14).apply {
            gravity = Gravity.CENTER
            setTextColor(color("#64748b"))
            background = rounded("#ffffff", dp(8), strokeColor = "#dbe3ef")
            setPadding(dp(10), dp(24), dp(10), dp(24))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        }
    }

    private fun menuItem(label: String, onClick: () -> Unit): TextView {
        return text(label, 15, bold = true).apply {
            setTextColor(color("#1f2937"))
            setPadding(dp(12), dp(12), dp(12), dp(12))
            setOnClickListener { onClick() }
        }
    }

    private fun actionMenuItem(icon: String, label: String, hex: String, onClick: () -> Unit): TextView {
        return text("$icon  $label", 13, bold = true).apply {
            setTextColor(color(hex))
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), dp(10), dp(8), dp(10))
            minHeight = dp(46)
            setLineSpacing(0f, 1.0f)
            setOnClickListener { onClick() }
        }
    }

    private fun menuDivider(): View {
        return View(this).apply {
            setBackgroundColor(color("#e5e7eb"))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(1)
            ).apply { setMargins(dp(8), dp(4), dp(8), dp(4)) }
        }
    }

    private fun summaryStrip(): LinearLayout {
        val c = db.counts()
        return card {
            addView(text("Clients: ${c["clients"]}  •  Inventory: ${c["inventory"]}  •  Pending: ${c["pending"]}", 13, bold = true).apply {
                setTextColor(color("#334155"))
            })
        }
    }

    private fun quickActions(): GridLayout {
        return GridLayout(this).apply {
            columnCount = 2
            setPadding(0, dp(4), 0, dp(8))
            addView(actionButton("Kirim", "#10b981") { renderPayment("kirim") })
            addView(actionButton("Chiqim", "#ef4444") { renderChiqimHistory() })
            addView(actionButton("So'rovlar", "#3b82f6") { renderRequestsList() })
            addView(actionButton("Yuklash", "#1e3a8a") { renderTripList() })
        }
    }

    private fun actionButton(label: String, hex: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = rounded(hex, dp(10))
            setOnClickListener { onClick() }
            layoutParams = GridLayout.LayoutParams().apply {
                width = 0
                height = dp(54)
                columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                setMargins(dp(4), dp(4), dp(4), dp(4))
            }
        }
    }

    private fun header(value: String): TextView = text(value, 24, bold = true)
    private fun sectionTitle(value: String): TextView = text(value, 18, bold = true).apply {
        setPadding(0, dp(18), 0, dp(8))
        setTextColor(color("#0f172a"))
    }
    private fun label(value: String): TextView = text(value, 13, bold = true).apply {
        setPadding(0, 0, 0, dp(4))
        setTextColor(color("#475569"))
    }

    private fun editText(hint: String, value: String, password: Boolean = false): EditText {
        return EditText(this).apply {
            this.hint = hint
            setText(value)
            textSize = 16f
            inputType = if (password) {
                InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            } else {
                InputType.TYPE_CLASS_TEXT
            }
        }
    }

    private fun button(label: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            setOnClickListener { onClick() }
        }
    }

    private fun primaryButton(label: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 14f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            background = rounded("#2563eb", dp(10))
            setOnClickListener { onClick() }
        }
    }

    private fun secondaryButton(label: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 13f
            setTextColor(color("#1f2937"))
            background = rounded("#ffffff", dp(8), strokeColor = "#d1d5db")
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f).apply {
                setMargins(dp(3), 0, dp(3), 0)
            }
        }
    }

    private fun compactSecondaryButton(label: String, onClick: () -> Unit): Button {
        return Button(this).apply {
            text = label
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(color("#475569"))
            background = rounded("#f8fafc", dp(8), strokeColor = "#cbd5e1")
            setPadding(dp(14), 0, dp(14), 0)
            minWidth = 0
            minimumWidth = 0
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(dp(92), dp(38))
        }
    }

    private fun dateField(value: String, onDateSelected: (String) -> Unit): EditText {
        return EditText(this).apply {
            hint = "Sana tanlang"
            setText(value)
            setSingleLine(true)
            textSize = 13f
            isFocusable = false
            isFocusableInTouchMode = false
            inputType = InputType.TYPE_NULL
            background = rounded("#ffffff", dp(4), strokeColor = "#facc15")
            setPadding(dp(8), 0, dp(8), 0)
            setOnClickListener { openDatePicker(text?.toString().orEmpty(), onDateSelected) }
        }
    }

    private fun openDatePicker(initialValue: String, onDateSelected: (String) -> Unit) {
        val calendar = Calendar.getInstance()
        parseFilterDate(initialValue)?.let { calendar.time = it }
        DatePickerDialog(
            this,
            { _, year, month, dayOfMonth ->
                onDateSelected(String.format(Locale.US, "%02d.%02d.%04d", dayOfMonth, month + 1, year))
            },
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH),
            calendar.get(Calendar.DAY_OF_MONTH)
        ).show()
    }

    private fun filterReportTransactions(source: JSONArray): JSONArray {
        if (reportDateFrom.isBlank() && reportDateTo.isBlank()) return source
        val fromDate = parseFilterDate(reportDateFrom)
        val toDate = parseFilterDate(reportDateTo)
        val filtered = JSONArray()
        for (i in 0 until source.length()) {
            val tx = source.getJSONObject(i)
            val txDate = parseTransactionDate(tx.optString("date_label")) ?: continue
            if (fromDate != null && txDate.before(startOfDay(fromDate))) continue
            if (toDate != null && txDate.after(endOfDay(toDate))) continue
            filtered.put(tx)
        }
        return filtered
    }

    private fun parseTransactionDate(value: String): Date? {
        val formats = listOf(
            "dd.MM.yyyy HH:mm:ss",
            "dd.MM.yyyy HH:mm",
            "dd.MM.yyyy",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm",
            "yyyy-MM-dd"
        )
        for (pattern in formats) {
            try {
                return SimpleDateFormat(pattern, Locale.US).apply { isLenient = false }.parse(value)
            } catch (_: Exception) {
            }
        }
        return null
    }

    private fun parseFilterDate(value: String): Date? {
        if (value.isBlank()) return null
        return try {
            SimpleDateFormat("dd.MM.yyyy", Locale.US).apply { isLenient = false }.parse(value)
        } catch (_: Exception) {
            null
        }
    }

    private fun startOfDay(date: Date): Date {
        return Calendar.getInstance().apply {
            time = date
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }.time
    }

    private fun endOfDay(date: Date): Date {
        return Calendar.getInstance().apply {
            time = date
            set(Calendar.HOUR_OF_DAY, 23)
            set(Calendar.MINUTE, 59)
            set(Calendar.SECOND, 59)
            set(Calendar.MILLISECOND, 999)
        }.time
    }

    private fun rememberNavigation(screen: ScreenState) {
        currentScreenState = screen
        session.selectedClientId = selectedClientId
        session.selectedClientName = selectedClientName
        session.lastScreen = screen.name
        session.lastReportClientId = activeReportClientId
        session.lastReportDateFrom = reportDateFrom
        session.lastReportDateTo = reportDateTo
        session.lastAgentReportDateFrom = agentReportDateFrom
        session.lastAgentReportDateTo = agentReportDateTo
        session.lastAgentReportTab = agentReportTab
    }

    private fun restoreLastScreen() {
        when (runCatching { ScreenState.valueOf(session.lastScreen) }.getOrDefault(ScreenState.POS)) {
            ScreenState.LOGIN -> renderLogin()
            ScreenState.CLIENT_SELECTION -> renderClientSelection()
            ScreenState.REQUEST_LIST -> renderRequestsList()
            ScreenState.REQUEST_FORM -> renderRequestForm()
            ScreenState.REQUEST_DETAILS -> {
                val req = db.rows("requests", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeRequestId }
                }
                if (req != null) renderRequestDetails(req, resetDraft = false) else renderRequestsList()
            }
            ScreenState.REQUEST_ADD_PRODUCT -> {
                val req = db.rows("requests", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeRequestId }
                }
                if (req != null) openRequestAddProductDialog(req) else renderRequestsList()
            }
            ScreenState.KIRIM_HISTORY -> renderKirimHistory()
            ScreenState.CHIQIM_HISTORY -> renderChiqimHistory()
            ScreenState.TRIP_LIST -> renderTripList()
            ScreenState.TRIP_DETAILS -> {
                val trip = db.rows("trips", "id DESC").let { rows ->
                    (0 until rows.length())
                        .map { rows.getJSONObject(it) }
                        .firstOrNull { it.optLong("id") == activeTripId }
                }
                if (trip != null) renderTripDetails(trip) else renderTripList()
            }
            ScreenState.TRIP_FORM -> renderTripForm()
            ScreenState.CLIENT_REPORT -> {
                val client = db.client(activeReportClientId)
                if (client != null && activeReportClientId != 0L) {
                    renderClientReport(client)
                } else {
                    renderClientSelection()
                }
            }
            ScreenState.AGENT_REPORT -> renderAgentReport()
            else -> renderPos()
        }
    }

    private fun formatAmount(value: Double): String {
        return String.format(Locale.US, "%,.0f", value)
    }

    private fun formatTripDateLabel(value: String): String {
        return parseTransactionDate(value)?.let {
            SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).format(it)
        } ?: value
    }

    private fun tripStateLabel(state: String): String {
        return when (state) {
            "validated" -> "Tasdiqlangan"
            "draft" -> "Qoralama"
            else -> state.ifBlank { "-" }
        }
    }

    private fun tripStateBg(state: String): String {
        return when (state) {
            "validated" -> "#ecfdf5"
            "draft" -> "#eff6ff"
            else -> "#f3f4f6"
        }
    }

    private fun tripStateFg(state: String): String {
        return when (state) {
            "validated" -> "#10b981"
            "draft" -> "#3b82f6"
            else -> "#64748b"
        }
    }

    private fun requestStateLabel(state: String): String {
        return when (state) {
            "done" -> "Bajarildi"
            "cancel" -> "Bekor"
            else -> "Kutilmoqda"
        }
    }

    private fun requestStateBg(state: String): String {
        return when (state) {
            "done" -> "#ecfdf5"
            "cancel" -> "#f3f4f6"
            else -> "#eff6ff"
        }
    }

    private fun requestStateFg(state: String): String {
        return when (state) {
            "done" -> "#10b981"
            "cancel" -> "#6b7280"
            else -> "#3b82f6"
        }
    }

    private fun resetSelectedClientToCash() {
        selectedClientId = 0L
        selectedClientName = "Naqt savdo"
        sourceRequestId = 0L
    }

    private fun chiqimExpenseLabel(expenseType: String): String {
        return when (expenseType) {
            "salary" -> "Oylik (Oylikdan)"
            else -> "Kunlik (Biznes)"
        }
    }

    private fun formatPendingTransactionDate(timestamp: Long): String {
        return SimpleDateFormat("dd.MM.yyyy HH:mm:ss", Locale.US).format(Date(timestamp))
    }

    private fun parseAmount(value: String): Double {
        return value.replace(",", "").trim().toDoubleOrNull() ?: 0.0
    }

    private fun text(value: String, size: Int, bold: Boolean = false): TextView {
        return TextView(this).apply {
            text = value
            textSize = size.toFloat()
            gravity = Gravity.START
            if (bold) typeface = android.graphics.Typeface.DEFAULT_BOLD
        }
    }

    private fun card(content: LinearLayout.() -> Unit): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded("#ffffff", dp(8), strokeColor = "#e5e7eb")
            setPadding(dp(12), dp(12), dp(12), dp(12))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, dp(6), 0, dp(10)) }
            content()
        }
    }

    private fun navBadge(label: String, bg: String, fg: String): TextView {
        return text(label, 11, bold = true).apply {
            setTextColor(color(fg))
            background = rounded(bg, dp(12))
            setPadding(dp(8), dp(4), dp(8), dp(4))
        }
    }

    private fun rounded(fill: String, radius: Int, strokeColor: String? = null): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius.toFloat()
            setColor(color(fill))
            if (strokeColor != null) setStroke(dp(1), color(strokeColor))
        }
    }

    private fun transparent(): GradientDrawable {
        return GradientDrawable().apply { setColor(Color.TRANSPARENT) }
    }

    private fun color(hex: String): Int = Color.parseColor(hex)
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun space(): View {
        return View(this).apply {
            layoutParams = LinearLayout.LayoutParams(1, 24)
        }
    }

    private data class CartLine(
        val productId: Long,
        val name: String,
        var qty: Double,
        var price: Double
    )

    private data class KirimHistoryItem(
        val id: Long,
        val offlineId: String = "",
        val clientId: Long,
        val clientName: String,
        val dateLabel: String,
        val amount: Double,
        val balance: Double,
        val isPending: Boolean = false,
        val sortTime: Long = 0L,
    )

    private data class ChiqimHistoryItem(
        val id: Long,
        val offlineId: String = "",
        val dateLabel: String,
        val amount: Double,
        val note: String,
        val expenseType: String,
        val isPending: Boolean = false,
        val sortTime: Long = 0L,
    )

    private data class TripDraftLine(
        val productId: Long,
        val name: String,
        val qty: Int,
        val price: Double,
    )

    private data class RequestDraftLine(
        val productId: Long,
        val name: String,
        val qty: Int,
        val price: Double,
    )

    private data class RequestEditLine(
        val productId: Long,
        val productName: String,
        var qty: Int,
        var price: Double,
        val imageUrl: String = "",
    )

    private data class AgentMetric(
        val label: String,
        val value: String,
        val fg: String,
        val bg: String,
    )

    private data class AgentSaleItem(
        val id: Long,
        val name: String,
        val dateLabel: String,
        val clientName: String,
        val amount: Double,
        val state: String,
        val isCash: Boolean,
        val profit: Double,
        val sortTime: Long = 0L,
    )

    private data class AgentPaymentItem(
        val id: Long,
        val name: String,
        val dateLabel: String,
        val partnerName: String,
        val amount: Double,
        val state: String,
        val note: String,
        val paymentMethod: String,
        val expenseType: String,
        val sortTime: Long = 0L,
    )

    private data class AgentReportSnapshot(
        val sales: List<AgentSaleItem>,
        val kirims: List<AgentPaymentItem>,
        val chiqims: List<AgentPaymentItem>,
        val salaryPayments: List<AgentPaymentItem>,
        val salesCount: Int,
        val totalSales: Double,
        val totalCash: Double,
        val totalNasiya: Double,
        val jamiNasiya: Double,
        val totalChiqim: Double,
        val sofBalans: Double,
        val yalpiBalans: Double,
        val totalFoyda: Double,
        val earnedSalary: Double,
        val salaryTaken: Double,
        val salaryLeft: Double,
        val agentKeeps: Double,
    )

    private data class ClientItem(val id: Long, val name: String) {
        override fun toString(): String = name
    }
}
