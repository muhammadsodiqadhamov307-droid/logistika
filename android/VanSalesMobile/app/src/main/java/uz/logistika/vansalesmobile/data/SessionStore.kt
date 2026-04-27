package uz.logistika.vansalesmobile.data

import android.content.Context

class SessionStore(context: Context) {
    private val prefs = context.getSharedPreferences("van_sales_session", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString("base_url", "") ?: ""
        set(value) = prefs.edit().putString("base_url", value.trimEnd('/')).apply()

    var token: String
        get() = prefs.getString("token", "") ?: ""
        set(value) = prefs.edit().putString("token", value).apply()

    var database: String
        get() = prefs.getString("database", "") ?: ""
        set(value) = prefs.edit().putString("database", value).apply()

    var login: String
        get() = prefs.getString("login", "") ?: ""
        set(value) = prefs.edit().putString("login", value).apply()

    var selectedClientId: Long
        get() = prefs.getLong("selected_client_id", 0L)
        set(value) = prefs.edit().putLong("selected_client_id", value).apply()

    var selectedClientName: String
        get() = prefs.getString("selected_client_name", "Naqt savdo") ?: "Naqt savdo"
        set(value) = prefs.edit().putString("selected_client_name", value).apply()

    var selectedAgentId: Long
        get() = prefs.getLong("selected_agent_id", 0L)
        set(value) = prefs.edit().putLong("selected_agent_id", value).apply()

    var selectedAgentName: String
        get() = prefs.getString("selected_agent_name", "") ?: ""
        set(value) = prefs.edit().putString("selected_agent_name", value).apply()

    var lastScreen: String
        get() = prefs.getString("last_screen", "POS") ?: "POS"
        set(value) = prefs.edit().putString("last_screen", value).apply()

    var lastReportClientId: Long
        get() = prefs.getLong("last_report_client_id", 0L)
        set(value) = prefs.edit().putLong("last_report_client_id", value).apply()

    var lastReportDateFrom: String
        get() = prefs.getString("last_report_date_from", "") ?: ""
        set(value) = prefs.edit().putString("last_report_date_from", value).apply()

    var lastReportDateTo: String
        get() = prefs.getString("last_report_date_to", "") ?: ""
        set(value) = prefs.edit().putString("last_report_date_to", value).apply()

    var lastAgentReportDateFrom: String
        get() = prefs.getString("last_agent_report_date_from", "") ?: ""
        set(value) = prefs.edit().putString("last_agent_report_date_from", value).apply()

    var lastAgentReportDateTo: String
        get() = prefs.getString("last_agent_report_date_to", "") ?: ""
        set(value) = prefs.edit().putString("last_agent_report_date_to", value).apply()

    var lastAgentReportTab: String
        get() = prefs.getString("last_agent_report_tab", "sales") ?: "sales"
        set(value) = prefs.edit().putString("last_agent_report_tab", value).apply()

    fun clearAuth() {
        prefs.edit()
            .remove("token")
            .remove("selected_client_id")
            .remove("selected_client_name")
            .remove("selected_agent_id")
            .remove("selected_agent_name")
            .remove("last_screen")
            .remove("last_report_client_id")
            .remove("last_report_date_from")
            .remove("last_report_date_to")
            .remove("last_agent_report_date_from")
            .remove("last_agent_report_date_to")
            .remove("last_agent_report_tab")
            .apply()
    }
}
