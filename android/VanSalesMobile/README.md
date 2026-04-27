# Van Sales Native Android

This is the native Android offline-first client for `van_sales_pharma`.

Current status: foundation slice.

Implemented:

- Native Android project scaffold.
- Local SQLite database for agent, clients, products, inventory, suppliers,
  requests, and pending sync queue.
- Token-based JSON-RPC client for the new Odoo mobile API.
- Login with Odoo URL, database name, username, and password.
- Bootstrap download and pending transaction sync shell.

Required tooling:

- Android Studio.
- Android SDK with compile SDK 36 installed.
- JDK supported by the installed Android Gradle Plugin.

Open this folder in Android Studio:

```text
android/VanSalesMobile
```

Then sync Gradle and run the `app` configuration on a device or emulator.

The first screen intentionally focuses on proving the offline data and sync
foundation before the full POS screens are added.
