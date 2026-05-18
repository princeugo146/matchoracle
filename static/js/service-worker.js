/**
 * MatchOracle Service Worker
 * Provides offline support and app-shell caching for PWA installability.
 * Registered via /sw.js (served at root scope by Django URL).
 */

const CACHE_NAME = 'matchoracle-shell-v1';

// App shell — pages and assets to pre-cache on install
const APP_SHELL = [
  '/',
  '/scores/',
  '/pricing/',
  '/accounts/login/',
  '/accounts/register/',
  '/static/manifest.json',
];

// ── Install ──────────────────────────────────────────────────────────────────
// Pre-cache the app shell so the app loads instantly on repeat visits.
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(APP_SHELL).catch(err => {
        // Non-fatal: log and continue so the SW still installs
        console.warn('[SW] Pre-cache error (non-fatal):', err);
      });
    })
  );
  // Activate immediately without waiting for old tabs to close
  self.skipWaiting();
});

// ── Activate ─────────────────────────────────────────────────────────────────
// Remove stale caches from previous SW versions.
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    )
  );
  // Take control of all open clients immediately
  self.clients.claim();
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
// Strategy: Network-first with cache fallback.
// - Non-GET requests pass through untouched (POST for forms/CSRF, etc.)
// - API, admin, and engine endpoints bypass the cache entirely
// - Successful GET responses are cached for offline use
// - When offline, serve from cache; for navigation fall back to cached "/"
self.addEventListener('fetch', event => {
  const { request } = event;

  // Only handle GET requests
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Bypass cache for dynamic/sensitive paths
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/admin/') ||
    url.pathname.startsWith('/dashboard/engine/') ||
    url.pathname.startsWith('/accounts/logout/')
  ) {
    return; // Let the browser handle these normally
  }

  event.respondWith(
    fetch(request)
      .then(response => {
        // Cache valid same-origin responses
        if (response && response.status === 200 && url.origin === self.location.origin) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => {
        // Network failed — serve from cache
        return caches.match(request).then(cached => {
          if (cached) return cached;
          // For page navigations, fall back to the cached home page
          if (request.mode === 'navigate') {
            return caches.match('/');
          }
        });
      })
  );
});
