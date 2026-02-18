//
//  PushNotificationAppDelegate.swift
//  FactCheck
//
//  Handles remote notification registration and device token; forwards token to API.
//

import UIKit
import UserNotifications

class PushNotificationAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    /// Call from UI (e.g. when user is authenticated and on main screen) to request permission and register for remote notifications.
    static func requestPermissionAndRegisterForRemoteNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            DispatchQueue.main.async {
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        // Convert token to hex string and send to backend
        let tokenString = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        Task {
            await APIService.shared.registerDeviceToken(deviceTokenHex: tokenString)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        print("Push registration failed: \(error.localizedDescription)")
    }

    // MARK: - UNUserNotificationCenterDelegate (optional: handle notification tap)

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        // Could extract job_id from response.notification.request.content.userInfo and open that job
        completionHandler()
    }
}
