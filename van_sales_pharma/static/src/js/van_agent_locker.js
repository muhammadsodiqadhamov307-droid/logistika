/** @odoo-module **/

import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";

if (session.is_van_agent) {
    const enforcePos = () => {
        const expectedHash = "#action=van_sales_pharma.action_van_mobile_pos";
        if (browser.location.hash !== expectedHash) {
            browser.location.hash = expectedHash;
        }
    };

    // Check immediately
    enforcePos();

    // Prevent navigating away
    window.addEventListener("hashchange", enforcePos);

    // Hide the Odoo main navbar completely for agents
    const style = document.createElement('style');
    style.innerHTML = `
        .o_main_navbar { display: none !important; }
        .o_web_client { padding-top: 0 !important; }
        .o_content { overflow: auto !important; height: 100vh !important; }
    `;
    document.head.appendChild(style);
}
