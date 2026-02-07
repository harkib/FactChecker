//
//  AuthService.swift
//  FactCheck
//
//  Created on 2/6/26.
//

import Foundation
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
    
    private override init() {
        super.init()
        checkAuthenticationStatus()
    }
    
    // MARK: - Keychain Management
    
    /// Store API key in Keychain
    private func storeAPIKey(_ apiKey: String) -> Bool {
        guard let data = apiKey.data(using: .utf8) else {
            return false
        }
        
        // Delete existing key if present
        deleteAPIKey()
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        
        let status = SecItemAdd(query as CFDictionary, nil)
        
        if status == errSecSuccess {
            isAuthenticated = true
            return true
        } else {
            print("Failed to store API key in Keychain: \(status)")
            return false
        }
    }
    
    /// Retrieve API key from Keychain
    func getAPIKey() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        
        if status == errSecSuccess,
           let data = result as? Data,
           let apiKey = String(data: data, encoding: .utf8) {
            return apiKey
        }
        
        return nil
    }
    
    /// Delete API key from Keychain
    private func deleteAPIKey() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey
        ]
        
        SecItemDelete(query as CFDictionary)
        isAuthenticated = false
    }
    
    /// Check if user is authenticated (has API key in Keychain)
    func checkAuthenticationStatus() {
        isAuthenticated = getAPIKey() != nil
    }
    
    // MARK: - Sign In with Apple
    
    /// Initiate Sign In with Apple flow
    func signInWithApple() {
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = [.fullName, .email]
        
        let authorizationController = ASAuthorizationController(authorizationRequests: [request])
        authorizationController.delegate = self
        authorizationController.presentationContextProvider = self
        authorizationController.performRequests()
    }
    
    /// Sign out (remove API key from Keychain)
    func signOut() {
        deleteAPIKey()
    }
    
    // MARK: - API Key Exchange
    
    /// Exchange Apple credentials for API key
    private func exchangeAppleCredentials(identityToken: String, authorizationCode: String) async throws -> String {
        guard let url = URL(string: "\(APIService.shared.baseURL)/auth/apple-signin") else {
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
            throw AuthError.apiKeyRetrievalFailed
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            print("API key exchange failed: \(errorMessage)")
            throw AuthError.apiKeyRetrievalFailed
        }
        
        let decoder = JSONDecoder()
        let authResponse = try decoder.decode(AppleSignInResponse.self, from: data)
        return authResponse.auth_key
    }
}

// MARK: - ASAuthorizationControllerDelegate

extension AuthService: ASAuthorizationControllerDelegate {
    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let appleIDCredential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            return
        }
        
        guard let identityTokenData = appleIDCredential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8),
              let authorizationCodeData = appleIDCredential.authorizationCode,
              let authorizationCode = String(data: authorizationCodeData, encoding: .utf8) else {
            print("Failed to extract credentials from Apple Sign In")
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
                if storeAPIKey(apiKey) {
                    await MainActor.run {
                        isLoading = false
                        isAuthenticated = true
                    }
                } else {
                    await MainActor.run {
                        isLoading = false
                    }
                    throw AuthError.keychainError(errSecInternalError)
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                }
                print("Failed to exchange credentials: \(error)")
            }
        }
    }
    
    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        isLoading = false
        
        if let authError = error as? ASAuthorizationError {
            if authError.code == .canceled {
                // User cancelled - don't show error
                return
            }
        }
        
        print("Apple Sign In error: \(error.localizedDescription)")
    }
}

// MARK: - ASAuthorizationControllerPresentationContextProviding

extension AuthService: ASAuthorizationControllerPresentationContextProviding {
    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        // Get the key window scene
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let window = windowScene.windows.first else {
            // Fallback - this shouldn't happen in normal app flow
            return UIWindow()
        }
        return window
    }
}
