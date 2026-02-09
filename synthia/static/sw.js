self.addEventListener('push', function(event) {
    const data = event.data ? event.data.json() : {};
    const title = data.title || data.body || 'Synthia';
    const options = {
        body: data.title ? data.body : undefined,
        icon: '/static/apple-touch-icon.png',
        badge: '/static/apple-touch-icon.png',
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (const client of clientList) {
                if (client.url.includes('/chat') && 'focus' in client) {
                    return client.focus();
                }
            }
            return clients.openWindow('/chat');
        })
    );
});
