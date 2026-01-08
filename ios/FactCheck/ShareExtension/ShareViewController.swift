//
//  ShareViewController.swift
//  ShareExtension
//
//  Created by harki bains on 1/8/26.
//

import UIKit
import Social
import UniformTypeIdentifiers

class ShareViewController: SLComposeServiceViewController {
    
    private var isLoading = false
    private var hasStarted = false
    private let apiService = APIService.shared

    override func viewDidLoad() {
        super.viewDidLoad()
        self.title = "Fact Check"
        
        // Hide the text view to minimize UI
        self.textView.isHidden = true
        self.textView.isEditable = false
        
        // Auto-start job creation immediately when view loads
        DispatchQueue.main.async { [weak self] in
            self?.startJobCreation()
        }
    }
    
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        
        // Hide text view after view appears (in case it shows up)
        self.textView.isHidden = true
    }

    override func isContentValid() -> Bool {
        // Always disable post button - we auto-create
        return false
    }
    
    private func startJobCreation() {
        // Prevent multiple starts
        guard !hasStarted else { return }
        hasStarted = true
        
        // Extract the shared URL and create job automatically
        guard let extensionItem = extensionContext?.inputItems.first as? NSExtensionItem else {
            self.showError("No content found")
            return
        }
        
        // Show loading - update title since textView is hidden
        isLoading = true
        self.title = "Creating job..."
        
        // Extract URL
        extractURL(from: extensionItem) { [weak self] urlString in
            guard let self = self, let url = urlString else {
                DispatchQueue.main.async {
                    self?.showError("No URL found")
                }
                return
            }
            
            // Create job via API
            Task {
                await self.createJob(url: url)
            }
        }
    }

    override func didSelectPost() {
        // This should not be called since isContentValid returns false
        // But if it is, just start job creation
        if !hasStarted {
            startJobCreation()
        }
    }
    
    private func extractURL(from extensionItem: NSExtensionItem, completion: @escaping (String?) -> Void) {
        // Try to get URL from attachments
        if let attachments = extensionItem.attachments {
            for attachment in attachments {
                // Try URL type first
                if attachment.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    attachment.loadItem(forTypeIdentifier: UTType.url.identifier, options: nil) { (item, error) in
                        if let url = item as? URL {
                            completion(url.absoluteString)
                        } else {
                            completion(nil)
                        }
                    }
                    return
                }
                // Try plain text (might contain a URL)
                else if attachment.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                    attachment.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { (item, error) in
                        if let text = item as? String {
                            // Check if text is a URL
                            let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            if trimmedText.hasPrefix("http://") || trimmedText.hasPrefix("https://") {
                                completion(trimmedText)
                            } else if trimmedText.contains("://") {
                                completion(trimmedText)
                            } else if trimmedText.contains(".") && !trimmedText.contains(" ") && trimmedText.count > 4 {
                                // Might be a URL without scheme
                                completion("https://\(trimmedText)")
                            } else {
                                completion(nil)
                            }
                        } else {
                            completion(nil)
                        }
                    }
                    return
                }
            }
        }
        
        // Fallback: try to get from text content
        if let textContent = extensionItem.attributedContentText?.string {
            let trimmedText = textContent.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedText.hasPrefix("http://") || trimmedText.hasPrefix("https://") {
                completion(trimmedText)
                return
            } else if trimmedText.contains("://") {
                completion(trimmedText)
                return
            }
        }
        
        // Also check the contentText (user's input)
        if let contentText = self.textView.text, !contentText.isEmpty {
            let trimmedText = contentText.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedText.hasPrefix("http://") || trimmedText.hasPrefix("https://") {
                completion(trimmedText)
                return
            } else if trimmedText.contains("://") {
                completion(trimmedText)
                return
            }
        }
        
        completion(nil)
    }
    
    private func createJob(url: String) async {
        do {
            let response = try await apiService.createJob(videoURL: url)
            
            // Show success message
            await MainActor.run {
                self.showSuccess("Job started")
            }
            
            // Auto-close after 2 seconds
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await MainActor.run {
                self.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
            }
        } catch let error as APIError {
            await MainActor.run {
                self.showError("Failed: \(error.errorDescription ?? "Unknown error")")
            }
        } catch {
            await MainActor.run {
                self.showError("Failed: \(error.localizedDescription)")
            }
        }
    }
    
    private func showSuccess(_ message: String) {
        // Update title since textView is hidden
        self.title = message
        self.isLoading = false
        self.reloadConfigurationItems()
        self.validateContent()
    }
    
    private func showError(_ message: String) {
        // Update title since textView is hidden
        self.title = message
        self.isLoading = false
        self.reloadConfigurationItems()
        self.validateContent()
        
        // Auto-close after 3 seconds on error
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            self.extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
        }
    }

    override func configurationItems() -> [Any]! {
        // To add configuration options via table cells at the bottom of the sheet, return an array of SLComposeSheetConfigurationItem here.
        return []
    }

}
