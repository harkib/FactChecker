//
//  FactCheckApp.swift
//  FactCheck
//
//  Created by harki bains on 12/30/25.
//

import SwiftUI

@main
struct FactCheckApp: App {
    @StateObject private var viewModel = FactCheckViewModel()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(viewModel)
                .onOpenURL { url in
                    handleIncomingURL(url)
                }
                .onContinueUserActivity("NSUserActivityTypeBrowsingWeb") { userActivity in
                    if let url = userActivity.webpageURL {
                        handleIncomingURL(url)
                    }
                }
        }
    }
    
    private func handleIncomingURL(_ url: URL) {
        // Handle URL scheme (factcheck://) or universal links
        let urlString = url.absoluteString
        var extractedURL: String?
        
        // If it's our custom scheme, extract the URL parameter
        if url.scheme == "factcheck" {
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let queryItems = components.queryItems,
               let sharedURL = queryItems.first(where: { $0.name == "url" })?.value {
                extractedURL = sharedURL
            } else if let host = url.host, !host.isEmpty {
                // Handle factcheck://https://example.com format
                extractedURL = "\(url.scheme ?? "https")://\(host)\(url.path)"
            } else {
                // Try to extract from path
                let path = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                if !path.isEmpty {
                    extractedURL = path
                }
            }
        } else if url.scheme == "http" || url.scheme == "https" {
            // Direct HTTP/HTTPS URL sharing
            extractedURL = urlString
        } else {
            // For URLs shared as plain text or other formats
            if urlString.contains("://") || urlString.hasPrefix("http://") || urlString.hasPrefix("https://") {
                extractedURL = urlString
            } else {
                // Might be a plain text URL without scheme
                let potentialURL = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
                if !potentialURL.isEmpty && (potentialURL.contains(".") || potentialURL.hasPrefix("www.")) {
                    extractedURL = potentialURL.hasPrefix("http") ? potentialURL : "https://\(potentialURL)"
                }
            }
        }
        
        // Handle the URL - add to jobs list
        if let sharedURL = extractedURL {
            viewModel.handleSharedURL(sharedURL)
        }
    }
}
