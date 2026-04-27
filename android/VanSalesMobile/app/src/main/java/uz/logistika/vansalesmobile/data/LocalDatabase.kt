package uz.logistika.vansalesmobile.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject

class LocalDatabase(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE agent (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                summary_id INTEGER,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                balance REAL DEFAULT 0,
                total_due REAL DEFAULT 0,
                is_cash_sale INTEGER DEFAULT 0,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE client_reports (
                client_id INTEGER PRIMARY KEY,
                client_name TEXT NOT NULL,
                total_due REAL DEFAULT 0,
                telegram_chat_id TEXT,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE inventory (
                product_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL DEFAULT 0,
                remaining REAL DEFAULT 0,
                image_url TEXT,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL DEFAULT 0,
                cost_price REAL DEFAULT 0,
                image_url TEXT,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE suppliers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                partner_id INTEGER,
                partner_name TEXT,
                state TEXT,
                total_amount REAL DEFAULT 0,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE trips (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                state TEXT,
                total_cost REAL DEFAULT 0,
                total_qty REAL DEFAULT 0,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                payment_type TEXT NOT NULL,
                amount REAL DEFAULT 0,
                note TEXT,
                expense_type TEXT,
                partner_id INTEGER,
                partner_name TEXT,
                state TEXT,
                raw_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE sync_queue (
                offline_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS agent")
        db.execSQL("DROP TABLE IF EXISTS clients")
        db.execSQL("DROP TABLE IF EXISTS client_reports")
        db.execSQL("DROP TABLE IF EXISTS inventory")
        db.execSQL("DROP TABLE IF EXISTS products")
        db.execSQL("DROP TABLE IF EXISTS suppliers")
        db.execSQL("DROP TABLE IF EXISTS requests")
        db.execSQL("DROP TABLE IF EXISTS trips")
        db.execSQL("DROP TABLE IF EXISTS payments")
        db.execSQL("DROP TABLE IF EXISTS sync_queue")
        onCreate(db)
    }

    fun applyBootstrap(payload: JSONObject) {
        writableDatabase.use { db ->
            db.beginTransaction()
            try {
                payload.optJSONObject("agent")?.let { upsertAgent(db, it) }
                replaceClients(db, payload.optJSONArray("clients") ?: JSONArray())
                replaceClientReports(db, payload.optJSONArray("client_reports") ?: JSONArray())
                replaceInventory(db, payload.optJSONArray("inventory") ?: JSONArray())
                replaceProducts(db, payload.optJSONArray("products") ?: JSONArray())
                replaceSuppliers(db, payload.optJSONArray("taminotchis") ?: JSONArray())
                replaceRequests(db, payload.optJSONArray("requests") ?: JSONArray())
                replaceTrips(db, payload.optJSONArray("trips") ?: JSONArray())
                replacePayments(db, payload.optJSONArray("payments") ?: JSONArray())
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        }
    }

    fun enqueueTransaction(type: String, offlineId: String, payload: JSONObject) {
        val now = System.currentTimeMillis()
        val values = ContentValues().apply {
            put("offline_id", offlineId)
            put("type", type)
            put("payload_json", payload.toString())
            put("status", "pending")
            put("created_at", now)
            put("updated_at", now)
        }
        writableDatabase.insertWithOnConflict("sync_queue", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun pendingTransactions(): JSONArray {
        val result = JSONArray()
        readableDatabase.rawQuery(
            "SELECT offline_id, type, payload_json, created_at FROM sync_queue WHERE status = 'pending' ORDER BY created_at ASC",
            emptyArray()
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val payload = JSONObject(cursor.getString(2))
                result.put(
                    JSONObject()
                        .put("offline_id", cursor.getString(0))
                        .put("type", cursor.getString(1))
                        .put("timestamp", cursor.getLong(3))
                        .put("data", payload)
                )
            }
        }
        return result
    }

    fun updatePendingTransactionAmount(offlineId: String, amount: Double) {
        writableDatabase.use { db ->
            db.rawQuery(
                "SELECT payload_json FROM sync_queue WHERE offline_id = ? AND status = 'pending'",
                arrayOf(offlineId)
            ).use { cursor ->
                if (!cursor.moveToFirst()) return
                val payload = JSONObject(cursor.getString(0)).put("amount", amount)
                val values = ContentValues().apply {
                    put("payload_json", payload.toString())
                    put("updated_at", System.currentTimeMillis())
                }
                db.update("sync_queue", values, "offline_id = ?", arrayOf(offlineId))
            }
        }
    }

    fun updatePendingPayment(offlineId: String, amount: Double, note: String, expenseType: String) {
        writableDatabase.use { db ->
            db.rawQuery(
                "SELECT payload_json FROM sync_queue WHERE offline_id = ? AND status = 'pending'",
                arrayOf(offlineId)
            ).use { cursor ->
                if (!cursor.moveToFirst()) return
                val payload = JSONObject(cursor.getString(0))
                    .put("amount", amount)
                    .put("note", note)
                    .put("expense_type", expenseType)
                val values = ContentValues().apply {
                    put("payload_json", payload.toString())
                    put("updated_at", System.currentTimeMillis())
                }
                db.update("sync_queue", values, "offline_id = ?", arrayOf(offlineId))
            }
        }
    }

    fun deletePendingTransaction(offlineId: String) {
        writableDatabase.delete("sync_queue", "offline_id = ? AND status = 'pending'", arrayOf(offlineId))
    }

    fun markSynced(offlineIds: JSONArray) {
        writableDatabase.use { db ->
            db.beginTransaction()
            try {
                for (i in 0 until offlineIds.length()) {
                    db.delete("sync_queue", "offline_id = ?", arrayOf(offlineIds.getString(i)))
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        }
    }

    fun rows(table: String, orderBy: String): JSONArray {
        val result = JSONArray()
        if (table == "inventory") {
            readableDatabase.rawQuery("SELECT raw_json, remaining, price FROM inventory ORDER BY $orderBy", emptyArray()).use { cursor ->
                while (cursor.moveToNext()) {
                    result.put(
                        JSONObject(cursor.getString(0))
                            .put("remaining", cursor.getDouble(1))
                            .put("price", cursor.getDouble(2))
                    )
                }
            }
            return result
        }
        readableDatabase.rawQuery("SELECT raw_json FROM $table ORDER BY $orderBy", emptyArray()).use { cursor ->
            while (cursor.moveToNext()) {
                result.put(JSONObject(cursor.getString(0)))
            }
        }
        return result
    }

    fun clientReport(clientId: Long): JSONObject? {
        readableDatabase.rawQuery(
            "SELECT raw_json FROM client_reports WHERE client_id = ?",
            arrayOf(clientId.toString())
        ).use { cursor ->
            return if (cursor.moveToFirst()) JSONObject(cursor.getString(0)) else null
        }
    }

    fun client(clientId: Long): JSONObject? {
        readableDatabase.rawQuery(
            "SELECT raw_json FROM clients WHERE id = ?",
            arrayOf(clientId.toString())
        ).use { cursor ->
            return if (cursor.moveToFirst()) JSONObject(cursor.getString(0)) else null
        }
    }

    fun agent(): JSONObject? {
        readableDatabase.rawQuery(
            "SELECT raw_json FROM agent ORDER BY updated_at DESC LIMIT 1",
            emptyArray()
        ).use { cursor ->
            return if (cursor.moveToFirst()) JSONObject(cursor.getString(0)) else null
        }
    }

    fun reduceInventory(productId: Long, qty: Double) {
        writableDatabase.use { db ->
            db.beginTransaction()
            try {
                db.rawQuery(
                    "SELECT raw_json, remaining FROM inventory WHERE product_id = ?",
                    arrayOf(productId.toString())
                ).use { cursor ->
                    if (cursor.moveToFirst()) {
                        val newRemaining = (cursor.getDouble(1) - qty).coerceAtLeast(0.0)
                        val raw = JSONObject(cursor.getString(0)).put("remaining", newRemaining)
                        val values = ContentValues().apply {
                            put("remaining", newRemaining)
                            put("raw_json", raw.toString())
                            put("updated_at", System.currentTimeMillis())
                        }
                        db.update("inventory", values, "product_id = ?", arrayOf(productId.toString()))
                    }
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        }
    }

    fun counts(): Map<String, Int> {
        return mapOf(
            "clients" to count("clients"),
            "inventory" to count("inventory"),
            "products" to count("products"),
            "requests" to count("requests"),
            "trips" to count("trips"),
            "pending" to count("sync_queue", "status = 'pending'")
        )
    }

    private fun upsertAgent(db: SQLiteDatabase, agent: JSONObject) {
        val values = ContentValues().apply {
            put("id", agent.optLong("id"))
            put("name", agent.optString("name"))
            put("phone", agent.optString("phone"))
            put("summary_id", agent.optLong("summary_id"))
            put("raw_json", agent.toString())
            put("updated_at", System.currentTimeMillis())
        }
        db.insertWithOnConflict("agent", null, values, SQLiteDatabase.CONFLICT_REPLACE)
    }

    private fun replaceClients(db: SQLiteDatabase, items: JSONArray) {
        db.delete("clients", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("id", it.optLong("id"))
                put("name", it.optString("name"))
                put("balance", it.optDouble("balance"))
                put("total_due", it.optDouble("total_due"))
                put("is_cash_sale", if (it.optBoolean("is_cash_sale")) 1 else 0)
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("clients", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceClientReports(db: SQLiteDatabase, items: JSONArray) {
        db.delete("client_reports", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("client_id", it.optLong("client_id"))
                put("client_name", it.optString("client_name"))
                put("total_due", it.optDouble("total_due"))
                put("telegram_chat_id", it.optString("telegram_chat_id"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("client_reports", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceInventory(db: SQLiteDatabase, items: JSONArray) {
        db.delete("inventory", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("product_id", it.optLong("product_id"))
                put("name", it.optString("name"))
                put("price", it.optDouble("price"))
                put("remaining", it.optDouble("remaining"))
                put("image_url", it.optString("image_url"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("inventory", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceProducts(db: SQLiteDatabase, items: JSONArray) {
        db.delete("products", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("product_id", it.optLong("product_id"))
                put("name", it.optString("name"))
                put("price", it.optDouble("price"))
                put("cost_price", it.optDouble("cost_price"))
                put("image_url", it.optString("image_url"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("products", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceSuppliers(db: SQLiteDatabase, items: JSONArray) {
        db.delete("suppliers", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("id", it.optLong("id"))
                put("name", it.optString("name"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("suppliers", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceRequests(db: SQLiteDatabase, items: JSONArray) {
        db.delete("requests", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("id", it.optLong("id"))
                put("name", it.optString("name"))
                put("partner_id", it.optLong("partner_id"))
                put("partner_name", it.optString("partner_name"))
                put("state", it.optString("state"))
                put("total_amount", it.optDouble("total_amount"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("requests", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replaceTrips(db: SQLiteDatabase, items: JSONArray) {
        db.delete("trips", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("id", it.optLong("id"))
                put("name", it.optString("name"))
                put("state", it.optString("state"))
                put("total_cost", it.optDouble("total_cost"))
                put("total_qty", it.optDouble("total_qty"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("trips", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun replacePayments(db: SQLiteDatabase, items: JSONArray) {
        db.delete("payments", null, null)
        forEach(items) {
            val values = ContentValues().apply {
                put("id", it.optLong("id"))
                put("payment_type", it.optString("payment_type"))
                put("amount", it.optDouble("amount"))
                put("note", it.optString("note"))
                put("expense_type", it.optString("expense_type"))
                put("partner_id", it.optLong("partner_id"))
                put("partner_name", it.optString("partner_name"))
                put("state", it.optString("state"))
                put("raw_json", it.toString())
                put("updated_at", System.currentTimeMillis())
            }
            db.insertWithOnConflict("payments", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        }
    }

    private fun count(table: String, where: String? = null): Int {
        val sql = if (where == null) "SELECT COUNT(*) FROM $table" else "SELECT COUNT(*) FROM $table WHERE $where"
        readableDatabase.rawQuery(sql, emptyArray()).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
    }

    private fun forEach(array: JSONArray, block: (JSONObject) -> Unit) {
        for (i in 0 until array.length()) {
            block(array.getJSONObject(i))
        }
    }

    companion object {
        private const val DB_NAME = "van_sales_mobile.db"
        private const val DB_VERSION = 4
    }
}
