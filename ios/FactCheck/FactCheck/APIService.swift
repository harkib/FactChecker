//
//  APIService.swift
//  FactCheck
//
//  Created on 12/30/25.
//

import Foundation
import UIKit
import UniformTypeIdentifiers

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
    
    private func addAPIKey(to request: inout URLRequest) {
        // Get API key from Keychain via AuthService
        if let apiKey = AuthService.shared.getAPIKey() {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        } else {
            // If no API key found, this request will fail - but we still set header to avoid nil
            // The API Gateway will reject it, which is expected behavior
            print("Warning: No API key found in Keychain")
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
    
    // MARK: - Push Notification (Device Token)
    
    /// Register device token with the backend for push notifications. Called when APNs returns a device token.
    func registerDeviceToken(deviceTokenHex: String) async {
        guard let url = URL(string: "\(baseURL)/device-token") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAPIKey(to: &request)
        addClientID(to: &request)
        var body: [String: Any] = ["device_token": deviceTokenHex]
        #if DEBUG || APNS_SANDBOX
        body["sandbox"] = true
        #endif
        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else { return }
        request.httpBody = bodyData
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else { return }
            if (200...299).contains(httpResponse.statusCode) {
                // Registered successfully (204 or 2xx)
            } else {
                print("Device token registration failed: \(httpResponse.statusCode)")
            }
        } catch {
            print("Device token registration error: \(error.localizedDescription)")
        }
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
    
    // MARK: - Get Job
    
    func getJob(jobId: String) async throws -> JobResponse {
        guard let url = URL(string: "\(baseURL)/jobs/\(jobId)") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        addAPIKey(to: &request)
        addClientID(to: &request)
        
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
            let jobResponse = try decoder.decode(JobResponse.self, from: data)
            return jobResponse
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
    
    // MARK: - Get Jobs
    
    func getJobs() async throws -> [JobResponse] {
        guard let url = URL(string: "\(baseURL)/jobs") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        addAPIKey(to: &request)
        addClientID(to: &request)
        
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
            let jobs = try decoder.decode([JobResponse].self, from: data)
            return jobs
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
    
    // MARK: - Create Upload Job
    
    func createUploadJob() async throws -> CreateUploadJobResponse {
        guard let url = URL(string: "\(baseURL)/upload-jobs") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAPIKey(to: &request)
        addClientID(to: &request)
        
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
            let uploadResponse = try decoder.decode(CreateUploadJobResponse.self, from: data)
            return uploadResponse
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
    
    // MARK: - Get Upload URL
    
    func getUploadURL(jobId: String) async throws -> GetUploadUrlResponse {
        guard let url = URL(string: "\(baseURL)/jobs/\(jobId)/upload-url") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        addAPIKey(to: &request)
        addClientID(to: &request)
        
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
            let uploadResponse = try decoder.decode(GetUploadUrlResponse.self, from: data)
            return uploadResponse
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
    
    // MARK: - Upload Video
    
    func uploadVideo(videoData: Data, uploadURL: URL) async throws {
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "PUT"
        request.setValue("video/mp4", forHTTPHeaderField: "Content-Type")
        request.httpBody = videoData
        
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }
            
            guard (200...299).contains(httpResponse.statusCode) else {
                throw APIError.httpError(statusCode: httpResponse.statusCode, message: "Failed to upload video")
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.networkError(error)
        }
    }
    
    // MARK: - Get Thumbnail URL
    
    func getThumbnailURL(jobId: String) async throws -> URL {
        guard let url = URL(string: "\(baseURL)/jobs/\(jobId)/thumbnail-url") else {
            throw APIError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        addAPIKey(to: &request)
        addClientID(to: &request)
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }
            
            guard (200...299).contains(httpResponse.statusCode) else {
                let errorMessage = extractErrorMessage(from: data)
                throw APIError.httpError(statusCode: httpResponse.statusCode, message: errorMessage)
            }
            
            // Parse response: {"url": "https://..."}
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let urlString = json["url"] as? String,
               let thumbnailURL = URL(string: urlString) {
                return thumbnailURL
            }
            
            throw APIError.invalidResponse
            
        } catch let error as APIError {
            throw error
        } catch let error as DecodingError {
            throw APIError.decodingError(error)
        } catch {
            throw APIError.networkError(error)
        }
    }
}

