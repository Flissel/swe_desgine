/**
 * RE System Dashboard - Notifications Module
 *
 * Toast notifications for user feedback.
 */

// ============================================
// Notification Container
// ============================================

let notificationContainer = null;

/**
 * Create or get the notification container
 * @returns {HTMLElement} Notification container element
 */
function getNotificationContainer() {
    if (notificationContainer) return notificationContainer;

    notificationContainer = document.getElementById('notification-container');
    if (notificationContainer) return notificationContainer;

    notificationContainer = document.createElement('div');
    notificationContainer.id = 'notification-container';
    notificationContainer.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 10px;
    `;
    document.body.appendChild(notificationContainer);
    return notificationContainer;
}

// ============================================
// Notification Display
// ============================================

/**
 * Show a notification toast
 * @param {string} message - Message to display
 * @param {string} type - Notification type: 'info', 'success', 'warn', 'error'
 * @param {number} duration - Auto-dismiss time in ms (default: 5000)
 */
export function showNotification(message, type = 'info', duration = 5000) {
    const container = getNotificationContainer();

    const icons = {
        success: '✓',
        warn: '⚠',
        error: '✕',
        info: 'ℹ'
    };

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span class="notification-icon">${icons[type] || icons.info}</span>
        <span class="notification-message">${message}</span>
        <button class="notification-close" aria-label="Close">×</button>
    `;

    // Add close button handler
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => notification.remove());

    container.appendChild(notification);

    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(() => {
            if (notification.parentElement) {
                notification.classList.add('notification-fade-out');
                setTimeout(() => notification.remove(), 300);
            }
        }, duration);
    }

    return notification;
}

/**
 * Show a success notification
 * @param {string} message - Message to display
 */
export function showSuccess(message) {
    return showNotification(message, 'success');
}

/**
 * Show a warning notification
 * @param {string} message - Message to display
 */
export function showWarning(message) {
    return showNotification(message, 'warn');
}

/**
 * Show an error notification
 * @param {string} message - Message to display
 */
export function showError(message) {
    return showNotification(message, 'error', 8000);
}

/**
 * Clear all notifications
 */
export function clearNotifications() {
    const container = getNotificationContainer();
    container.innerHTML = '';
}
