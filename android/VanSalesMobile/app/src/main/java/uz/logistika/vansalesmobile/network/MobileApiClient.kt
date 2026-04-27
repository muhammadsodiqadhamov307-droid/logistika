package uz.logistika.vansalesmobile.network

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class MobileApiClient(
    private val baseUrl: String,
    private val database: String = ""
) {
    fun login(database: String, login: String, password: String): JSONObject {
        return call(
            "/van/mobile/api/login",
            JSONObject()
                .put("db", database)
                .put("login", login)
                .put("password", password),
            token = null
        )
    }

    fun bootstrap(token: String): JSONObject {
        return call("/van/mobile/api/bootstrap", JSONObject(), token)
    }

    fun sync(token: String, transactions: JSONArray): JSONObject {
        return call(
            "/van/mobile/api/sync",
            JSONObject().put("transactions", transactions),
            token
        )
    }

    fun updateClientTelegram(token: String, clientId: Long, telegramChatId: String): JSONObject {
        return call(
            "/van/mobile/api/update-client-telegram",
            JSONObject()
                .put("client_id", clientId)
                .put("telegram_chat_id", telegramChatId),
            token
        )
    }

    fun createClient(token: String, name: String, phone: String, telegramChatId: String): JSONObject {
        return call(
            "/van/mobile/api/create-client",
            JSONObject()
                .put("name", name)
                .put("phone", phone)
                .put("telegram_chat_id", telegramChatId),
            token
        )
    }

    fun createTrip(token: String, date: String, note: String, lines: JSONArray, taminotchiId: Long?): JSONObject {
        val params = JSONObject()
            .put("date", date)
            .put("note", note)
            .put("lines", lines)
        if (taminotchiId != null && taminotchiId > 0L) {
            params.put("taminotchi_id", taminotchiId)
        }
        return call("/van/mobile/api/create-trip", params, token)
    }

    fun createRequest(token: String, partnerId: Long, lines: JSONArray, notes: String): JSONObject {
        return call(
            "/van/mobile/api/create-request",
            JSONObject()
                .put("partner_id", partnerId)
                .put("lines", lines)
                .put("notes", notes),
            token
        )
    }

    fun updateRequestState(token: String, requestId: Long, state: String): JSONObject {
        return call(
            "/van/mobile/api/update-request-state",
            JSONObject()
                .put("request_id", requestId)
                .put("state", state),
            token
        )
    }

    fun updateRequest(token: String, requestId: Long, lines: JSONArray): JSONObject {
        return call(
            "/van/mobile/api/update-request",
            JSONObject()
                .put("request_id", requestId)
                .put("lines", lines),
            token
        )
    }

    fun rebuildInventory(token: String): JSONObject {
        return call("/van/mobile/api/rebuild-inventory", JSONObject(), token)
    }

    fun editKirim(token: String, paymentId: Long, amount: Double): JSONObject {
        return call(
            "/van/mobile/api/edit-kirim",
            JSONObject()
                .put("payment_id", paymentId)
                .put("new_amount", amount),
            token
        )
    }

    fun deleteKirim(token: String, paymentId: Long): JSONObject {
        return call(
            "/van/mobile/api/delete-kirim",
            JSONObject().put("payment_id", paymentId),
            token
        )
    }

    fun editChiqim(token: String, paymentId: Long, amount: Double, note: String, expenseType: String): JSONObject {
        return call(
            "/van/mobile/api/edit-chiqim",
            JSONObject()
                .put("payment_id", paymentId)
                .put("new_amount", amount)
                .put("note", note)
                .put("expense_type", expenseType),
            token
        )
    }

    fun deleteChiqim(token: String, paymentId: Long): JSONObject {
        return call(
            "/van/mobile/api/delete-chiqim",
            JSONObject().put("payment_id", paymentId),
            token
        )
    }

    fun editSotuv(token: String, orderId: Long, lines: JSONArray): JSONObject {
        return call(
            "/van/mobile/api/edit-sotuv",
            JSONObject()
                .put("order_id", orderId)
                .put("lines", lines),
            token
        )
    }

    fun deleteSotuv(token: String, orderId: Long): JSONObject {
        return call(
            "/van/mobile/api/delete-sotuv",
            JSONObject().put("order_id", orderId),
            token
        )
    }

    private fun call(path: String, params: JSONObject, token: String?): JSONObject {
        val normalizedBase = baseUrl.trimEnd('/')
        val dbQuery = if (database.isBlank()) {
            ""
        } else {
            "?db=${URLEncoder.encode(database, "UTF-8")}"
        }
        val connection = (URL("$normalizedBase$path$dbQuery").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15000
            readTimeout = 30000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            if (!token.isNullOrBlank()) {
                setRequestProperty("Authorization", "Bearer $token")
            }
        }

        val body = JSONObject()
            .put("jsonrpc", "2.0")
            .put("method", "call")
            .put("params", params)
            .put("id", System.currentTimeMillis())

        OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(body.toString())
        }

        val responseCode = connection.responseCode
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        val responseText = BufferedReader(stream.reader(Charsets.UTF_8)).use { it.readText() }
        val envelope = JSONObject(responseText)

        if (envelope.has("error")) {
            throw IllegalStateException(envelope.getJSONObject("error").toString())
        }

        val result = envelope.optJSONObject("result")
            ?: throw IllegalStateException("Missing JSON-RPC result")

        if (!result.optBoolean("success", false)) {
            throw IllegalStateException(result.optString("error", "Mobile API request failed"))
        }

        return result
    }
}
