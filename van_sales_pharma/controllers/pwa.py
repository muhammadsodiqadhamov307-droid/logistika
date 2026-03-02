# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class VanSalesPWA(http.Controller):

    @http.route('/van-manifest.json', type='http', auth='public', methods=['GET'], cors='*')
    def manifest(self):
        manifest_data = """{
    "name": "Van Sales",
    "short_name": "Van Sales",
    "start_url": "/web#action=van_sales_pharma.action_van_mobile_pos",
    "display": "standalone",
    "background_color": "#1e3a8a",
    "theme_color": "#1e3a8a",
    "icons": [
        {
            "src": "/van_sales_pharma/static/description/icon.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/van_sales_pharma/static/description/icon.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
}"""
        return request.make_response(manifest_data, headers=[
            ('Content-Type', 'application/json'),
            ('Cache-Control', 'max-age=86400')
        ])

    @http.route('/van-sw.js', type='http', auth='public', methods=['GET'])
    def service_worker(self):
        sw_data = """
const CACHE_NAME = 'van-sales-v1';
const ASSETS_TO_CACHE = [
    // We don't eagerly cache the entire Odoo system, just the shell if possible,
    // or rely on Odoo's own caching. But we cache the SW itself and basic offline page.
    '/van_sales_pharma/static/description/icon.png',
];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.filter(name => name !== CACHE_NAME)
                          .map(name => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    // Basic network-first strategy for Odoo dynamism
    // For images, we can do cache-first or stale-while-revalidate
    if (event.request.destination === 'image') {
        event.respondWith(
            caches.match(event.request).then(cachedResponse => {
                if (cachedResponse) {
                    // Return from cache, but update in background
                    fetch(event.request).then(networkResponse => {
                        caches.open(CACHE_NAME).then(cache => {
                            cache.put(event.request, networkResponse);
                        });
                    }).catch(() => {});
                    return cachedResponse;
                }
                
                // If not in cache, fetch and cache
                return fetch(event.request).then(networkResponse => {
                    const clonedRes = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, clonedRes);
                    });
                    return networkResponse;
                }).catch(() => {
                    // Optional offline placeholder
                    return new Response();
                });
            })
        );
    } else {
        // Network first for logic/html
        event.respondWith(
            fetch(event.request)
            .catch(() => caches.match(event.request))
        );
    }
});
"""
        return request.make_response(sw_data, headers=[
            ('Content-Type', 'application/javascript'),
            ('Service-Worker-Allowed', '/'),
            ('Cache-Control', 'no-cache')
        ])
