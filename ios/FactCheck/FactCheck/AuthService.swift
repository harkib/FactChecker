//
//  AuthService.swift
//  FactCheck
//
//  Created on 2/6/26.
//

import Foundation
import UIKit
import AuthenticationServices
import Security
import Combine

enum AuthError: LocalizedError {
    case noCredentials
    case keychainError(OSStatus)
    case signInCancelled
    case signInFailed(Error)
    case apiKeyRetrievalFailed
    
    var errorDescription: String? {
        switch self {
        case .noCredentials:
            return "No credentials found"
        case .keychainError(let status):
            return "Keychain error: \(status)"
        case .signInCancelled:
            return "Sign in was cancelled"
        case .signInFailed(let error):
            return "Sign in failed: \(error.localizedDescription)"
        case .apiKeyRetrievalFailed:
            return "Failed to retrieve API key from server"
        }
    }
}

class AuthService: NSObject, ObservableObject {
    static let shared = AuthService()
    
    @Published var isAuthenticated: Bool = false
    @Published var isLoading: Bool = false
    
    private let apiKeyKeychainKey = "com.factcheck.apiKey"
    private let apiKeyService = "FactCheckAPI"
    private let keychainAccessGroup = "group.HarkiBains.FactCheck"
    
    // Retain the authorization controller to prevent deallocation before delegate callbacks
    private var authorizationController: ASAuthorizationController?
    
    private override init() {
        super.init()
        // Don't call checkAuthenticationStatus() here - it's now async
        // Will be called from ContentView on app launch
    }
    
    // MARK: - Keychain Management
    
    /// Store API key in Keychain
    private func storeAPIKey(_ apiKey: String) -> Bool {
        guard let data = apiKey.data(using: .utf8) else {
            print("AuthService: Failed to convert API key to Data")
            return false
        }
        
        // Delete existing key if present
        deleteAPIKey()
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecAttrAccessGroup as String: keychainAccessGroup,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        
        let status = SecItemAdd(query as CFDictionary, nil)
        
        if status == errSecSuccess {
            // Don't set isAuthenticated here - verification will set it
            return true
        } else {
            print("AuthService: Failed to store API key in Keychain, status: \(status)")
            return false
        }
    }
    
    /// Retrieve API key from Keychain (shared with Share Extension via App Group)
    func getAPIKey() -> String? {
        // Try shared keychain first (with App Group)
        let sharedQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecAttrAccessGroup as String: keychainAccessGroup,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(sharedQuery as CFDictionary, &result)
        
        if status == errSecSuccess,
           let data = result as? Data,
           let apiKey = String(data: data, encoding: .utf8) {
            return apiKey
        }
        
        // Migration: try legacy keychain (stored before App Group was added)
        let legacyQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var legacyResult: AnyObject?
        let legacyStatus = SecItemCopyMatching(legacyQuery as CFDictionary, &legacyResult)
        
        if legacyStatus == errSecSuccess,
           let data = legacyResult as? Data,
           let apiKey = String(data: data, encoding: .utf8) {
            _ = storeAPIKey(apiKey)  // Migrate to shared keychain
            let deleteQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: apiKeyService,
                kSecAttrAccount as String: apiKeyKeychainKey
            ]
            SecItemDelete(deleteQuery as CFDictionary)  // Remove legacy
            return apiKey
        }
        
