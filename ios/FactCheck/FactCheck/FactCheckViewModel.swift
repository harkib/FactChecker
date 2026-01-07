//
//  FactCheckViewModel.swift
//  FactCheck
//
//  Created on 12/30/25.
//

import Foundation
import SwiftUI
import Combine

@MainActor
class FactCheckViewModel: ObservableObject {
    @Published var videoURL: String = ""
    @Published var currentJobId: String?
    @Published var jobStatus: String?
    @Published var jobResponse: JobResponse?
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    private var pollingTask: Task<Void, Never>?
    private let pollingInterval: TimeInterval = 5.0
    private nonisolated(unsafe) var pollingTaskNonisolated: Task<Void, Never>?
    
    private let apiService = APIService.shared
    
    // MARK: - Job Submission
    
    func submitJob() {
        guard !videoURL.isEmpty else {
            errorMessage = "Please enter a video URL"
            return
        }
        
        // Validate URL format
        guard URL(string: videoURL.trimmingCharacters(in: .whitespacesAndNewlines)) != nil else {
            errorMessage = "Please enter a valid URL"
            return
        }
        
        // Reset state
        errorMessage = nil
        jobResponse = nil
        jobStatus = nil
        isLoading = true
        
        // Stop any existing polling
        stopPolling()
        
        Task {
            do {
                // Trim whitespace from URL before sending
                let trimmedURL = videoURL.trimmingCharacters(in: .whitespacesAndNewlines)
                let response = try await apiService.createJob(videoURL: trimmedURL)
                currentJobId = response.job_id
                jobStatus = response.status
                
                // Start polling for job status
                startPolling()
            } catch let error as APIError {
                errorMessage = error.errorDescription ?? error.localizedDescription
                isLoading = false
            } catch {
                errorMessage = "Failed to create job: \(error.localizedDescription)"
                isLoading = false
            }
        }
    }
    
    // MARK: - Polling
    
    private func startPolling() {
        guard let jobId = currentJobId else { return }
        
        stopPolling() // Ensure no duplicate polling tasks
        
        let task = Task {
            while !Task.isCancelled {
                do {
                    // Wait before polling (except first time)
                    if jobStatus != nil {
                        try await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
                    }
                    
                    let response = try await apiService.getJob(jobId: jobId)
                    
                    jobStatus = response.status
                    jobResponse = response
                    
                    // Check for error message in response
                    if let errorMsg = response.error_message {
                        errorMessage = errorMsg
                    }
                    
                    // Stop polling if job is completed or failed
                    if response.status == "completed" || response.status == "failed" {
                        isLoading = false
                        stopPolling()
                        break
                    }
                    
                } catch let error as APIError {
                    // Handle API errors during polling
                    if case .httpError(let statusCode, _) = error, statusCode == 404 {
                        errorMessage = "Job not found. It may have been deleted."
                    } else {
                        errorMessage = error.errorDescription ?? error.localizedDescription
                    }
                    isLoading = false
                    stopPolling()
                    break
                } catch {
                    // Handle other errors during polling (network issues, decoding errors, etc.)
                    errorMessage = "Error checking job status: \(error.localizedDescription)"
                    isLoading = false
                    stopPolling()
                    break
                }
            }
        }
        pollingTask = task
        pollingTaskNonisolated = task
    }
    
    private func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
        pollingTaskNonisolated?.cancel()
        pollingTaskNonisolated = nil
    }
    
    nonisolated private func stopPollingNonisolated() {
        pollingTaskNonisolated?.cancel()
        pollingTaskNonisolated = nil
    }
    
    // MARK: - Reset
    
    func reset() {
        stopPolling()
        videoURL = ""
        currentJobId = nil
        jobStatus = nil
        jobResponse = nil
        isLoading = false
        errorMessage = nil
    }
    
    deinit {
        stopPollingNonisolated()
    }
}

