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
    @Published var jobs: [JobResponse] = []
    @Published var expandedJobIds: Set<String> = []
    @Published var isLoading: Bool = false
    @Published var isRefreshing: Bool = false
    @Published var errorMessage: String?
    
    private var jobsPollingTask: Task<Void, Never>?
    private let pollingInterval: TimeInterval = 5.0
    private nonisolated(unsafe) var jobsPollingTaskNonisolated: Task<Void, Never>?
    
    private let apiService = APIService.shared
    
    init() {
        // Start polling jobs list on initialization
        startJobsPolling()
    }
    
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
        isLoading = true
        
        Task {
            do {
                // Trim whitespace from URL before sending
                let trimmedURL = videoURL.trimmingCharacters(in: .whitespacesAndNewlines)
                let response = try await apiService.createJob(videoURL: trimmedURL)
                
                // Clear the input field
                videoURL = ""
                
                // Refresh jobs list to include the new job
                await refreshJobs()
                isLoading = false
            } catch let error as APIError {
                errorMessage = error.errorDescription ?? error.localizedDescription
                isLoading = false
            } catch {
                errorMessage = "Failed to create job: \(error.localizedDescription)"
                isLoading = false
            }
        }
    }
    
    // MARK: - Jobs List Polling
    
    func startJobsPolling() {
        stopJobsPolling() // Ensure no duplicate polling tasks
        
        let task = Task {
            // Initial fetch
            await refreshJobs()
            
            // Then poll every interval
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(pollingInterval * 1_000_000_000))
                if !Task.isCancelled {
                    await refreshJobs()
                }
            }
        }
        jobsPollingTask = task
        jobsPollingTaskNonisolated = task
    }
    
    func stopJobsPolling() {
        jobsPollingTask?.cancel()
        jobsPollingTask = nil
        jobsPollingTaskNonisolated?.cancel()
        jobsPollingTaskNonisolated = nil
    }
    
    nonisolated private func stopJobsPollingNonisolated() {
        jobsPollingTaskNonisolated?.cancel()
        jobsPollingTaskNonisolated = nil
    }
    
    func refreshJobs() async {
        isRefreshing = true
        errorMessage = nil
        
        do {
            let fetchedJobs = try await apiService.getJobs()
            jobs = fetchedJobs
            isRefreshing = false
        } catch let error as APIError {
            errorMessage = error.errorDescription ?? error.localizedDescription
            isRefreshing = false
        } catch {
            errorMessage = "Failed to fetch jobs: \(error.localizedDescription)"
            isRefreshing = false
        }
    }
    
    // MARK: - Job Expansion
    
    func toggleJobExpansion(jobId: String) {
        if expandedJobIds.contains(jobId) {
            expandedJobIds.remove(jobId)
        } else {
            expandedJobIds.insert(jobId)
        }
    }
    
    func isJobExpanded(_ jobId: String) -> Bool {
        return expandedJobIds.contains(jobId)
    }
    
    // MARK: - Share URL Handling
    
    func handleSharedURL(_ url: String) {
        // Validate URL format
        guard URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines)) != nil else {
            errorMessage = "Invalid URL format"
            return
        }
        
        // Set the URL and auto-submit
        videoURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
        submitJob()
    }
    
    // MARK: - Reset
    
    func reset() {
        stopJobsPolling()
        videoURL = ""
        jobs = []
        expandedJobIds = []
        isLoading = false
        isRefreshing = false
        errorMessage = nil
    }
    
    deinit {
        stopJobsPollingNonisolated()
    }
}