        return nil
    }
    
    /// Delete API key from Keychain
    private func deleteAPIKey() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecAttrAccessGroup as String: keychainAccessGroup
        ]
        
        SecItemDelete(query as CFDictionary)
        isAuthenticated = false
    }
    
    /// Verify API key with a single health check (for app launch verification)
    /// Returns true if API key is valid, false otherwise
    private func verifyAPIKeyOnce() async -> Bool {
        guard let apiKey = getAPIKey() else {
            return false
        }
        
        guard let url = URL(string: "\(APIService.shared.baseURL)/health") else {
            return false
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.setValue(getClientID(), forHTTPHeaderField: "X-Client-ID")
        
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            return (200...299).contains(httpResponse.statusCode)
        } catch {
            return false
        }
    }
    
    /// Check if user is authenticated by verifying API key in Keychain
    /// Verifies the API key by calling /health endpoint once
    func checkAuthenticationStatus() async {
        guard getAPIKey() != nil else {
            await MainActor.run {
                isAuthenticated = false
            }
            return
        }
        
        // Verify the key works
        let isValid = await verifyAPIKeyOnce()
        
        await MainActor.run {
            if isValid {
                isAuthenticated = true
            } else {
                // Key exists but is invalid - clear it
                deleteAPIKey()
                isAuthenticated = false
            }
        }
    }
    
    // MARK: - Sign In with Apple
    
    /// Initiate Sign In with Apple flow
    func signInWithApple() {
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = [.fullName, .email]
        
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self
        
        // Retain the controller to prevent deallocation before delegate callbacks
        self.authorizationController = controller
        
        controller.performRequests()
    }
    
    /// Sign out (remove API key from Keychain)
    func signOut() {
        deleteAPIKey()
    }
    
    // MARK: - API Key Exchange
    
    /// Exchange Apple credentials for API key
    private func exchangeAppleCredentials(identityToken: String, authorizationCode: String) async throws -> String {
        guard let url = URL(string: "\(APIService.shared.baseURL)/auth/apple-signin") else {
            print("AuthService: Invalid API URL")
            throw AuthError.apiKeyRetrievalFailed
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let requestBody = AppleSignInRequest(
            identity_token: identityToken,
            authorization_code: authorizationCode
        )
        request.httpBody = try JSONEncoder().encode(requestBody)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            print("AuthService: Invalid HTTP response")
            throw AuthError.apiKeyRetrievalFailed
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            print("AuthService: API key exchange failed with status \(httpResponse.statusCode): \(errorMessage)")
            throw AuthError.apiKeyRetrievalFailed
        }
        
        let decoder = JSONDecoder()
        let authResponse = try decoder.decode(AppleSignInResponse.self, from: data)
        return authResponse.auth_key
    }
    
    /// Verify API key works by calling /health endpoint with retries
    /// This waits for API Gateway propagation before completing authentication
    private func verifyAPIKey() async throws {
        guard let url = URL(string: "\(APIService.shared.baseURL)/health") else {
            print("AuthService: Invalid health check URL")
            throw AuthError.apiKeyRetrievalFailed
        }
        
        let maxRetries = 30
        let retryDelay: TimeInterval = 5
        var lastError: Error?
        
        for attempt in 1...maxRetries {
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            
            // Add API key header (will be retrieved from Keychain via APIService)
            if let apiKey = getAPIKey() {
                request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
            } else {
                print("AuthService: No API key found in Keychain for verification")
                throw AuthError.apiKeyRetrievalFailed
            }
            
            // Add client ID header
            let clientID = getClientID()
            request.setValue(clientID, forHTTPHeaderField: "X-Client-ID")
            
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                
                guard let httpResponse = response as? HTTPURLResponse else {
                    print("AuthService: Invalid HTTP response")
                    throw AuthError.apiKeyRetrievalFailed
                }
                
                if (200...299).contains(httpResponse.statusCode) {
                    return  // Success - API key is verified
                } else if httpResponse.statusCode == 403 {
                    // 403 means API Gateway hasn't propagated yet - retry
                    if attempt < maxRetries {
                        try await Task.sleep(nanoseconds: UInt64(retryDelay * 1_000_000_000))
                        continue
                    } else {
                        print("AuthService: Health check failed after \(maxRetries) attempts - API key may not be active")
                        throw AuthError.apiKeyRetrievalFailed
                    }
                } else {
                    // Other error - don't retry
                    let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
                    print("AuthService: Health check failed with status \(httpResponse.statusCode): \(errorMessage)")
                    throw AuthError.apiKeyRetrievalFailed
                }
            } catch {
                lastError = error
                if attempt < maxRetries {
                    try await Task.sleep(nanoseconds: UInt64(retryDelay * 1_000_000_000))
                } else {
                    print("AuthService: Health check failed after \(maxRetries) attempts")
                    throw error
                }
            }
        }
        
        // Should not reach here, but handle just in case
        if let error = lastError {
            throw error
        }
        throw AuthError.apiKeyRetrievalFailed
    }
    
    /// Get client ID (same logic as APIService)
    private func getClientID() -> String {
        let clientIDKey = "FactCheckClientID"
        
        // Check UserDefaults first
        if let cachedID = UserDefaults.standard.string(forKey: clientIDKey) {
            return cachedID
        }
        
        // Get IDFV from device
        if let idfv = UIDevice.current.identifierForVendor?.uuidString {
            // Cache it for future use
            UserDefaults.standard.set(idfv, forKey: clientIDKey)
            return idfv
        }
        
        // Fallback: generate a temporary UUID if IDFV is not available
        let fallbackID = UUID().uuidString
        UserDefaults.standard.set(fallbackID, forKey: clientIDKey)
        return fallbackID
    }
}

