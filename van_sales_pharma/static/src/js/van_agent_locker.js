/** @odoo-module **/

import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

if (session.is_van_agent) {
    const expectedHash = "#action=van_sales_pharma.action_van_mobile_pos";

    // 1. Immediate Hash Change
    if (browser.location.hash !== expectedHash) {
        browser.location.replace('/web' + expectedHash);
    }

    // 2. Prevent navigating away
    window.addEventListener("hashchange", () => {
        if (browser.location.hash !== expectedHash) {
            browser.location.replace('/web' + expectedHash);
        }
    });

    // 3. Patch Action Service to block everything else
    registry.category("services").add("van_agent_locker", {
        dependencies: ["action"],
        start(env, { action }) {
            const originalDoAction = action.doAction.bind(action);
            action.doAction = (actionRequest, options) => {
                // If it's a string, it might be an xml_id
                let actionTag = actionRequest;
                if (typeof actionRequest === 'object' && actionRequest !== null) {
                    actionTag = actionRequest.tag || actionRequest.xml_id;
                }

                // Allow the mobile POS client action, login/logout routes
                if (
                    actionRequest === 'van_sales_pharma.action_van_mobile_pos' ||
                    actionTag === 'van_sales_pharma.MobilePosClientAction' ||
                    actionTag === 'reload'
                ) {
                    return originalDoAction(actionRequest, options);
                }

                // Block everything else and force POS
                console.warn("Blocked agent from opening action:", actionRequest);
                return originalDoAction('van_sales_pharma.action_van_mobile_pos', options);
            };
        }
    });

    // 4. Hide the Odoo main navbar completely for agents
    const style = document.createElement('style');
    style.innerHTML = `
        .o_main_navbar { display: none !important; }
        .o_web_client { padding-top: 0 !important; }
        .o_content { overflow: auto !important; height: 100vh !important; }
        .o_control_panel { display: none !important; }
    `;
    document.head.appendChild(style);
}
