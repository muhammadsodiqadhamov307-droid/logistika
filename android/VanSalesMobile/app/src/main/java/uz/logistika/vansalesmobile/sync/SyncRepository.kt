package uz.logistika.vansalesmobile.sync

import org.json.JSONArray
import org.json.JSONObject
import uz.logistika.vansalesmobile.data.LocalDatabase
import uz.logistika.vansalesmobile.data.SessionStore
import uz.logistika.vansalesmobile.network.MobileApiClient
import java.util.UUID

class SyncRepository(
    private val db: LocalDatabase,
    private val session: SessionStore
) {
    private fun rememberBootstrap(bootstrap: JSONObject) {
        db.applyBootstrap(bootstrap)
        bootstrap.optJSONObject("agent")?.let { agent ->
            val actingId = agent.optLong("acting_agent_id", agent.optLong("id"))
            if (actingId > 0L) {
                session.selectedAgentId = actingId
                session.selectedAgentName = agent.optString("acting_agent_name").ifBlank { agent.optString("name") }
            }
        }
    }

    fun login(baseUrl: String, database: String, login: String, password: String): JSONObject {
        session.baseUrl = baseUrl
        session.database = database
        session.login = login
        val result = MobileApiClient(session.baseUrl, database, session.selectedAgentId).login(database, login, password)
        session.token = result.getString("token")
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun bootstrap(): JSONObject {
        require(session.token.isNotBlank()) { "Login required" }
        val result = MobileApiClient(session.baseUrl, session.database, session.selectedAgentId).bootstrap(session.token)
        rememberBootstrap(result)
        return result
    }

    fun syncPending(): JSONObject {
        require(session.token.isNotBlank()) { "Login required" }
        val pending = db.pendingTransactions()
        if (pending.length() == 0) {
            return JSONObject().put("success", true).put("message", "No pending transactions")
        }
        val result = MobileApiClient(session.baseUrl, session.database, session.selectedAgentId).sync(session.token, pending)
        db.markSynced(result.optJSONArray("synced") ?: org.json.JSONArray())
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun updateClientTelegram(clientId: Long, telegramChatId: String): JSONObject {
        val result = client().updateClientTelegram(session.token, clientId, telegramChatId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun createClient(name: String, phone: String, telegramChatId: String): JSONObject {
        val result = client().createClient(session.token, name, phone, telegramChatId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun createTrip(date: String, note: String, lines: JSONArray, taminotchiId: Long?): JSONObject {
        val result = client().createTrip(session.token, date, note, lines, taminotchiId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun createRequest(partnerId: Long, lines: JSONArray, notes: String): JSONObject {
        val result = client().createRequest(session.token, partnerId, lines, notes)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun updateRequestState(requestId: Long, state: String): JSONObject {
        val result = client().updateRequestState(session.token, requestId, state)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun updateRequest(requestId: Long, lines: JSONArray): JSONObject {
        val result = client().updateRequest(session.token, requestId, lines)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun rebuildInventory(): JSONObject {
        val result = client().rebuildInventory(session.token)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun editKirim(paymentId: Long, amount: Double): JSONObject {
        val result = client().editKirim(session.token, paymentId, amount)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun deleteKirim(paymentId: Long): JSONObject {
        val result = client().deleteKirim(session.token, paymentId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun editChiqim(paymentId: Long, amount: Double, note: String, expenseType: String): JSONObject {
        val result = client().editChiqim(session.token, paymentId, amount, note, expenseType)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun deleteChiqim(paymentId: Long): JSONObject {
        val result = client().deleteChiqim(session.token, paymentId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun editSotuv(orderId: Long, lines: JSONArray): JSONObject {
        val result = client().editSotuv(session.token, orderId, lines)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun deleteSotuv(orderId: Long): JSONObject {
        val result = client().deleteSotuv(session.token, orderId)
        result.optJSONObject("bootstrap")?.let { rememberBootstrap(it) }
        return result
    }

    fun switchActingAgent(agentId: Long): JSONObject {
        val previousId = session.selectedAgentId
        val previousName = session.selectedAgentName
        session.selectedAgentId = agentId
        return try {
            val result = MobileApiClient(session.baseUrl, session.database, session.selectedAgentId).bootstrap(session.token)
            rememberBootstrap(result)
            result
        } catch (e: Exception) {
            session.selectedAgentId = previousId
            session.selectedAgentName = previousName
            throw e
        }
    }

    fun enqueueDemoCashSale(productId: Long, qty: Double, price: Double) {
        val payload = JSONObject()
            .put("partner_id", false)
            .put(
                "lines",
                org.json.JSONArray().put(
                    JSONObject()
                        .put("product_id", productId)
                        .put("qty", qty)
                        .put("price", price)
                )
            )
        db.enqueueTransaction("sale", UUID.randomUUID().toString(), payload)
    }

    private fun client(): MobileApiClient {
        require(session.token.isNotBlank()) { "Login required" }
        return MobileApiClient(session.baseUrl, session.database, session.selectedAgentId)
    }
}