// MARK: - ASAuthorizationControllerDelegate

extension AuthService: ASAuthorizationControllerDelegate {
    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        // Clear the retained controller
        self.authorizationController = nil
        
        guard let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            print("AuthService: Failed to cast credential to ASAuthorizationAppleIDCredential")
            return
        }
        
        guard let identityTokenData = appleIDCredential.identityToken else {
            print("AuthService: identityToken is nil")
            return
        }
        
        guard let authorizationCodeData = appleIDCredential.authorizationCode else {
            print("AuthService: authorizationCode is nil")
            return
        }
        
        guard let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            print("AuthService: Failed to convert identityToken Data to String")
            return
        }
        
        guard let authorizationCode = String(data: authorizationCodeData, encoding: .utf8) else {
            print("AuthService: Failed to convert authorizationCode Data to String")
            return
        }
        
        isLoading = true
        
        Task {
            do {
                // Exchange Apple credentials for API key
                let apiKey = try await exchangeAppleCredentials(
                    identityToken: identityToken,
                    authorizationCode: authorizationCode
                )
                
                // Store API key in Keychain
                guard storeAPIKey(apiKey) else {
                    await MainActor.run {
                        isLoading = false
                    }
                    print("AuthService: Failed to store API key in Keychain")
                    throw AuthError.keychainError(errSecInternalError)
                }
                
                // Verify API key works by calling /health endpoint
                // This waits for API Gateway propagation before completing authentication
                try await verifyAPIKey()
                
                // API key verified - authentication complete
                await MainActor.run {
                    isLoading = false
                    isAuthenticated = true
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                }
                print("AuthService: Failed to exchange credentials: \(error.localizedDescription)")
            }
        }
    }
    
    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        // Clear the retained controller
        self.authorizationController = nil
        
        isLoading = false
        
        if let authError = error as? ASAuthorizationError {
            if authError.code == .canceled {
                // User cancelled - don't show error
                return
            }
            print("AuthService: Apple Sign In error: \(authError.localizedDescription)")
        } else {
            print("AuthService: Apple Sign In error: \(error.localizedDescription)")
        }
    }
}

// MARK: - ASAuthorizationControllerPresentationContextProviding

extension AuthService: ASAuthorizationControllerPresentationContextProviding {
    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        // Try multiple methods to get the window for better SwiftUI compatibility
        if let windowScene = UIApplication.shared.connectedScenes
            .first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene {
            if let keyWindow = windowScene.windows.first(where: { $0.isKeyWindow }) {
                return keyWindow
            }
            if let firstWindow = windowScene.windows.first {
                return firstWindow
            }
        }
        
        // Fallback: try deprecated windows property (for older iOS versions)
        if let keyWindow = UIApplication.shared.windows.first(where: { $0.isKeyWindow }) {
            return keyWindow
        }
        
        return UIWindow()
    }
}
