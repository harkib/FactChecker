//
//  APIService.swift
//  ShareExtension
//
//  Created on 1/8/26.
//

import Foundation
import UIKit
import Security

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int, message: String)
    case decodingError(Error)
    case networkError(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .httpError(let statusCode, let message):
            return "HTTP Error \(statusCode): \(message)"
        case .decodingError(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}

class APIService {
    static let shared = APIService()
    
    // API Configuration
    var baseURL: String = "https://td14m345de.execute-api.us-east-1.amazonaws.com/prod"
    
    // Keychain keys (must match AuthService in main app)
    private let apiKeyKeychainKey = "com.factcheck.apiKey"
    private let apiKeyService = "FactCheckAPI"
    private let keychainAccessGroup = "group.HarkiBains.FactCheck"
    
    // Client ID (IDFV) - cached for performance
    private static let clientIDKey = "FactCheckClientID"
    
    private init() {}
    
    // MARK: - Helper Methods
    
    /// Get client ID (IDFV) - retrieves from UserDefaults or generates new one
    private func getClientID() -> String {
        // Check UserDefaults first
        if let cachedID = UserDefaults.standard.string(forKey: APIService.clientIDKey) {
            return cachedID
        }
        
        // Get IDFV from device
        if let idfv = UIDevice.current.identifierForVendor?.uuidString {
            // Cache it for future use
            UserDefaults.standard.set(idfv, forKey: APIService.clientIDKey)
            return idfv
        }
        
        // Fallback: generate a temporary UUID if IDFV is not available
        let fallbackID = UUID().uuidString
        UserDefaults.standard.set(fallbackID, forKey: APIService.clientIDKey)
        return fallbackID
    }
    
    /// Retrieve API key from shared Keychain (stored by main app via AuthService)
    private func getAPIKey() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: apiKeyService,
            kSecAttrAccount as String: apiKeyKeychainKey,
            kSecAttrAccessGroup as String: keychainAccessGroup,
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
    
    private func addAPIKey(to request: inout URLRequest) {
        if let apiKey = getAPIKey() {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        } else {
            print("ShareExtension: No API key found in Keychain - user may need to sign in via main app")
        }
    }
    
    private func addClientID(to request: inout URLRequest) {
        let clientID = getClientID()
        request.setValue(clientID, forHTTPHeaderField: "X-Client-ID")
    }
    
    private func extractErrorMessage(from data: Data) -> String {
        // Try to parse FastAPI error format: {"detail": "error message"}
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? String {
            return detail
        }
        // Fall back to string representation
        return String(data: data, encoding: .utf8) ?? "Unknown error"
    }
    
    // MARK: - Create Job
    
    func createJob(videoURL: String) async throws -> CreateJobResponse {
        guard let url = URL(string: "\(baseURL)/jobs") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAPIKey(to: &request)
        addClientID(to: &request)
        
        let requestBody = CreateJobRequest(video_url: videoURL)
        request.httpBody = try JSONEncoder().encode(requestBody)
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }
            
            guard (200...299).contains(httpResponse.statusCode) else {
                let errorMessage = extractErrorMessage(from: data)
                throw APIError.httpError(statusCode: httpResponse.statusCode, message: errorMessage)
            }
            
            let decoder = JSONDecoder()
            let jobResponse = try decoder.decode(CreateJobResponse.self, from: data)
            return jobResponse
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
}

